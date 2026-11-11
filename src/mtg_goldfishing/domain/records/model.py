"""The shapes of the records: log entries, turn snapshots and call records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mtg_goldfishing.domain.events import Event
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
    `turn` (the table turn) are kept so a later `effect` can be judged to answer it from the
    log alone. In a contested game `seat` names the seat it was issued to.
    """

    card: str
    step: Step
    instance_id: str = ""
    card_name: str = ""
    turn: int = 0
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class ContestedSnapshot:
    """What a contested game's snapshot adds: the seat it describes, the table turn and
    round, every seat's life, the eliminated seats, and the described seat's commander
    damage to every other seat."""

    seat: SeatNumber
    table_turn: int
    round: int
    lives: tuple[tuple[SeatNumber, int], ...]
    eliminated: tuple[SeatNumber, ...]
    commander_damage: tuple[tuple[str, tuple[tuple[SeatNumber, int], ...]], ...]


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
    contested: ContestedSnapshot | None = None

    @property
    def table_turn(self) -> int:
        """The table turn the snapshot is kept by; in a goldfish game, its turn."""
        return self.turn if self.contested is None else self.contested.table_turn


@dataclass(frozen=True)
class Payment:
    cost: str
    sources: tuple[str, ...]
    life: int
    from_pool: str
    surplus: str


@dataclass(frozen=True)
class SeatEvents:
    """A call's summary and events as one seat may see them."""

    seat: SeatNumber
    events: tuple[Event, ...]


@dataclass(frozen=True)
class EliminationRecord:
    """A seat a call eliminated, and why: `life`, `commander_damage` or `concede`."""

    seat: SeatNumber
    cause: str


@dataclass(frozen=True)
class ResolvedRecord:
    """A stack item a call resolved: its id, its controller, its source, the delta applied
    (with what the service added) and where its card went (None for an ability)."""

    item: str
    controller: SeatNumber
    source: str
    delta: dict[str, object]
    to: str | None


@dataclass(frozen=True)
class AutoPassRecord:
    """An automatic pass a call caused: the seat, and the item passed on (None in an
    `attack` or `end` window with an empty stack)."""

    seat: SeatNumber
    item: str | None


@dataclass(frozen=True)
class ContestedEntry:
    """What a contested game's log entry adds.

    `seat` made the call (None for `new_game`); `active`, `table_turn` and `round` place
    it in the game as it stood before the call. `public` is the public form of the call's
    summary and events; `private` holds, for each other seat that may see more of them,
    the same events in the form that seat may see. `stacked` names the item the call put on
    the stack; `resolved`, `countered`, `removed` and `auto_passes` the items it resolved,
    countered or took off the stack and the automatic passes it caused.
    """

    seat: SeatNumber | None
    active: SeatNumber | None
    table_turn: int
    round: int
    eliminated: tuple[EliminationRecord, ...] = ()
    no_blocks: tuple[SeatNumber, ...] = ()
    public: tuple[Event, ...] = ()
    private: tuple[SeatEvents, ...] = ()
    stacked: str | None = None
    resolved: tuple[ResolvedRecord, ...] = ()
    countered: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    auto_passes: tuple[AutoPassRecord, ...] = ()


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
    contested: ContestedEntry | None = None
    cast_triggers: tuple[dict[str, object], ...] = ()


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
