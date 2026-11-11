"""What the SQLite adapter does beyond the port contracts: rows, restarts and concurrency."""

import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.sqlite import SqliteStores
from mtg_goldfishing.adapters.sqlite.database import DEFAULT_BUSY_TIMEOUT
from mtg_goldfishing.application.ports import GameRecords, StoredGame
from mtg_goldfishing.domain.game.model import GameResult, GameStatus, Result
from tests.support.builders import a_game
from tests.support.card_data import recorded_card
from tests.support.stored import a_call, a_log_entry, a_rich_deck, a_rich_game, a_snapshot

GAME = "gtest000001"
OTHER = "gother0001"


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "goldfishing.db"


@pytest.fixture
def stores(path: Path) -> Iterator[SqliteStores]:
    opened = SqliteStores.open(path)
    yield opened
    opened.database.close()


def _restarted(stores: SqliteStores, path: Path) -> SqliteStores:
    """The stores as a newly started service finds them."""
    stores.database.close()
    return SqliteStores.open(path)


def _query(path: Path, sql: str, *parameters: object) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql, parameters).fetchall()
    finally:
        connection.close()


def _execute(path: Path, sql: str, *parameters: object) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(sql, parameters)
    finally:
        connection.close()


# @spec STOR-005
def test_a_saved_game_is_returned_equal_after_a_restart(stores: SqliteStores, path: Path) -> None:
    game = a_rich_game()
    stores.games.add(game)
    game.tested.life = 22
    stores.games.save(game, version=1)

    restarted = _restarted(stores, path)
    try:
        assert restarted.games.get(GAME) == StoredGame(game, 2)
    finally:
        restarted.database.close()


# @spec STOR-004
def test_a_game_s_row_keeps_copies_of_its_deck_seed_status_and_result(
    stores: SqliteStores, path: Path
) -> None:
    game = a_game().with_seed(42).with_status(GameStatus.ENDED).build().game
    game.result = Result(GameResult.WIN, "")
    stores.games.add(game)

    assert _query(path, "SELECT deck_id, seed, status, result, version FROM games") == [
        ("dtest", 42, "ended", "win", 1)
    ]


# @spec STOR-004
def test_a_game_s_json_document_is_authoritative_over_its_other_columns(
    stores: SqliteStores, path: Path
) -> None:
    game = a_game().build().game
    stores.games.add(game)

    _execute(path, "UPDATE games SET status = 'ended', deck_id = 'dother', seed = 1")

    assert stores.games.get(GAME) == StoredGame(game, 1)


# @spec STOR-006
def test_a_unit_of_work_that_fails_part_way_and_is_rolled_back_saves_none_of_its_writes(
    stores: SqliteStores,
) -> None:
    stores.games.add(a_game().build().game)
    stores.records.add_snapshot(GAME, a_snapshot(3, written_by=1))
    stores.unit_of_work.begin()
    stores.games.save(a_game().with_life(10).build().game, version=1)
    stores.records.append_entry(GAME, a_log_entry(2))
    with pytest.raises(sqlite3.IntegrityError):
        stores.records.add_snapshot(GAME, a_snapshot(3, written_by=2))
    stores.unit_of_work.rollback()

    assert (stores.games.get(GAME), stores.records.read(GAME).entries) == (
        StoredGame(a_game().build().game, 1),
        (),
    )


# @spec STOR-006
def test_writes_in_an_open_unit_of_work_are_not_seen_by_another_connection(
    stores: SqliteStores, path: Path
) -> None:
    stores.games.add(a_game().build().game)
    stores.unit_of_work.begin()
    stores.records.append_entry(GAME, a_log_entry(1))

    seen = _query(path, "SELECT count(*) FROM log_entries")
    stores.unit_of_work.commit()

    assert seen == [(0,)]


# @spec STOR-008
def test_a_save_from_a_second_service_on_the_same_database_at_a_stale_version_fails(
    stores: SqliteStores, path: Path
) -> None:
    stores.games.add(a_game().build().game)
    second = SqliteStores.open(path)
    try:
        stores.games.save(a_game().with_life(30).build().game, version=1)
        refused = second.games.save(a_game().with_life(20).build().game, version=1)
        assert (refused, stores.games.get(GAME)) == (
            False,
            StoredGame(a_game().with_life(30).build().game, 2),
        )
    finally:
        second.database.close()


