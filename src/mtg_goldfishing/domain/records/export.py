"""The `get_log` export: a game's records as JSON-ready data.

The export carries the records' own fields and nothing computed from them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from enum import Enum

from mtg_goldfishing.domain.events import Event
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.records.model import (
    CallRecord,
    ContestedEntry,
    ContestedSnapshot,
    LogEntry,
    Payment,
    ReminderRecord,
    TurnSnapshot,
)
from mtg_goldfishing.domain.records.reminders import judge_reminders


# @spec REC-019, REC-020, REC-021, REC-022, REC-025
def export(
    game: Game,
    entries: Sequence[LogEntry],
    snapshots: Sequence[TurnSnapshot],
    calls: Sequence[CallRecord],
    *,
    since: int | None,
    include_snapshots: bool = True,
    include_calls: bool = False,
) -> dict[str, object]:
    """The get_log document for a game.

    With `since`, only entries numbered after it, call records whose change number is
    after it, and snapshots written by those entries are kept. Snapshots are left out
    when `include_snapshots` is false, call records unless `include_calls` is true; a
    left-out section is absent from the document. Reminders are judged over every entry,
    so a reminder answered after `since` reads as answered.
    """
    verdicts = iter(judge_reminders(entries))
    answered = [[next(verdicts).answered for _ in entry.reminders] for entry in entries]

    def after_since(number: int | None) -> bool:
        return since is None or (number is not None and number > since)

    document: dict[str, object] = {
        "game": game_to_data(game),
        "entries": [
            log_entry_to_data(entry, verdict)
            for entry, verdict in zip(entries, answered, strict=True)
            if after_since(entry.seq)
        ],
    }
    if include_snapshots:
        document["snapshots"] = [
            snapshot_to_data(s) for s in snapshots if after_since(s.written_by)
        ]
    if include_calls:
        document["calls"] = [call_record_to_data(c) for c in calls if after_since(c.change)]
    return document


# @spec REC-056, REC-063
def game_to_data(game: Game) -> dict[str, object]:
    """The header of the export. In a contested game `turn` is the tested seat's own turn
    count, beside the table turn, the round and every seat in turn order."""
    result = game.result
    data: dict[str, object] = {
        "game_id": game.game_id,
        "deck_id": game.tested.deck_id,
        "seed": game.seed,
        "turn_limit": game.turn_limit,
        "draw_first_turn": game.draw_first_turn,
        "status": game.status.value,
        "turn": game.tested.turns if game.contested else game.turn,
        "change": game.change,
        "result": {"outcome": result.outcome.value, "notes": result.notes} if result else None,
    }
    if game.contested:
        data["table_turn"] = game.turn
        data["round"] = game.round
        data["seats"] = [
            {
                "number": seat.number.value,
                "deck_id": seat.deck_id,
                "tested": seat.tested,
                "starting_life": seat.starting_life,
                "life": seat.life,
                "eliminated": seat.eliminated,
            }
            for seat in game.seats
        ]
    return data


def _value_to_data(value: object) -> object:
    """A value inside an event as JSON-ready data."""
    if isinstance(value, SeatNumber):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ManaString):
        return str(value)
    if isinstance(value, tuple | list):
        return [_value_to_data(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _value_to_data(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    return value


# @spec REC-040
def event_to_data(event: Event) -> dict[str, object]:
    """An event as data: its type's name and its fields."""
    fields = _value_to_data(event)
    assert isinstance(fields, dict)
    return {"type": type(event).__name__, **fields}


def _reminder_to_data(reminder: ReminderRecord, answered: bool | None) -> dict[str, object]:
    data: dict[str, object] = {
        "card": reminder.card,
        "step": reminder.step.value,
        "instance_id": reminder.instance_id,
    }
    if reminder.seat is not None:
        data["seat"] = reminder.seat.value
    if answered is not None:
        data["answered"] = answered
    return data


def _contested_entry_to_data(contested: ContestedEntry) -> dict[str, object]:
    return {
        "seat": None if contested.seat is None else contested.seat.value,
        "active": None if contested.active is None else contested.active.value,
        "table_turn": contested.table_turn,
        "round": contested.round,
        "eliminated": [
            {"seat": record.seat.value, "cause": record.cause} for record in contested.eliminated
        ],
        "no_blocks": [seat.value for seat in contested.no_blocks],
        "stacked": contested.stacked,
        "resolved": [
            {
                "item": record.item,
                "controller": record.controller.value,
                "source": record.source,
                "delta": _value_to_data(record.delta),
                "to": record.to,
            }
            for record in contested.resolved
        ],
        "countered": list(contested.countered),
        "removed": list(contested.removed),
        "auto_passes": [
            {"seat": record.seat.value, "item": record.item} for record in contested.auto_passes
        ],
        "public": [event_to_data(event) for event in contested.public],
        "private": {
            str(shown.seat.value): [event_to_data(event) for event in shown.events]
            for shown in contested.private
        },
    }


