"""The SQLite game repository keeps the games it most recently read or wrote in memory.

Reads of a game's stored document (the `state` column of `games`) are counted on the
calling thread's connection, so a test can say whether a request decoded the game. A
second `SqliteStores` opened on the same file stands for another process sharing the
database. A few tests move a stored row from outside with SQL, as only a change made to the
database from outside the service could.
"""

from __future__ import annotations

import random
import re
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.sqlite import SqliteDatabase, SqliteGameRepository, SqliteStores
from mtg_goldfishing.adapters.sqlite.codec import encode
from mtg_goldfishing.application.ports import StoredGame
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatId
from tests.support.builders import a_game

LIMIT = 64

DOCUMENT_READ = re.compile(
    r"\s*SELECT\b(?P<columns>.*?)\bFROM\s+games\b", re.IGNORECASE | re.DOTALL
)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "goldfishing.db"


@pytest.fixture
def stores(path: Path) -> Iterator[SqliteStores]:
    stores = SqliteStores.open(path)
    yield stores
    stores.database.close()


@pytest.fixture
def elsewhere(path: Path, stores: SqliteStores) -> Iterator[SqliteStores]:
    """Another process's stores on the same database file."""
    other = SqliteStores.open(path)
    yield other
    other.database.close()


@contextmanager
def counting_document_reads(database: SqliteDatabase) -> Iterator[list[str]]:
    """The statements that read a game's stored document on this thread while the block runs."""
    reads: list[str] = []

    def seen(statement: str) -> None:
        found = DOCUMENT_READ.match(statement)
        if found and re.search(r"\bstate\b", found.group("columns"), re.IGNORECASE):
            reads.append(statement)

    connection = database.connection()
    connection.set_trace_callback(seen)
    try:
        yield reads
    finally:
        connection.set_trace_callback(None)


def a_numbered_game(number: int) -> Game:
    game = a_game().build().game
    game.game_id = f"gmemory{number:04}"
    game.tested.seat_id = SeatId(game.game_id)
    return game


def changed(game: Game, change: int) -> Game:
    """A copy of the game with its change number and the tested seat's life moved on."""
    copy = game.copy()
    copy.change = change
    copy.tested.life = 40 - change
    return copy


def stored_elsewhere(stores: SqliteStores, games: list[Game]) -> list[str]:
    """Add the games through a second repository, so the one under test has kept none."""
    adder = SqliteGameRepository(stores.database)
    for game in games:
        adder.add(game)
    return [game.game_id for game in games]


def read_all(stores: SqliteStores, ids: list[str]) -> None:
    for game_id in ids:
        stores.games.get(game_id)


def set_stored_row(database: SqliteDatabase, game: Game, version: int) -> None:
    """Rewrite a stored game's document and version counter from outside the repository."""
    with database.writing() as connection:
        connection.execute(
            "UPDATE games SET state = ?, version = ? WHERE game_id = ?",
            (encode(game, Game), version, game.game_id),
        )


def in_another_thread[T](call: Callable[[], T]) -> T:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(call).result()


# ------------------------------------------------------------- each repository's own memory


# @spec STOR-066
def test_a_new_repository_keeps_no_game(stores: SqliteStores) -> None:
    (game_id,) = stored_elsewhere(stores, [a_numbered_game(1)])
    fresh = SqliteGameRepository(stores.database)

    with counting_document_reads(stores.database) as reads:
        fresh.get(game_id)

    assert len(reads) == 1


