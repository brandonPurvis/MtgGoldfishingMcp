"""What every RecordStore promises, run against each adapter that implements it."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.application.ports import GameRecords, RecordStore
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.support.stored import a_call, a_log_entry, a_snapshot
from tests.support.stores import STORE_ADAPTER_IDS, STORE_ADAPTERS, OpenStores

GAME = "gtest000001"
OTHER = "gother0001"


# @spec APP-012, APP-013, STOR-001
@pytest.fixture(params=STORE_ADAPTERS, ids=STORE_ADAPTER_IDS)
def records(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[RecordStore]:
    open_stores: OpenStores = request.param
    with open_stores(tmp_path) as stores:
        yield stores.records


def test_a_game_with_no_records_reads_as_empty(records: RecordStore) -> None:
    assert records.read(GAME) == GameRecords((), (), ())


def test_log_entries_are_read_back_equal_in_sequence_order(records: RecordStore) -> None:
    records.append_entry(GAME, a_log_entry(1))
    records.append_entry(GAME, a_log_entry(2, tool="advance"))

    assert records.read(GAME).entries == (a_log_entry(1), a_log_entry(2, tool="advance"))


def test_turn_snapshots_are_read_back_equal_in_turn_order(records: RecordStore) -> None:
    records.add_snapshot(GAME, a_snapshot(1, written_by=3))
    records.add_snapshot(GAME, a_snapshot(2, written_by=6))

    assert records.read(GAME).snapshots == (
        a_snapshot(1, written_by=3),
        a_snapshot(2, written_by=6),
    )


def test_call_records_are_read_back_with_ids_in_the_order_they_were_added(
    records: RecordStore,
) -> None:
    records.add_call(a_call(GAME, 1))
    records.add_call(a_call(GAME, None, tool="play"))

    assert records.read(GAME).calls == (
        replace(a_call(GAME, 1), id=1),
        replace(a_call(GAME, None, tool="play"), id=2),
    )


def test_a_game_reads_only_its_own_records(records: RecordStore) -> None:
    records.append_entry(OTHER, a_log_entry(1))
    records.add_snapshot(OTHER, a_snapshot(1, written_by=1))
    records.add_call(a_call(OTHER, 1))
    records.add_call(a_call(None, None))

    assert records.read(GAME) == GameRecords((), (), ())


# @spec STOR-012
def test_reading_since_a_change_returns_only_entries_with_a_greater_sequence_number(
    records: RecordStore,
) -> None:
    for seq in (1, 2, 3):
        records.append_entry(GAME, a_log_entry(seq))

    assert records.read(GAME, since=1).entries == (a_log_entry(2), a_log_entry(3))


# @spec STOR-012
def test_reading_since_a_change_returns_only_calls_with_a_greater_change_number(
    records: RecordStore,
) -> None:
    for change in (1, 2, None, 3):
        records.add_call(a_call(GAME, change))

    assert [call.change for call in records.read(GAME, since=1).calls] == [2, 3]


# @spec STOR-012
def test_reading_since_a_change_returns_only_snapshots_written_by_later_entries(
    records: RecordStore,
) -> None:
    records.add_snapshot(GAME, a_snapshot(1, written_by=4))
    records.add_snapshot(GAME, a_snapshot(2, written_by=9))

    assert records.read(GAME, since=4).snapshots == (a_snapshot(2, written_by=9),)


def test_reading_without_since_returns_calls_with_no_change_number(records: RecordStore) -> None:
    records.add_call(a_call(GAME, None))

    assert [call.change for call in records.read(GAME).calls] == [None]


def test_changing_the_arguments_of_an_added_call_does_not_change_the_stored_call(
    records: RecordStore,
) -> None:
    call = a_call(GAME, 1)
    records.add_call(call)

    call.arguments["to"] = "end"

    assert records.read(GAME).calls[0].arguments == a_call(GAME, 1).arguments


# @spec REC-052
def test_a_call_record_s_seat_number_is_read_back(records: RecordStore) -> None:
    seated: Any = replace(a_call(GAME, 3), seat=SeatNumber(2))
    records.add_call(seated)
    (read,) = records.read(GAME).calls
    seat: Any = read
    assert seat.seat == SeatNumber(2)
