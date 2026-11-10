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
from mtg_goldfishing.domain.game.model import OPPONENTS, Game, PaymentRecord, Zone
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


@dataclass(frozen=True)
class CommanderListing:
    name: str
    casts: int
    damage: tuple[int, ...]


@dataclass(frozen=True)
class StateListing:
    """The listing; the fields after `notices` are present only for the full detail."""

    hand: tuple[str, ...]
    battlefield: tuple[PermanentListing, ...]
    graveyard: tuple[str, ...]
    command: tuple[str, ...]
    notices: tuple[NoticeKind, ...]
    exile: tuple[str, ...] | None = None
    library_size: int | None = None
    commanders: tuple[CommanderListing, ...] | None = None
    payments: tuple[PaymentRecord, ...] | None = None


DETAILS = ("summary", "full")


# @spec GAME-029, GAME-030, GAME-031, GAME-032
def list_state(game: Game, deck: LoadedDeck, detail: object = None) -> StateListing | Error:
    """List the game's public zones. The library's contents and order are never listed."""
    detail = detail or "summary"
    if detail not in DETAILS:
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="detail", names=DETAILS)
    battlefield = tuple(
        PermanentListing(
            instance_id=card.id,
            name=face_name(deck, card),
            tapped=card.tapped,
            counters=tuple(sorted(card.counters.items())),
            mana=reading_of(deck, card).mana_abilities,
            haste=has_haste(game, deck, card),
            vigilance=has_vigilance(game, deck, card),
            triggers=reading_of(deck, card).step_triggers,
        )
        for card in game.battlefield
    )
    listing = StateListing(
        hand=tuple(card.name for card in game.hand),
        battlefield=battlefield,
        graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD)),
        command=tuple(card.name for card in game.in_zone(Zone.COMMAND)),
        notices=tuple(game.notices),
    )
    if detail == "summary":
        return listing
    return replace(
        listing,
        exile=tuple(card.name for card in game.in_zone(Zone.EXILE)),
        library_size=len(game.library),
        commanders=tuple(
            CommanderListing(
                c.name,
                game.commander_casts.get(c.id, 0),
                tuple(game.commander_damage.get(c.id, [0] * OPPONENTS)),
            )
            for c in game.commanders
        ),
        payments=tuple(game.turn_stats.payments),
    )
