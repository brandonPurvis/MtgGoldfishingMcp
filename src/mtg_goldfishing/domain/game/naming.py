"""Naming cards in calls: full names, face names or instance ids, ignoring case."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, InstanceChosen
from mtg_goldfishing.domain.game.cards_in_play import names_of
from mtg_goldfishing.domain.game.model import HIDDEN_ZONES, CardInstance, Game, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber

_INSTANCE_ID = re.compile(r"^c\d+$", re.IGNORECASE)


class Purpose(Enum):
    """What the operation will do with the card, which decides the natural candidate."""

    ANY = "any"
    TAP = "tap"
    UNTAP = "untap"


def is_instance_id(name: str) -> bool:
    return bool(_INSTANCE_ID.match(name.strip()))


def matches(deck: LoadedDeck, card: CardInstance, name: str) -> bool:
    """Whether a name given in a call refers to this instance."""
    wanted = name.strip().casefold()
    if is_instance_id(name):
        return card.id == wanted
    return any(candidate.casefold() == wanted for candidate in names_of(deck, card))


def _preference(card: CardInstance, purpose: Purpose) -> tuple[int, int]:
    natural = {Purpose.TAP: not card.tapped, Purpose.UNTAP: card.tapped}.get(purpose, True)
    return (0 if natural else 1, card.number)


def _differ(cards: Sequence[CardInstance]) -> bool:
    first = cards[0]
    return any(
        (c.tapped, c.counters, c.face) != (first.tapped, first.counters, first.face)
        for c in cards[1:]
    )


def _visible_to(card: CardInstance, seat: SeatNumber) -> bool:
    """Whether a seat may see the card: in a public zone, or in its own hand or library."""
    return card.zone not in HIDDEN_ZONES or card.owner == seat


def _missing(
    game: Game, deck: LoadedDeck, seat: SeatNumber, name: str, zones: Sequence[Zone]
) -> Error:
    elsewhere = next(
        (
            c.zone.value
            for c in game.cards
            if c.zone not in zones and _visible_to(c, seat) and matches(deck, c, name)
        ),
        None,
    )
    return Error(
        ErrorKind.CARD_NOT_IN_ZONE,
        subject=name,
        zone=" or ".join(zone.value for zone in zones),
        found_in=elsewhere,
    )


def _searched(game: Game, seat: SeatNumber, zone: Zone) -> list[SeatNumber]:
    """Whose cards a zone is searched among, in order.

    A hidden zone holds only the acting seat's own cards; a public zone holds the cards the
    acting seat controls first, then every other seat's in turn order from the next seat.
    """
    if zone in HIDDEN_ZONES:
        return [seat]
    return [seat, *(other.number for other in game.others_from(seat))]


# @spec GAME-013, GAME-014, GAME-015, GAME-016, GAME-017, GAME-018
def resolve(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    names: Sequence[str],
    zones: Sequence[Zone],
    *,
    purpose: Purpose = Purpose.ANY,
) -> tuple[list[CardInstance], list[InstanceChosen]] | Error:
    """Resolve each name to a different instance in the expected zones, for the acting seat.

    Zones are searched in the order given, and within a zone the acting seat's cards come
    before other seats' (see `_searched`). Instance ids are resolved first; each name then
    takes a matching instance no id or earlier name has taken, so a name given more than
    once means that many different instances. When the matching instances differ from one
    another, the chosen instance is reported by id. The result follows the order of the
    names given.
    """

    def candidates_for(name: str) -> list[CardInstance]:
        return [
            card
            for zone in zones
            for whose in _searched(game, seat, zone)
            for card in sorted(game.in_zone(zone, whose), key=lambda c: _preference(c, purpose))
            if matches(deck, card, name)
        ]

    picks: dict[int, CardInstance] = {}
    taken: set[str] = set()
    for position, name in enumerate(names):
        if not is_instance_id(name):
            continue
        key = name.strip().lower()
        if key in taken:
            return Error(ErrorKind.INSTANCE_REPEATED, subject=key)
        found = candidates_for(name)
        if not found:
            return _missing(game, deck, seat, name, zones)
        picks[position] = found[0]
        taken.add(key)
    named_by_id = set(taken)
    reported: list[InstanceChosen] = []
    for position, name in enumerate(names):
        if is_instance_id(name):
            continue
        candidates = candidates_for(name)
        if not candidates:
            return _missing(game, deck, seat, name, zones)
        free = [card for card in candidates if card.id not in taken]
        if not free:
            wanted = name.strip().casefold()
            return Error(
                ErrorKind.TOO_FEW_MATCHING,
                subject=name,
                number=len(candidates),
                expected=sum(1 for n in names if n.strip().casefold() == wanted)
                + sum(1 for card in candidates if card.id in named_by_id),
            )
        pick = free[0]
        if len(candidates) > 1 and _differ(candidates):
            reported.append(InstanceChosen(name, pick.id))
        picks[position] = pick
        taken.add(pick.id)
    return [picks[position] for position in range(len(names))], reported


def resolve_one(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    name: str,
    zones: Sequence[Zone],
    *,
    purpose: Purpose = Purpose.ANY,
) -> tuple[CardInstance, list[InstanceChosen]] | Error:
    found = resolve(game, deck, seat, [name], zones, purpose=purpose)
    if isinstance(found, Error):
        return found
    cards, reported = found
    return cards[0], reported
