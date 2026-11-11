"""The get_log export narrowed by its filters: `seat` keeps one seat's records, `tools` the
records of some tools, and every filter given keeps a record only together."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.records.export import export
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot
from tests.support.builders import a_game
from tests.support.stored import (
    a_call,
    a_contested_log_entry,
    a_contested_reminder,
    a_contested_snapshot,
)

S1, S2 = SeatNumber(1), SeatNumber(2)
NOT_YET = pytest.mark.xfail(strict=True, reason="M5: not implemented yet")


def a_contested_game() -> Game:
    builder: Any = a_game().and_an_opposing_seat()
    game: Game = builder.build().game
    return game


def the_new_game_entry() -> LogEntry:
    """The `new_game` entry, which no seat makes."""
    entry: Any = a_contested_log_entry(1, seat=1, table_turn=0, tool="new_game")
    return replace(entry, contested=replace(entry.contested, seat=None, active=None))


def entries() -> list[LogEntry]:
    """new_game, then seat 1's play, seat 2's effect, seat 1's advance and seat 2's play."""
    return [
        the_new_game_entry(),
        a_contested_log_entry(2, seat=1, table_turn=1, tool="play"),
        a_contested_log_entry(3, seat=2, table_turn=1, tool="effect"),
        a_contested_log_entry(4, seat=1, table_turn=1, tool="advance"),
        a_contested_log_entry(5, seat=2, table_turn=2, tool="play"),
    ]


def a_snapshot_of(seat: int, *, table_turn: int, written_by: int) -> TurnSnapshot:
    snapshot: Any = a_contested_snapshot(1, table_turn=table_turn, written_by=written_by)
    return replace(snapshot, contested=replace(snapshot.contested, seat=SeatNumber(seat)))


def snapshots() -> list[TurnSnapshot]:
    """Seat 1's turn, written by change 4, and seat 2's, written by change 6."""
    return [
        a_snapshot_of(1, table_turn=1, written_by=4),
        a_snapshot_of(2, table_turn=2, written_by=6),
    ]


def a_call_of(seat: int | None, change: int, tool: str) -> CallRecord:
    return replace(
        a_call("gtest000001", change, tool=tool),
        seat=None if seat is None else SeatNumber(seat),
    )


def calls() -> list[CallRecord]:
    return [
        a_call_of(None, 1, "new_game"),
        a_call_of(1, 2, "play"),
        a_call_of(2, 3, "effect"),
        a_call_of(2, 3, "get_state"),
        a_call_of(1, 4, "advance"),
    ]


def exported(**filters: Any) -> dict[str, Any]:
    document: dict[str, Any] = export(
        a_contested_game(), entries(), snapshots(), calls(), include_calls=True, **filters
    )
    return document


def seqs(document: dict[str, Any]) -> list[int]:
    return [entry["seq"] for entry in document["entries"]]


# ------------------------------------------------------------------ seat


# @spec REC-089
@NOT_YET
def test_seat_keeps_only_the_log_entries_of_calls_that_seat_made() -> None:
    assert seqs(exported(since=None, seat=S2)) == [3, 5]


# @spec REC-089
@NOT_YET
def test_the_new_game_entry_is_kept_by_no_seat() -> None:
    assert seqs(exported(since=None, seat=S1)) == [2, 4]


# @spec REC-089
@NOT_YET
def test_seat_keeps_only_the_call_records_of_calls_that_seat_made() -> None:
    document = exported(since=None, seat=S2)
    assert [(call["tool"], call["seat"]) for call in document["calls"]] == [
        ("effect", 2),
        ("get_state", 2),
    ]


# @spec REC-089
@NOT_YET
def test_seat_keeps_only_the_snapshots_of_that_seat_s_turns() -> None:
    document = exported(since=None, seat=S1)
    assert [snapshot["seat"] for snapshot in document["snapshots"]] == [1]


# ------------------------------------------------------------------ tools


# @spec REC-090
@NOT_YET
def test_tools_keeps_only_the_log_entries_of_calls_to_those_tools() -> None:
    assert seqs(exported(since=None, tools={"play", "advance"})) == [2, 4, 5]


# @spec REC-090
@NOT_YET
def test_tools_keeps_only_the_call_records_of_calls_to_those_tools() -> None:
    document = exported(since=None, tools={"get_state"})
    assert [call["tool"] for call in document["calls"]] == ["get_state"]


# @spec REC-090
def test_tools_keeps_the_snapshots_the_same_call_without_it_keeps() -> None:
    assert exported(since=None, tools={"effect"})["snapshots"] == exported(since=None)["snapshots"]


# ------------------------------------------------------------------ filters combined


# @spec REC-091
@NOT_YET
def test_since_and_seat_keep_only_the_log_entries_both_keep() -> None:
    assert seqs(exported(since=3, seat=S2)) == [5]


# @spec REC-091
@NOT_YET
def test_since_and_seat_keep_a_snapshot_written_after_since_that_describes_the_seat() -> None:
    document = exported(since=4, seat=S1)
    assert document["snapshots"] == []
    assert [s["seat"] for s in exported(since=4, seat=S2)["snapshots"]] == [2]


# @spec REC-091
@NOT_YET
def test_seat_and_tools_keep_only_the_records_both_keep() -> None:
    document = exported(since=None, seat=S2, tools={"play"})
    assert seqs(document) == [5]
    assert document["calls"] == []


# ------------------------------------------------------------------ kept records are whole


# @spec REC-092
def test_the_game_object_is_whole_under_every_filter() -> None:
    filtered = exported(since=3, seat=S2, tools={"play"})
    assert filtered["game"] == exported(since=None)["game"]


# @spec REC-092
@NOT_YET
def test_a_kept_log_entry_is_exported_as_the_unfiltered_export_gives_it() -> None:
    whole = {entry["seq"]: entry for entry in exported(since=None)["entries"]}
    filtered = exported(since=None, seat=S2, tools={"effect"})["entries"]
    assert filtered == [whole[3]]


# @spec REC-092
def test_a_filtered_export_holds_no_field_the_unfiltered_export_does_not() -> None:
    filtered = exported(since=None, seat=S2, tools={"effect"})
    assert set(filtered) == set(exported(since=None))


# @spec REC-092
@NOT_YET
def test_a_reminder_answered_by_a_call_the_filters_leave_out_reads_as_answered() -> None:
    reminder = a_contested_reminder(1, table_turn=1)
    advanced: Any = replace(
        a_contested_log_entry(2, seat=1, table_turn=1, tool="advance"), reminders=(reminder,)
    )
    answering = a_contested_log_entry(3, seat=1, table_turn=1, source="Phyrexian Arena")
    document = export(
        a_contested_game(), [advanced, answering], [], [], since=None, tools={"advance"}
    )
    kept = document["entries"]
    assert isinstance(kept, list)
    assert [(e["seq"], [r["answered"] for r in e["reminders"]]) for e in kept] == [(2, [True])]
