"""Rules text on request: `get_state` with `card` gives the rules text of the cards a seat names.

Only cards the calling seat may see are answered: every public zone's, the stack's, its own
hand's and library's, and those a pending choice addressed to it reveals. A name says nothing
of where the card was found, so asking by name about a card of the seat's own library gives
nothing away; an instance id of such a card would, and is refused.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.game.cards_in_play import card_of
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import HIDDEN_ZONES, CardInstance, Game, TokenSpec, Zone
from mtg_goldfishing.domain.game.naming import is_instance_id, matches
from mtg_goldfishing.domain.game.seats import SeatNumber

PUBLIC_IN_ORDER = (Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND)
"""The public zones a name is looked for in, in order, each across every seat."""


@dataclass(frozen=True)
class RulesText:
    """What `get_state` answers for `card`: the card data of each card named, or the spec of
    each token named, once each, in the order first named. It says nothing of where any
    card is, nor which instance it is."""

    cards: tuple[Card | TokenSpec, ...]


def _entries(card: object) -> list[str] | Error:
    """The names and instance ids `card` gives, each without its surrounding whitespace."""
    given = [card] if isinstance(card, str) else card
    if not isinstance(given, list) or not given or not all(isinstance(e, str) for e in given):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="card")
    entries = [entry.strip() for entry in given]
    if not all(entries):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="card")
    return entries


def _revealed_to(game: Game, seat: SeatNumber) -> list[str]:
    """The instance ids the pending choices addressed to the seat reveal to it."""
    return [card for choice in game.pending if choice.seat == seat for card in choice.revealed]


def _seen_by_name(game: Game, seat: SeatNumber) -> Iterator[CardInstance]:
    """Every card the seat may see, in the order a name is looked for: its own hand; each
    public zone across every seat, the calling seat's first; the stack, top first; the
    cards revealed to it; its own library."""
    yield from game.hand_of(seat)
    seats = [seat, *(other.number for other in game.others_from(seat))]
    for zone in PUBLIC_IN_ORDER:
        for whose in seats:
            yield from game.in_zone(zone, whose)
    for item in reversed(game.stack):
        found = game.find(item.card) if item.card is not None else None
        if found is not None:
            yield found
    yield from (game.instance(instance_id) for instance_id in _revealed_to(game, seat))
    yield from game.in_zone(Zone.LIBRARY, seat)


def _by_id(game: Game, seat: SeatNumber, entry: str) -> CardInstance | Error:
    card = game.find(entry)
    if card is None:
        return Error(ErrorKind.NO_CARD_SEEN, subject=entry)
    if card.zone not in HIDDEN_ZONES or card.id in _revealed_to(game, seat):
        return card
    if card.owner != seat:
        return Error(ErrorKind.HIDDEN_ZONE, subject=card.id, number=card.owner.value)
    if card.zone is Zone.LIBRARY:
        return Error(ErrorKind.LIBRARY_CARD_BY_ID, subject=card.id)
    return card


def _by_name(game: Game, decks: Decks, seat: SeatNumber, entry: str) -> CardInstance | Error:
    found = next(
        (card for card in _seen_by_name(game, seat) if matches(decks.of(card.owner), card, entry)),
        None,
    )
    return found if found is not None else Error(ErrorKind.NO_CARD_SEEN, subject=entry)


def _text_of(decks: Decks, card: CardInstance) -> Card | TokenSpec | None:
    """A token's spec, or a card's own data: the data it carries, else its owner's deck's."""
    if card.is_token:
        return card.token
    return card_of(decks.of(card.owner), card)


# @spec GAME-186, GAME-187, GAME-188, GAME-189, GAME-190, GAME-191, GAME-192, GAME-193
# @spec GAME-194, GAME-195, GAME-196, GAME-197
def rules_text(
    game: Game, decks: Decks, seat: SeatNumber, card: object, *, detail: object = None
) -> RulesText | Error:
    """The rules text of the cards `card` names, for the calling seat, in any game.

    `card` is a name or instance id, or a non-empty list of them; it is not given with
    `detail`. Each entry is resolved in turn, and the first one refused refuses the call. A
    card is answered with its own data, a token with its spec, and each only once.
    """
    if detail is not None:
        return Error(ErrorKind.CARD_WITH_DETAIL)
    entries = _entries(card)
    if isinstance(entries, Error):
        return entries
    answered: list[Card | TokenSpec] = []
    for entry in entries:
        found = (
            _by_id(game, seat, entry)
            if is_instance_id(entry)
            else _by_name(game, decks, seat, entry)
        )
        if isinstance(found, Error):
            return found
        text = _text_of(decks, found)
        if text is None:
            return Error(ErrorKind.NO_CARD_SEEN, subject=entry)
        if text not in answered:
            answered.append(text)
    return RulesText(tuple(answered))
