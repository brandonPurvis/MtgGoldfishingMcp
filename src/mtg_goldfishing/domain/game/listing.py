"""`get_state`: the zones and what the service has read, when the status line is not enough."""

from __future__ import annotations

from dataclasses import dataclass, replace

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, NoticeKind
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
    Seat,
    Zone,
)
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.reading.model import ManaAbility
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


DETAILS = ("summary", "full")


def _permanent(game: Game, deck: LoadedDeck, card: CardInstance) -> PermanentListing:
    return PermanentListing(
        instance_id=card.id,
        name=face_name(deck, card),
        tapped=card.tapped,
        counters=tuple(sorted(card.counters.items())),
        mana=reading_of(deck, card).mana_abilities,
        haste=has_haste(game, deck, card),
        vigilance=has_vigilance(game, deck, card),
        triggers=reading_of(deck, card).step_triggers,
        owner=card.owner if game.contested and card.owner != card.controller else None,
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
        battlefield=tuple(
            _permanent(game, decks.of(card.owner), card) for card in game.battlefield_of(number)
        ),
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


# @spec GAME-029, GAME-030, GAME-031, GAME-032, GAME-088, GAME-089, GAME-121, GAME-122
# @spec GAME-124, GAME-125
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
    battlefield = tuple(
        _permanent(game, every.of(card.owner), card) for card in game.battlefield_of(seat)
    )
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
