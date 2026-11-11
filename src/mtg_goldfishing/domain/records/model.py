"""The shapes of the records: log entries, turn snapshots and call records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.steps import Step


@dataclass(frozen=True)
class HandCard:
    name: str
    payable: bool


@dataclass(frozen=True)
class PermanentRecord:
    name: str
    tapped: bool
    counters: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ReminderRecord:
    """A reminder issued for one permanent.

    `card` is the name of the permanent's face in play. `instance_id`, `card_name` and
    `turn` are kept so a later `effect` can be judged to answer it from the log alone.
    """

    card: str
    step: Step
    instance_id: str = ""
    card_name: str = ""
    turn: int = 0


@dataclass(frozen=True)
class TurnSnapshot:
    """The state of a game at the end of a turn."""

    turn: int
    hand: tuple[HandCard, ...]
    battlefield: tuple[PermanentRecord, ...]
    graveyard: tuple[str, ...]
    lands: int
    mana_available: int
    mana_spent: int
    land_drop_made: bool
    life: int
    damage_dealt: int
    commander_damage: tuple[tuple[str, tuple[int, ...]], ...]
    unanswered_reminders: tuple[ReminderRecord, ...]
    written_by: int = 0


@dataclass(frozen=True)
class Payment:
    cost: str
    sources: tuple[str, ...]
    life: int
    from_pool: str
    surplus: str


@dataclass(frozen=True)
class LogEntry:
    """The record of one accepted change to a game."""

    seq: int
    turn: int
    step: Step | None
    tool: str
    arguments: dict[str, object]
    outcome: dict[str, object] | None
    card: str | None
    from_zone: str | None
    delta: dict[str, object] | None
    choices: dict[str, object] | None
    paid: Payment | None
    drawn: tuple[str, ...]
    steps: tuple[Step, ...]
    reason: str | None
    override: str | None
    overridden_checks: tuple[str, ...]
    expect_mismatches: tuple[str, ...]
    reminders: tuple[ReminderRecord, ...]
    assumptions: tuple[str, ...]
    notices: tuple[str, ...]


@dataclass(frozen=True)
class CallRecord:
    """One tool call exactly as it was made and answered.

    `seat` is the calling seat's number in a contested game; a goldfish game's call records,
    a contested game's `new_game` and a call whose id names no seat name none.
    """

    time: datetime
    game_id: str | None
    tool: str
    arguments: dict[str, object]
    status: str
    response: str
    is_override: bool
    change: int | None
    id: int = 0
    seat: SeatNumber | None = None
