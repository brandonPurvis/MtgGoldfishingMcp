"""`get_state`: the zones and what the service has read, when the status line is not enough."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, NoticeKind, RevealedCard
from mtg_goldfishing.domain.game.cards_in_play import (
    face_name,
    has_haste,
    has_vigilance,
    reading_of,
)
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import (
    OPPONENTS,
    CardInstance,
    Game,
    PaymentRecord,
    PendingChoice,
    Seat,
    Zone,
)
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.reading.model import ManaAbility, Whose
from mtg_goldfishing.domain.steps import Step


@dataclass(frozen=True)
class PermanentListing:
    instance_id: str
    name: str
    tapped: bool
    counters: tuple[tuple[str, int], ...]
    mana: tuple[ManaAbility, ...]
    haste: bool
    vigilance: bool
    triggers: tuple[Step, ...]
    owner: SeatNumber | None = None
    """In a contested game, the seat that owns the permanent when it is not its controller."""
    opponent_triggers: tuple[Step, ...] = ()
    """In a contested game, the steps it has a trigger in on opponents' turns only."""


@dataclass(frozen=True)
class CommanderListing:
    name: str
    casts: int
    damage: tuple[int, ...]


@dataclass(frozen=True)
class SeatListing:
    """One seat of a contested game as any seat may see it: its life, the sizes of its hand
    and library, whether it is eliminated, and its public zones. `exile` and `commanders`
    are present only for the full detail; a commander's damage is to each other seat in
    ascending seat number."""

    seat: SeatNumber
    life: int
    hand_size: int
    library_size: int
    eliminated: bool
    battlefield: tuple[PermanentListing, ...]
    graveyard: tuple[str, ...]
    command: tuple[str, ...]
    exile: tuple[str, ...] | None = None
    commanders: tuple[CommanderListing, ...] | None = None


@dataclass(frozen=True)
class StackListing:
    """One item on the stack as any seat may see it."""

    item: str
    source: str
    controller: SeatNumber


@dataclass(frozen=True)
class WindowListing:
    """The open response window: what opened it and the seat it is asking, if any."""

    kind: str
    asking: SeatNumber | None


@dataclass(frozen=True)
class ChoiceListing:
    """A pending choice the calling seat owes, with what it asks: the cards a `look`,
    `search` or `hand` choice revealed; the text of an `ask` and the seat that asked; the
    attackers a `blocks` choice may block; or the stack item a `resolve` choice is about,
    with its source, held delta and destination (None for its default one) and the error
    that kept it from resolving as held."""

    choice_id: str
    kind: str
    revealed: tuple[RevealedCard, ...] = ()
    text: str = ""
    asked_by: SeatNumber | None = None
    attackers: tuple[RevealedCard, ...] = ()
    item: str | None = None
    source: str = ""
    delta: Mapping[str, object] = field(default_factory=dict)
    to: str | None = None
    error: Error | None = None


@dataclass(frozen=True)
class StateListing:
    """The listing; the fields after `notices` are present only for the full detail.

    The zones are the calling seat's. A contested game's listing also has `seats`: every
    seat in turn order, as any seat may see it.
    """

    hand: tuple[str, ...]
    battlefield: tuple[PermanentListing, ...]
    graveyard: tuple[str, ...]
    command: tuple[str, ...]
    notices: tuple[NoticeKind, ...]
    exile: tuple[str, ...] | None = None
    library_size: int | None = None
    commanders: tuple[CommanderListing, ...] | None = None
    payments: tuple[PaymentRecord, ...] | None = None
    seats: tuple[SeatListing, ...] | None = None
    seat: SeatNumber | None = None
    """The calling seat, in a contested game."""
    stack: tuple[StackListing, ...] = ()
    """In a contested game, the items on the stack, top first."""
    window: WindowListing | None = None
    """In a contested game, the open response window."""
    choices: tuple[ChoiceListing, ...] = ()
    """In a contested game, the pending choices the calling seat owes, in the order they
    will be answered."""


DETAILS = ("summary", "full")


# @spec GAME-030, GAME-123, GAME-171
def _permanent(game: Game, decks: Decks, card: CardInstance) -> PermanentListing:
    """A permanent as listed: its triggers on its controller's turn or each turn, and, in a
    contested game, apart from them, those on opponents' turns only; a goldfish game, which
    has no opponents' turns, lists none of those. The permanent, and every permanent that
    could grant it haste or vigilance, is read from its owner's deck."""
    deck = decks.of(card.owner)
    triggers = reading_of(deck, card).step_triggers
    own = tuple(dict.fromkeys(t.step for t in triggers if t.whose is not Whose.OPPONENTS))
    others = tuple(dict.fromkeys(t.step for t in triggers if t.whose is Whose.OPPONENTS))
    return PermanentListing(
        instance_id=card.id,
        name=face_name(deck, card),
        tapped=card.tapped,
        counters=tuple(sorted(card.counters.items())),
        mana=reading_of(deck, card).mana_abilities,
        haste=has_haste(game, deck, card, decks),
        vigilance=has_vigilance(game, deck, card, decks),
        triggers=own,
        owner=card.owner if game.contested and card.owner != card.controller else None,
        opponent_triggers=others if game.contested else (),
    )


