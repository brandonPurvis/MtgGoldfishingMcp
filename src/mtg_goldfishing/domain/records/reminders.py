"""Judging reminders answered or unanswered from the log."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mtg_goldfishing.domain.records.model import LogEntry, ReminderRecord


@dataclass(frozen=True)
class JudgedReminder:
    """A reminder, the sequence number of the entry that issued it, and whether it was met."""

    seq: int
    reminder: ReminderRecord
    answered: bool


# @spec REC-010
def names_reminded_permanent(source: str, *, card_name: str, face: str, instance_id: str) -> bool:
    """Whether an `effect`'s source names a reminded permanent.

    It does when, ignoring case, it equals the permanent's card name, the name of its face
    in play when it was reminded, or its instance id. The permanent need not still be on
    the battlefield. This is the one rule: the game marks reminders answered by it, and the
    log is judged by it.
    """
    wanted = source.strip().casefold()
    return any(name and name.casefold() == wanted for name in (card_name, face, instance_id))


def _effect_source(entry: LogEntry) -> str | None:
    if entry.tool != "effect":
        return None
    source = entry.arguments.get("source")
    return source if isinstance(source, str) else entry.card


def _answers(entry: LogEntry, issued_by: LogEntry, reminder: ReminderRecord) -> bool:
    source = _effect_source(entry)
    return (
        source is not None
        and entry.seq > issued_by.seq
        and entry.turn == reminder.turn
        and names_reminded_permanent(
            source,
            card_name=reminder.card_name,
            face=reminder.card,
            instance_id=reminder.instance_id,
        )
    )


# @spec REC-009, REC-010
def judge_reminders(entries: Sequence[LogEntry]) -> list[JudgedReminder]:
    """Every reminder recorded in the entries, in order, judged answered or unanswered.

    A reminder is answered when a later accepted `effect` in the same turn names the
    reminded permanent as its source. One such effect answers every reminder it names.
    """
    return [
        JudgedReminder(
            entry.seq,
            reminder,
            any(_answers(later, entry, reminder) for later in entries),
        )
        for entry in entries
        for reminder in entry.reminders
    ]