def _hold_open_unit_of_work_on(
    stores: SqliteStores, opened: threading.Event, release: threading.Event
) -> threading.Thread:
    """Start a thread that saves the game in a unit of work and keeps it open until released."""

    def work() -> None:
        stores.unit_of_work.begin()
        stores.games.save(a_game().with_life(1).build().game, version=1)
        opened.set()
        release.wait(timeout=10)
        stores.unit_of_work.commit()

    thread = threading.Thread(target=work)
    thread.start()
    assert opened.wait(timeout=10)
    return thread


# @spec STOR-009
def test_another_game_can_be_read_while_a_game_is_being_written(stores: SqliteStores) -> None:
    stores.games.add(a_game().build().game)
    stores.games.add(a_rich_game(OTHER))
    release = threading.Event()
    writer = _hold_open_unit_of_work_on(stores, threading.Event(), release)

    try:
        other = stores.games.get(OTHER)
    finally:
        release.set()
        writer.join()

    assert other == StoredGame(a_rich_game(OTHER), 1)


# @spec STOR-009
def test_a_game_being_written_reads_as_it_was_until_its_unit_of_work_commits(
    stores: SqliteStores,
) -> None:
    stores.games.add(a_game().build().game)
    release = threading.Event()
    writer = _hold_open_unit_of_work_on(stores, threading.Event(), release)

    try:
        seen = stores.games.get(GAME)
    finally:
        release.set()
        writer.join()

    assert seen == StoredGame(a_game().build().game, 1)


# @spec STOR-009
def test_a_write_to_another_game_waits_at_most_for_the_open_write_and_is_saved(
    stores: SqliteStores,
) -> None:
    stores.games.add(a_game().build().game)
    stores.games.add(a_rich_game(OTHER))
    release = threading.Event()
    writer = _hold_open_unit_of_work_on(stores, threading.Event(), release)
    threading.Timer(0.2, release.set).start()
    changed = a_rich_game(OTHER)
    changed.tested.life = 5

    saved = stores.games.save(changed, version=1)

    writer.join()

    assert saved is True


# @spec STOR-009
def test_a_write_waits_up_to_a_busy_timeout_of_five_seconds() -> None:
    assert DEFAULT_BUSY_TIMEOUT == 5.0


# @spec STOR-011
def test_nothing_stored_is_deleted_by_later_writes_or_a_restart(
    stores: SqliteStores, path: Path
) -> None:
    game = a_game().build().game
    stores.games.add(game)
    stores.decks.add(a_rich_deck())
    for change in (1, 2, 3):
        game.change = change
        stores.games.save(game, version=change)
        stores.records.append_entry(GAME, a_log_entry(change))
        stores.records.add_call(a_call(GAME, change))
    stores.records.add_snapshot(GAME, a_snapshot(1, written_by=2))

    restarted = _restarted(stores, path)
    try:
        kept = (
            restarted.games.get(GAME),
            restarted.decks.get("drich"),
            restarted.records.read(GAME),
        )
    finally:
        restarted.database.close()

    assert kept == (
        StoredGame(game, 4),
        a_rich_deck(),
        GameRecords(
            tuple(a_log_entry(change) for change in (1, 2, 3)),
            (a_snapshot(1, written_by=2),),
            tuple(replace(a_call(GAME, change), id=change) for change in (1, 2, 3)),
        ),
    )


def test_a_cached_card_is_found_after_a_restart(stores: SqliteStores, path: Path) -> None:
    valki = recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor")
    stores.card_cache.put(valki)

    restarted = _restarted(stores, path)
    try:
        assert restarted.card_cache.get("Tibalt, Cosmic Impostor") == valki
    finally:
        restarted.database.close()


def test_a_cached_card_has_one_row_keyed_by_its_lower_cased_full_name(
    stores: SqliteStores, path: Path
) -> None:
    stores.card_cache.put(recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor"))

    assert _query(path, "SELECT key FROM card_cache") == [
        ("valki, god of lies // tibalt, cosmic impostor",)
    ]


def test_a_cached_card_has_a_lookup_row_for_each_face_name(
    stores: SqliteStores, path: Path
) -> None:
    stores.card_cache.put(recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor"))

    assert sorted(_query(path, "SELECT face_key FROM card_names")) == [
        ("tibalt, cosmic impostor",),
        ("valki, god of lies",),
    ]