def _seat_listing(game: Game, decks: Decks, seat: Seat, full: bool) -> SeatListing:
    """A seat's public zones, each permanent read with its owner's deck."""
    number = seat.number
    others = [other.number for other in game.seats if other.number != number]
    return SeatListing(
        seat=number,
        life=seat.life,
        hand_size=len(game.hand_of(number)),
        library_size=len(seat.library),
        eliminated=seat.eliminated,
        battlefield=tuple(_permanent(game, decks, card) for card in game.battlefield_of(number)),
        graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD, number)),
        command=tuple(card.name for card in game.in_zone(Zone.COMMAND, number)),
        exile=tuple(card.name for card in game.in_zone(Zone.EXILE, number)) if full else None,
        commanders=tuple(
            CommanderListing(
                c.name,
                seat.commander_casts.get(c.id, 0),
                tuple(seat.commander_damage_to(c, other) for other in others),
            )
            for c in game.commanders_of(number)
        )
        if full
        else None,
    )


def _cards(
    game: Game, decks: Decks, instance_ids: list[str], *, by_face: bool
) -> tuple[RevealedCard, ...]:
    """The cards a choice shows that are still in the game: by card name, as revealed, or by
    the name of the face in play."""
    shown = []
    for instance_id in instance_ids:
        card = next((c for c in game.cards if c.id == instance_id), None)
        if card is not None:
            name = face_name(decks.of(card.owner), card) if by_face else card.name
            shown.append(RevealedCard(card.id, name))
    return tuple(shown)


# @spec GAME-173, GAME-174, GAME-175, GAME-176
def _choice(game: Game, decks: Decks, choice: PendingChoice) -> ChoiceListing:
    """A pending choice as the seat it is addressed to may see it, with what it asks."""
    listed = ChoiceListing(choice.choice_id, choice.kind)
    if choice.kind == "ask":
        return replace(listed, text=choice.text, asked_by=choice.asked_by)
    if choice.kind == "blocks":
        return replace(listed, attackers=_cards(game, decks, choice.attackers, by_face=True))
    if choice.kind == "resolve":
        item = next((i for i in game.stack if i.id == choice.item), None)
        if item is None:
            return replace(listed, item=choice.item, source=choice.source, error=choice.error)
        return replace(
            listed,
            item=item.id,
            source=item.source,
            delta=dict(item.delta),
            to=item.to.value if item.to is not None else None,
            error=choice.error,
        )
    return replace(listed, revealed=_cards(game, decks, choice.revealed, by_face=False))


# @spec GAME-029, GAME-030, GAME-031, GAME-032, GAME-088, GAME-089, GAME-121, GAME-122
# @spec GAME-124, GAME-125, GAME-172, GAME-177
def list_state(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    detail: object = None,
    decks: Decks | None = None,
) -> StateListing | Error:
    """List the calling seat's zones, and in a contested game every seat's public zones and
    the sizes of its hand and library. No library's contents or order is ever listed, nor
    any hand but the calling seat's. `decks` gives each seat's deck; omitted, every seat
    plays `deck`."""
    detail = detail or "summary"
    listed = game.seat(seat)
    imaginary = game.imaginary
    if detail not in DETAILS:
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="detail", names=DETAILS)
    every = decks or Decks.everyone_playing(game, deck)
    battlefield = tuple(_permanent(game, every, card) for card in game.battlefield_of(seat))
    full = detail == "full"
    listing = StateListing(
        hand=tuple(card.name for card in game.hand_of(seat)),
        battlefield=battlefield,
        graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD, seat)),
        command=tuple(card.name for card in game.in_zone(Zone.COMMAND, seat)),
        notices=tuple(game.notices),
        seats=tuple(_seat_listing(game, every, s, full) for s in game.seats)
        if game.contested
        else None,
        seat=seat if game.contested else None,
        stack=tuple(
            StackListing(item.id, item.source, item.controller) for item in reversed(game.stack)
        ),
        window=WindowListing(game.window.kind.value, game.window.asking)
        if game.window is not None
        else None,
        choices=tuple(_choice(game, every, c) for c in game.pending if c.seat == seat)
        if game.contested
        else (),
    )
    if not full:
        return listing
    return replace(
        listing,
        exile=tuple(card.name for card in game.in_zone(Zone.EXILE, seat)),
        library_size=len(listed.library),
        commanders=tuple(
            CommanderListing(
                c.name,
                listed.commander_casts.get(c.id, 0),
                tuple(imaginary.commander_damage.get(c.id, [0] * OPPONENTS) if imaginary else ()),
            )
            for c in game.commanders_of(seat)
        ),
        payments=tuple(listed.turn_stats.payments),
    )
