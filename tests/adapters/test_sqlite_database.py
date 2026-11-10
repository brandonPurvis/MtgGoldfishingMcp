"""The SQLite database file: where it lives, how it is opened, and its schema version."""

import sqlite3
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.sqlite import (
    MIGRATIONS,
    SCHEMA_VERSION,
    SchemaTooNew,
    SqliteDatabase,
)


def _query(path: Path, sql: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def _open_and_close(path: Path, migrations: tuple[str, ...] = MIGRATIONS) -> None:
    SqliteDatabase(path, migrations=migrations).close()


def _tables(path: Path) -> set[str]:
    rows = _query(path, "SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(name) for (name,) in rows}


# @spec STOR-003
def test_the_database_file_and_its_directory_are_created_on_first_start(tmp_path: Path) -> None:
    path = tmp_path / "not" / "yet" / "there" / "goldfishing.db"

    _open_and_close(path)

    assert path.is_file()


# @spec STOR-002
def test_the_database_is_opened_in_wal_mode(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"

    _open_and_close(path)

    assert _query(path, "PRAGMA journal_mode") == [("wal",)]


def test_a_new_database_has_every_table_of_the_design(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"

    _open_and_close(path)

    assert {
        "games",
        "decks",
        "log_entries",
        "snapshots",
        "calls",
        "card_cache",
        "card_names",
        "schema_version",
    } <= _tables(path)


def test_a_new_database_records_the_current_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"

    _open_and_close(path)

    assert _query(path, "SELECT version FROM schema_version") == [(SCHEMA_VERSION,)]


# @spec STOR-013
def test_starting_against_an_older_schema_applies_the_forward_migrations(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path)
    later = (*MIGRATIONS, "CREATE TABLE added_later (id INTEGER PRIMARY KEY)")

    _open_and_close(path, later)

    assert "added_later" in _tables(path)


# @spec STOR-013
def test_a_migrated_database_records_the_version_it_reached(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path)
    later = (*MIGRATIONS, "CREATE TABLE added_later (id INTEGER PRIMARY KEY)")

    _open_and_close(path, later)

    assert _query(path, "SELECT version FROM schema_version") == [(SCHEMA_VERSION + 1,)]


# @spec STOR-013
def test_migrating_keeps_the_data_already_stored(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO decks (deck_id, deck, created_at) VALUES ('d1', '{}', '')")
    connection.close()
    later = (*MIGRATIONS, "ALTER TABLE decks ADD COLUMN note TEXT")

    _open_and_close(path, later)

    assert _query(path, "SELECT deck_id, note FROM decks") == [("d1", None)]


# @spec STOR-013
def test_a_migration_that_fails_leaves_the_database_at_its_previous_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path)
    broken = (*MIGRATIONS, "CREATE TABLE half_done (id INTEGER); SELECT * FROM no_such_table")

    with pytest.raises(sqlite3.OperationalError):
        _open_and_close(path, broken)

    assert (_query(path, "SELECT version FROM schema_version"), "half_done" in _tables(path)) == (
        [(SCHEMA_VERSION,)],
        False,
    )


# @spec STOR-014
def test_starting_against_a_newer_schema_refuses_naming_both_versions(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path, (*MIGRATIONS, "CREATE TABLE from_the_future (id INTEGER)"))

    with pytest.raises(SchemaTooNew) as refused:
        _open_and_close(path)

    assert (refused.value.found, refused.value.supported) == (SCHEMA_VERSION + 1, SCHEMA_VERSION)


# @spec STOR-014
def test_the_refusal_message_names_both_versions(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path, (*MIGRATIONS, "CREATE TABLE from_the_future (id INTEGER)"))

    with pytest.raises(SchemaTooNew, match=rf"\b{SCHEMA_VERSION + 1}\b.*\b{SCHEMA_VERSION}\b"):
        _open_and_close(path)


# @spec STOR-014
def test_starting_against_a_newer_schema_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "goldfishing.db"
    _open_and_close(path, (*MIGRATIONS, "CREATE TABLE from_the_future (id INTEGER)"))
    before = path.read_bytes()

    with pytest.raises(SchemaTooNew):
        _open_and_close(path)

    assert path.read_bytes() == before
