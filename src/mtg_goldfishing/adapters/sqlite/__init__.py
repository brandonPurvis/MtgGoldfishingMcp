"""The persistence ports and the card cache on SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mtg_goldfishing.adapters.sqlite.cards import SqliteCardCache
from mtg_goldfishing.adapters.sqlite.codec import CodecError
from mtg_goldfishing.adapters.sqlite.database import SchemaTooNew, SqliteDatabase
from mtg_goldfishing.adapters.sqlite.repositories import (
    SqliteDeckRepository,
    SqliteGameRepository,
    SqliteRecordStore,
    SqliteUnitOfWork,
)
from mtg_goldfishing.adapters.sqlite.schema import MIGRATIONS, SCHEMA_VERSION


@dataclass(frozen=True)
class SqliteStores:
    """Every SQLite-backed store over one database."""

    database: SqliteDatabase
    games: SqliteGameRepository
    decks: SqliteDeckRepository
    records: SqliteRecordStore
    unit_of_work: SqliteUnitOfWork
    card_cache: SqliteCardCache

    @classmethod
    def open(cls, path: str | Path) -> SqliteStores:
        """Open (creating and migrating as needed) the database at `path`, and its stores."""
        database = SqliteDatabase(path)
        return cls(
            database=database,
            games=SqliteGameRepository(database),
            decks=SqliteDeckRepository(database),
            records=SqliteRecordStore(database),
            unit_of_work=SqliteUnitOfWork(database),
            card_cache=SqliteCardCache(database),
        )


__all__ = [
    "MIGRATIONS",
    "SCHEMA_VERSION",
    "CodecError",
    "SchemaTooNew",
    "SqliteCardCache",
    "SqliteDatabase",
    "SqliteDeckRepository",
    "SqliteGameRepository",
    "SqliteRecordStore",
    "SqliteStores",
    "SqliteUnitOfWork",
]
