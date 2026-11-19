"""The SQLite deck repository keeps recently found loaded decks in memory.

Reads of the `decks` table are counted on the calling thread's connection, so each test
can say whether a request reached the database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.sqlite import SqliteDatabase, SqliteDeckRepository, SqliteStores
from mtg_goldfishing.adapters.sqlite.codec import encode
from mtg_goldfishing.domain.deck.model import LoadedDeck
from tests.support.builders import a_deck
from tests.support.stored import a_rich_deck

RICH = "drich"
LIMIT = 64

not_yet_kept = pytest.mark.xfail(
    strict=True, reason="the deck repository does not keep decks in memory yet"
)


@pytest.fixture
def stores(tmp_path: Path) -> Iterator[SqliteStores]:
    stores = SqliteStores.open(tmp_path / "goldfishing.db")
    yield stores
    stores.database.close()


@contextmanager
def counting_deck_reads(database: SqliteDatabase) -> Iterator[list[str]]:
    """The statements that read the `decks` table on this thread while the block runs."""
    reads: list[str] = []

    def seen(statement: str) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "FROM decks" in statement:
            reads.append(statement)

    connection = database.connection()
    connection.set_trace_callback(seen)
    try:
        yield reads
    finally:
        connection.set_trace_callback(None)


def numbered_decks(count: int) -> list[LoadedDeck]:
    deck = a_deck("Forest", "Sol Ring")
    return [replace(deck, deck_id=f"d{number:02}") for number in range(count)]


def stored(stores: SqliteStores, decks: list[LoadedDeck]) -> list[str]:
    """Add the decks through a second repository, so the one under test has kept none."""
    adder = SqliteDeckRepository(stores.database)
    for deck in decks:
        adder.add(deck)
    return [deck.deck_id for deck in decks]


# ------------------------------------------------------------------- found decks are kept


# @spec STOR-053, STOR-054
@not_yet_kept
def test_a_deck_found_once_is_answered_from_memory_afterwards(stores: SqliteStores) -> None:
    stored(stores, [a_rich_deck()])
    stores.decks.get(RICH)

    with counting_deck_reads(stores.database) as reads:
        found = stores.decks.get(RICH)

    assert (found, reads) == (a_rich_deck(), [])


# @spec STOR-054
@not_yet_kept
def test_a_kept_deck_is_answered_from_memory_inside_a_unit_of_work(stores: SqliteStores) -> None:
    stored(stores, [a_rich_deck()])
    stores.decks.get(RICH)
    stores.unit_of_work.begin()

    with counting_deck_reads(stores.database) as reads:
        found = stores.decks.get(RICH)
    stores.unit_of_work.rollback()

    assert (found, reads) == (a_rich_deck(), [])


# @spec STOR-053
def test_a_deck_read_while_a_transaction_is_open_is_not_kept(stores: SqliteStores) -> None:
    stored(stores, [a_rich_deck()])
    stores.unit_of_work.begin()
    stores.decks.get(RICH)
    stores.unit_of_work.commit()

    with counting_deck_reads(stores.database) as reads:
        stores.decks.get(RICH)

    assert len(reads) == 1


# @spec STOR-064
def test_each_repository_keeps_its_own_decks(stores: SqliteStores) -> None:
    stored(stores, [a_rich_deck()])
    stores.decks.get(RICH)
    other = SqliteDeckRepository(stores.database)

    with counting_deck_reads(stores.database) as reads:
        other.get(RICH)

    assert len(reads) == 1


# ------------------------------------------------------------------- at most 64, by recency


# @spec STOR-055
def test_keeping_one_deck_past_the_limit_forgets_the_least_recently_asked_for(
    stores: SqliteStores,
) -> None:
    ids = stored(stores, numbered_decks(LIMIT + 1))
    for deck_id in ids:
        stores.decks.get(deck_id)

    with counting_deck_reads(stores.database) as reads:
        stores.decks.get(ids[0])

    assert len(reads) == 1


# @spec STOR-055
@not_yet_kept
def test_the_other_decks_stay_kept_when_one_is_forgotten(stores: SqliteStores) -> None:
    ids = stored(stores, numbered_decks(LIMIT + 1))
    for deck_id in ids:
        stores.decks.get(deck_id)

    with counting_deck_reads(stores.database) as reads:
        for deck_id in ids[1:]:
            stores.decks.get(deck_id)

    assert reads == []


# @spec STOR-061
@not_yet_kept
def test_a_deck_answered_from_memory_becomes_the_most_recently_asked_for(
    stores: SqliteStores,
) -> None:
    ids = stored(stores, numbered_decks(LIMIT + 1))
    for deck_id in ids[:LIMIT]:
        stores.decks.get(deck_id)
    stores.decks.get(ids[0])
    stores.decks.get(ids[LIMIT])

    with counting_deck_reads(stores.database) as reads:
        stores.decks.get(ids[0])

    assert reads == []


# @spec STOR-053
@not_yet_kept
def test_a_deck_just_kept_is_the_most_recently_asked_for(stores: SqliteStores) -> None:
    ids = stored(stores, numbered_decks(LIMIT + 1))
    for deck_id in ids:
        stores.decks.get(deck_id)

    with counting_deck_reads(stores.database) as reads:
        stores.decks.get(ids[LIMIT])

    assert reads == []


# ------------------------------------------------------------------------- misses and adds


# @spec STOR-056
def test_a_deck_id_that_names_no_deck_reaches_the_database_every_time(
    stores: SqliteStores,
) -> None:
    with counting_deck_reads(stores.database) as reads:
        stores.decks.get("dnothing")
        stores.decks.get("dnothing")

    assert len(reads) == 2


# @spec STOR-056
def test_a_deck_added_after_a_miss_is_found(stores: SqliteStores) -> None:
    stores.decks.get(RICH)
    stored(stores, [a_rich_deck()])

    assert stores.decks.get(RICH) == a_rich_deck()


# @spec STOR-057
def test_adding_a_deck_returns_what_the_database_holds_not_a_kept_copy(
    stores: SqliteStores,
) -> None:
    stored(stores, [a_rich_deck()])
    stores.decks.get(RICH)
    held = replace(a_deck("Island"), deck_id=RICH)
    with stores.database.writing() as connection:
        connection.execute(
            "UPDATE decks SET deck = ? WHERE deck_id = ?", (encode(held, LoadedDeck), RICH)
        )

    assert stores.decks.add(a_rich_deck()) == held


# @spec STOR-065
def test_an_added_deck_is_not_kept_in_memory(stores: SqliteStores) -> None:
    stores.decks.add(a_rich_deck())

    with counting_deck_reads(stores.database) as reads:
        stores.decks.get(RICH)

    assert len(reads) == 1


# @spec STOR-058
def test_a_deck_added_in_a_unit_of_work_that_is_rolled_back_is_not_found(
    stores: SqliteStores,
) -> None:
    stores.unit_of_work.begin()
    stores.decks.add(a_rich_deck())
    stores.decks.get(RICH)
    stores.unit_of_work.rollback()

    assert stores.decks.get(RICH) is None


# ------------------------------------------------------------------------------- closing


# @spec STOR-059
def test_a_closed_database_raises_even_for_a_kept_deck(stores: SqliteStores) -> None:
    stored(stores, [a_rich_deck()])
    stores.decks.get(RICH)
    stores.database.close()

    with pytest.raises(sqlite3.ProgrammingError):
        stores.decks.get(RICH)
