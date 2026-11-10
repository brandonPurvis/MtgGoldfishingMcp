"""The `get_log` export: a game's records as JSON-ready data.

The export carries the records' own fields and nothing computed from them.
"""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import (
    CallRecord,
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


def game_to_data(game: Game) -> dict[str, object]:
    result = game.result
    return {
        "game_id": game.game_id,
        "deck_id": game.deck_id,
        "seed": game.seed,
        "turn_limit": game.turn_limit,
        "draw_first_turn": game.draw_first_turn,
        "status": game.status.value,
        "turn": game.turn,
        "change": game.change,
        "result": {"outcome": result.outcome.value, "notes": result.notes} if result else None,
    }


def _reminder_to_data(reminder: ReminderRecord, answered: bool | None) -> dict[str, object]:
    data: dict[str, object] = {
        "card": reminder.card,
        "step": reminder.step.value,
        "instance_id": reminder.instance_id,
    }
    if answered is not None:
        data["answered"] = answered
    return data


def _payment_to_data(paid: Payment) -> dict[str, object]:
    return {
        "cost": paid.cost,
        "sources": list(paid.sources),
        "life": paid.life,
        "from_pool": paid.from_pool,
        "surplus": paid.surplus,
    }


def log_entry_to_data(entry: LogEntry, answered: Sequence[bool] | None = None) -> dict[str, object]:
    """A log entry as data; `answered`, when given, says for each reminder whether it was met."""
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
    }


def snapshot_to_data(snapshot: TurnSnapshot) -> dict[str, object]:
    return {
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
            {"card": r.card, "step": r.step.value} for r in snapshot.unanswered_reminders
        ],
    }


def call_record_to_data(call: CallRecord) -> dict[str, object]:
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
    }
