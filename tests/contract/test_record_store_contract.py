"""What every RecordStore promises, run against each adapter that implements it."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.application.ports import GameRecords, RecordStore
from mtg_goldfishing.domain.events import EffectRecorded, HiddenCardsDrawn
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.support.stored import (
    a_call,
    a_contested_log_entry,
    a_contested_snapshot,
    a_log_entry,
    a_snapshot,
)
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


# ------------------------------------------------------------------ contested records


# @spec APP-046, STOR-022
def test_a_seat_with_no_call_record_has_no_digest_baseline(records: RecordStore) -> None:
    records.add_call(replace(a_call(GAME, 3), seat=SeatNumber(1)))
    store: Any = records
    assert store.digest_baseline(GAME, SeatNumber(2)) is None


# @spec APP-046, STOR-022
def test_a_seat_s_digest_baseline_is_the_change_on_its_latest_call_record_other_than_get_log(
    records: RecordStore,
) -> None:
    two = SeatNumber(2)
    records.add_call(replace(a_call(GAME, 3), seat=two))
    records.add_call(replace(a_call(GAME, 5, tool="get_state"), seat=two))
    records.add_call(replace(a_call(GAME, 7, tool="get_log"), seat=two))
    records.add_call(replace(a_call(GAME, 8), seat=SeatNumber(1)))
    records.add_call(replace(a_call(OTHER, 9), seat=two))
    store: Any = records
    assert store.digest_baseline(GAME, two) == 5


# @spec APP-046, STOR-022
def test_a_seat_whose_only_call_records_are_get_log_has_no_digest_baseline(
    records: RecordStore,
) -> None:
    records.add_call(replace(a_call(GAME, 7, tool="get_log"), seat=SeatNumber(2)))
    store: Any = records
    assert store.digest_baseline(GAME, SeatNumber(2)) is None


# @spec APP-092, STOR-029
def test_a_second_snapshot_for_a_table_turn_raises_and_the_first_stays(
    records: RecordStore, request: pytest.FixtureRequest
) -> None:
    records.add_snapshot(GAME, a_snapshot(1, written_by=3))
    with pytest.raises(Exception):  # noqa: B017, PT011
        records.add_snapshot(GAME, a_snapshot(1, written_by=4))
    assert records.read(GAME).snapshots == (a_snapshot(1, written_by=3),)


# @spec STOR-028
def test_snapshots_of_two_seats_turns_of_the_same_number_are_kept_by_table_turn(
    records: RecordStore,
) -> None:
    first = a_contested_snapshot(3, table_turn=5, written_by=10)
    second = a_contested_snapshot(3, table_turn=6, written_by=12)
    records.add_snapshot(GAME, first)
    records.add_snapshot(GAME, second)
    assert records.read(GAME).snapshots == (first, second)


# @spec REC-040, REC-067
def test_a_contested_log_entry_with_its_public_events_is_read_back_equal(
    records: RecordStore,
) -> None:
    entry = a_contested_log_entry(
        4,
        seat=2,
        table_turn=3,
        public=(EffectRecorded("Phyrexian Arena"), HiddenCardsDrawn(SeatNumber(2), 1)),
    )
    records.append_entry(GAME, entry)
    assert records.read(GAME).entries == (entry,)