# @spec STOR-066
def test_a_game_one_repository_keeps_is_not_shared_with_another(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    other = SqliteGameRepository(stores.database)

    found = other.get(game.game_id)

    assert found is not None
    assert found.game is not game


# ------------------------------------------------------------------ written games are kept


# @spec STOR-067
def test_a_game_added_in_a_unit_of_work_is_kept_when_it_commits(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.unit_of_work.begin()
    stores.games.add(game)
    stores.unit_of_work.commit()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is game, found.version) == (True, 1)


# @spec STOR-067
def test_a_game_saved_in_a_unit_of_work_is_kept_at_the_version_the_save_wrote(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    saved = changed(game, 1)
    stores.unit_of_work.begin()
    stores.games.save(saved, version=1)
    stores.unit_of_work.commit()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is saved, found.version) == (True, 2)


# @spec STOR-067
def test_the_last_write_of_a_game_in_a_unit_of_work_is_the_one_kept(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    first, second = changed(game, 1), changed(game, 2)
    stores.unit_of_work.begin()
    stores.games.add(game)
    stores.games.save(first, version=1)
    stores.games.save(second, version=2)
    stores.unit_of_work.commit()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is second, found.version) == (True, 3)


# @spec STOR-067, STOR-069
def test_a_failed_save_after_a_successful_one_leaves_the_successful_one_kept(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    saved, stale = changed(game, 1), changed(game, 2)
    stores.unit_of_work.begin()
    stores.games.save(saved, version=1)
    stores.games.save(stale, version=1)
    stores.unit_of_work.commit()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert found.game is saved


# @spec STOR-067
def test_a_game_written_becomes_the_most_recently_asked_for(stores: SqliteStores) -> None:
    ids = stored_elsewhere(stores, [a_numbered_game(n) for n in range(LIMIT + 1)])
    read_all(stores, ids[:LIMIT])
    first = stores.games.get(ids[0])
    assert first is not None
    stores.games.save(changed(first.game, 1), version=first.version)
    stores.games.get(ids[LIMIT])

    with counting_document_reads(stores.database) as reads:
        stores.games.get(ids[0])

    assert reads == []


# @spec STOR-082
def test_a_game_added_outside_a_unit_of_work_is_kept_once_the_add_returns(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is game, found.version) == (True, 1)


# @spec STOR-082
def test_a_game_saved_outside_a_unit_of_work_is_kept_once_the_save_returns(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    saved = changed(game, 1)
    stores.games.save(saved, version=1)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is saved, found.version) == (True, 2)


# @spec STOR-072
def test_a_written_game_is_kept_by_the_time_its_commit_returns(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.unit_of_work.begin()
    stores.games.add(game)
    stores.unit_of_work.commit()

    found = in_another_thread(lambda: stores.games.get(game.game_id))

    assert found is not None
    assert found.game is game


# ------------------------------------------------------- writes that do not commit keep nothing


# @spec STOR-069
def test_a_save_refused_for_a_stale_version_keeps_nothing(
    stores: SqliteStores, elsewhere: SqliteStores
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    theirs = changed(game, 7)
    elsewhere.games.save(theirs, version=1)

    stores.games.save(changed(game, 1), version=1)

    assert stores.games.get(game.game_id) == StoredGame(theirs, 2)


# @spec STOR-070
def test_a_game_added_in_a_unit_of_work_that_is_rolled_back_is_not_found(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.unit_of_work.begin()
    stores.games.add(game)
    stores.unit_of_work.rollback()

    assert stores.games.get(game.game_id) is None


# @spec STOR-070
def test_a_rolled_back_save_leaves_the_game_kept_before_it(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.unit_of_work.begin()
    stores.games.save(changed(game, 1), version=1)
    stores.unit_of_work.rollback()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is game, found.version) == (True, 1)


# @spec STOR-070
def test_a_save_whose_commit_fails_leaves_the_game_kept_before_it(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.unit_of_work.begin()
    stores.games.save(changed(game, 1), version=1)
    connection = stores.database.connection()
    connection.execute("PRAGMA defer_foreign_keys = ON")
    connection.execute(
        "INSERT INTO seats (seat_id, game_id, seat_number, deck_id, tested)"
        " VALUES ('sorphan', 'gnothing00', 1, 'dnothing', 0)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        stores.unit_of_work.commit()
    stores.unit_of_work.rollback()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is game, found.version) == (True, 1)


def _ended_by_sqlite(stores: SqliteStores, game_id: str) -> None:
    """Make SQLite roll back the open transaction on its own, through a constraint conflict
    whose resolution is ROLLBACK."""
    with pytest.raises(sqlite3.IntegrityError):
        stores.database.connection().execute(
            "INSERT OR ROLLBACK INTO games SELECT * FROM games WHERE game_id = ?", (game_id,)
        )
    assert not stores.database.connection().in_transaction


# @spec STOR-070
def test_a_save_in_a_transaction_sqlite_ends_on_its_own_leaves_the_game_kept_before_it(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.unit_of_work.begin()
    stores.games.save(changed(game, 1), version=1)
    _ended_by_sqlite(stores, game.game_id)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert (found.game is game, found.version) == (True, 1)


# @spec STOR-071
def test_a_later_commit_does_not_keep_a_write_whose_transaction_sqlite_ended(
    stores: SqliteStores, elsewhere: SqliteStores
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.unit_of_work.begin()
    stores.games.save(changed(game, 1), version=1)
    _ended_by_sqlite(stores, game.game_id)
    stores.games.add(a_numbered_game(2))
    theirs = changed(game, 7)
    elsewhere.games.save(theirs, version=1)

    assert stores.games.get(game.game_id) == StoredGame(theirs, 2)


# ------------------------------------------------------------------- answering from memory


# @spec STOR-073
def test_a_kept_game_is_answered_without_reading_its_document(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)

    with counting_document_reads(stores.database) as reads:
        stores.games.get(game.game_id)

    assert reads == []


# @spec STOR-073
def test_a_kept_game_is_answered_without_reading_its_document_inside_a_unit_of_work(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.unit_of_work.begin()

    with counting_document_reads(stores.database) as reads:
        stores.games.get(game.game_id)
    stores.unit_of_work.rollback()

    assert reads == []


# @spec STOR-073
def test_a_kept_game_is_returned_itself_to_every_call_that_asks_for_it(
    stores: SqliteStores,
) -> None:
    (game_id,) = stored_elsewhere(stores, [a_numbered_game(1)])
    first = stores.games.get(game_id)

    second = stores.games.get(game_id)

    assert first is not None
    assert second is not None
    assert second.game is first.game


# @spec STOR-073
def test_a_kept_game_is_answered_while_its_stored_version_is_unchanged(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    set_stored_row(stores.database, changed(game, 5), version=1)

    assert stores.games.get(game.game_id) == StoredGame(game, 1)


# @spec STOR-074
def test_a_game_not_kept_is_read_with_its_version_in_one_statement(stores: SqliteStores) -> None:
    (game_id,) = stored_elsewhere(stores, [a_numbered_game(1)])

    with counting_document_reads(stores.database) as reads:
        stores.games.get(game_id)

    assert [bool(re.search(r"\bversion\b", read, re.IGNORECASE)) for read in reads] == [True]


# @spec STOR-074
def test_a_kept_game_whose_stored_version_moved_on_is_read_again(
    stores: SqliteStores, elsewhere: SqliteStores
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    theirs = changed(game, 7)
    elsewhere.games.save(theirs, version=1)

    assert stores.games.get(game.game_id) == StoredGame(theirs, 2)


# ------------------------------------------------------------------------ games read are kept


# @spec STOR-075
def test_a_game_read_while_no_transaction_is_open_is_kept(stores: SqliteStores) -> None:
    (game_id,) = stored_elsewhere(stores, [a_numbered_game(1)])
    stores.games.get(game_id)

    with counting_document_reads(stores.database) as reads:
        stores.games.get(game_id)

    assert reads == []


# @spec STOR-075
def test_a_game_read_again_after_its_version_moved_on_is_kept_at_the_version_read(
    stores: SqliteStores, elsewhere: SqliteStores
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    elsewhere.games.save(changed(game, 7), version=1)
    stores.games.get(game.game_id)

    with counting_document_reads(stores.database) as reads:
        found = stores.games.get(game.game_id)

    assert (reads, found and found.version) == ([], 2)


# @spec STOR-075
def test_a_game_just_read_is_the_most_recently_asked_for(stores: SqliteStores) -> None:
    ids = stored_elsewhere(stores, [a_numbered_game(n) for n in range(LIMIT + 1)])
    read_all(stores, ids)

    with counting_document_reads(stores.database) as reads:
        stores.games.get(ids[LIMIT])

    assert reads == []


# @spec STOR-076
def test_a_game_read_inside_a_unit_of_work_is_not_kept(stores: SqliteStores) -> None:
    (game_id,) = stored_elsewhere(stores, [a_numbered_game(1)])
    stores.unit_of_work.begin()
    stores.games.get(game_id)
    stores.unit_of_work.commit()

    with counting_document_reads(stores.database) as reads:
        stores.games.get(game_id)

    assert len(reads) == 1


# @spec STOR-076
def test_an_uncommitted_save_read_back_in_its_unit_of_work_is_not_kept(
    stores: SqliteStores, elsewhere: SqliteStores
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.unit_of_work.begin()
    stores.games.save(changed(game, 1), version=1)
    stores.games.get(game.game_id)
    stores.unit_of_work.rollback()
    theirs = changed(game, 7)
    elsewhere.games.save(theirs, version=1)

    assert stores.games.get(game.game_id) == StoredGame(theirs, 2)


# ------------------------------------------------------------------- at most 64, by recency


# @spec STOR-077
def test_a_kept_game_returned_becomes_the_most_recently_asked_for(stores: SqliteStores) -> None:
    ids = stored_elsewhere(stores, [a_numbered_game(n) for n in range(LIMIT + 1)])
    read_all(stores, ids[:LIMIT])
    stores.games.get(ids[0])
    stores.games.get(ids[LIMIT])

    with counting_document_reads(stores.database) as reads:
        stores.games.get(ids[0])

    assert reads == []


# @spec STOR-078
def test_keeping_one_game_past_the_limit_forgets_the_least_recently_asked_for(
    stores: SqliteStores,
) -> None:
    ids = stored_elsewhere(stores, [a_numbered_game(n) for n in range(LIMIT + 1)])
    read_all(stores, ids)

    with counting_document_reads(stores.database) as reads:
        stores.games.get(ids[0])

    assert len(reads) == 1


# @spec STOR-078
def test_the_other_games_stay_kept_when_one_is_forgotten(stores: SqliteStores) -> None:
    ids = stored_elsewhere(stores, [a_numbered_game(n) for n in range(LIMIT + 1)])
    read_all(stores, ids)

    with counting_document_reads(stores.database) as reads:
        read_all(stores, ids[1:])

    assert reads == []


# ------------------------------------------------------------- a stored row that has gone


def _delete_stored_row(database: SqliteDatabase, game_id: str) -> None:
    with database.writing() as connection:
        connection.execute("DELETE FROM seats WHERE game_id = ?", (game_id,))
        connection.execute("DELETE FROM games WHERE game_id = ?", (game_id,))


# @spec STOR-079
def test_a_kept_game_whose_row_has_gone_is_reported_as_no_game(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    _delete_stored_row(stores.database, game.game_id)

    assert stores.games.get(game.game_id) is None


# @spec STOR-081
def test_a_kept_game_whose_row_has_gone_is_forgotten(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    _delete_stored_row(stores.database, game.game_id)
    stores.games.get(game.game_id)
    replacement = changed(game, 5)
    stored_elsewhere(stores, [replacement])

    assert stores.games.get(game.game_id) == StoredGame(replacement, 1)


# ------------------------------------------------------------------------------- closing


# @spec STOR-080
def test_a_closed_database_raises_even_for_a_kept_game(stores: SqliteStores) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    stores.games.get(game.game_id)
    stores.database.close()

    with pytest.raises(sqlite3.ProgrammingError):
        stores.games.get(game.game_id)


# @spec STOR-080
def test_a_closed_database_raises_for_a_game_not_kept(stores: SqliteStores) -> None:
    stores.database.close()

    with pytest.raises(sqlite3.ProgrammingError):
        stores.games.get("gnothing00")


# ----------------------------------------------------------------- never an earlier version


# @spec STOR-083
def test_a_read_of_an_earlier_version_does_not_replace_the_game_kept(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    second = changed(game, 1)
    stores.games.save(second, version=1)
    third = changed(game, 2)
    stores.games.save(third, version=2)
    set_stored_row(stores.database, second, version=2)
    stores.games.get(game.game_id)
    set_stored_row(stores.database, changed(game, 9), version=3)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert found.game is third


# @spec STOR-083
def test_a_commit_of_an_earlier_version_does_not_replace_the_game_kept(
    stores: SqliteStores,
) -> None:
    game = a_numbered_game(1)
    stores.games.add(game)
    second = changed(game, 1)
    stores.games.save(second, version=1)
    third = changed(game, 2)
    stores.games.save(third, version=2)
    set_stored_row(stores.database, game, version=1)
    stores.games.save(changed(game, 5), version=1)
    set_stored_row(stores.database, changed(game, 9), version=3)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert found.game is third


# ------------------------------------------------------------------------------- threads


# @spec STOR-084
def test_threads_reading_and_writing_games_at_once_each_see_the_stored_games(
    stores: SqliteStores,
) -> None:
    games = [a_numbered_game(n) for n in range(LIMIT + 16)]
    ids = stored_elsewhere(stores, games)
    expected = {game.game_id: StoredGame(game, 1) for game in games}
    writers = ids[:4]

    def write(game_id: str) -> None:
        for version in range(1, 6):
            found = stores.games.get(game_id)
            assert found is not None
            assert stores.games.save(changed(found.game, version), version=version)

    def read(seed: int) -> list[str]:
        order = [game_id for game_id in ids if game_id not in writers] * 3
        random.Random(seed).shuffle(order)
        return [game_id for game_id in order if stores.games.get(game_id) != expected[game_id]]

    with ThreadPoolExecutor(max_workers=8) as pool:
        written = [pool.submit(write, game_id) for game_id in writers]
        mismatched = [pool.submit(read, seed) for seed in range(4)]
        for done in written:
            done.result()
        wrong = [game_id for found in mismatched for game_id in found.result()]

    assert wrong == []