def _payment_to_data(paid: Payment) -> dict[str, object]:
    return {
        "cost": paid.cost,
        "sources": list(paid.sources),
        "life": paid.life,
        "from_pool": paid.from_pool,
        "surplus": paid.surplus,
    }


# @spec REC-042
def log_entry_to_data(entry: LogEntry, answered: Sequence[bool] | None = None) -> dict[str, object]:
    """A log entry as data; `answered`, when given, says for each reminder whether it was met.
    A contested game's entry adds its seats and its public and private events."""
    contested = {} if entry.contested is None else _contested_entry_to_data(entry.contested)
    return {
        "seq": entry.seq,
        "turn": entry.turn,
        "step": entry.step.value if entry.step else None,
        "tool": entry.tool,
        "arguments": entry.arguments,
        "outcome": entry.outcome,
        "card": entry.card,
        "from": entry.from_zone,
        "delta": entry.delta,
        "choices": entry.choices,
        "paid": _payment_to_data(entry.paid) if entry.paid else None,
        "drawn": list(entry.drawn),
        "steps": [step.value for step in entry.steps],
        "reason": entry.reason,
        "override": entry.override,
        "overridden_checks": list(entry.overridden_checks),
        "expect_mismatches": list(entry.expect_mismatches),
        "reminders": [
            _reminder_to_data(r, answered[i] if answered is not None else None)
            for i, r in enumerate(entry.reminders)
        ],
        "assumptions": list(entry.assumptions),
        "notices": list(entry.notices),
        **contested,
    }


def _contested_snapshot_to_data(contested: ContestedSnapshot) -> dict[str, object]:
    return {
        "seat": contested.seat.value,
        "table_turn": contested.table_turn,
        "round": contested.round,
        "lives": {str(seat.value): life for seat, life in contested.lives},
        "eliminated": [seat.value for seat in contested.eliminated],
        "commander_damage": {
            name: {str(seat.value): damage for seat, damage in dealt}
            for name, dealt in contested.commander_damage
        },
    }


# @spec REC-042, REC-046, REC-047, REC-079
def snapshot_to_data(snapshot: TurnSnapshot) -> dict[str, object]:
    """A snapshot as data. A contested game's leaves out the goldfish damage figures and adds
    its seats, every seat's life and its commander damage to every other seat."""
    data: dict[str, object] = {
        "turn": snapshot.turn,
        "hand": [{"name": c.name, "payable": c.payable} for c in snapshot.hand],
        "battlefield": [
            {"name": p.name, "tapped": p.tapped, "counters": dict(p.counters)}
            for p in snapshot.battlefield
        ],
        "graveyard": list(snapshot.graveyard),
        "lands": snapshot.lands,
        "mana_available": snapshot.mana_available,
        "mana_spent": snapshot.mana_spent,
        "land_drop_made": snapshot.land_drop_made,
        "life": snapshot.life,
        "damage_dealt": snapshot.damage_dealt,
        "commander_damage": {name: list(damage) for name, damage in snapshot.commander_damage},
        "unanswered_reminders": [
            {"card": r.card, "step": r.step.value}
            | ({} if r.seat is None else {"seat": r.seat.value})
            for r in snapshot.unanswered_reminders
        ],
    }
    if snapshot.contested is not None:
        del data["damage_dealt"]
        data.update(_contested_snapshot_to_data(snapshot.contested))
    return data


def call_record_to_data(call: CallRecord) -> dict[str, object]:
    """A call record as data; the calling seat's number only when the record names one."""
    seat: dict[str, object] = {} if call.seat is None else {"seat": call.seat.value}
    return {
        "id": call.id,
        "time": call.time.isoformat(),
        "game_id": call.game_id,
        "tool": call.tool,
        "arguments": call.arguments,
        "status": call.status,
        "response": call.response,
        "is_override": call.is_override,
        "change": call.change,
        **seat,
    }
