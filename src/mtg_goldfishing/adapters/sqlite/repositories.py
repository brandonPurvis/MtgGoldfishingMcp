"""The persistence ports on SQLite: games, loaded decks, records and the unit of work.

Every stored domain value is one JSON document written by the codec, and that document is
authoritative. The other columns of a row are copies, kept to find rows by.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.adapters.sqlite.database import SqliteDatabase
from mtg_goldfishing.application.ports import GameRecords, StoredGame
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot

Now = Callable[[], datetime]
"""Supplies the time a row is written, for its timestamp columns."""


def utc_now() -> datetime:
    return datetime.now(UTC)


# @spec STOR-001, STOR-004, STOR-005, STOR-008
class SqliteGameRepository:
    """Each game is one row: its state as one JSON document and a version counter."""

    def __init__(self, database: SqliteDatabase, *, now: Now = utc_now) -> None:
        self._database = database
        self._now = now

    def get(self, game_id: str) -> StoredGame | None:
        row = (
            self._database.connection()
            .execute("SELECT state, version FROM games WHERE game_id = ?", (game_id,))
            .fetchone()
        )
        if row is None:
            return None
        state, version = row
        return StoredGame(decode(state, Game), int(version))

    def add(self, game: Game) -> None:
        now = self._now().isoformat()
        with self._database.writing() as connection:
            connection.execute(
                "INSERT INTO games (game_id, deck_id, seed, status, result, state, version,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (*_copied_columns(game), now, now),
            )

    def save(self, game: Game, *, version: int) -> bool:
        """Save only if the stored version is still `version`, in one compare-and-set write."""
        game_id, deck_id, seed, status, result, state = _copied_columns(game)
        with self._database.writing() as connection:
            cursor = connection.execute(
                "UPDATE games SET deck_id = ?, seed = ?, status = ?, result = ?, state = ?,"
                " version = version + 1, updated_at = ? WHERE game_id = ? AND version = ?",
                (deck_id, seed, status, result, state, self._now().isoformat(), game_id, version),
            )
            return cursor.rowcount == 1


def _copied_columns(game: Game) -> tuple[str, str, int, str, str | None, str]:
    result = game.result.outcome.value if game.result else None
    return (
        game.game_id,
        game.deck_id,
        game.seed,
        game.status.value,
        result,
        encode(game, Game),
    )


# @spec STOR-001, STOR-010
class SqliteDeckRepository:
    """Each loaded deck is one row, written once and never replaced."""

    def __init__(self, database: SqliteDatabase, *, now: Now = utc_now) -> None:
        self._database = database
        self._now = now

    def get(self, deck_id: str) -> LoadedDeck | None:
        row = (
            self._database.connection()
            .execute("SELECT deck FROM decks WHERE deck_id = ?", (deck_id,))
            .fetchone()
        )
        return None if row is None else decode(row[0], LoadedDeck)

    def add(self, deck: LoadedDeck) -> LoadedDeck:
        with self._database.writing() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO decks (deck_id, deck, created_at) VALUES (?, ?, ?)",
                (deck.deck_id, encode(deck, LoadedDeck), self._now().isoformat()),
            )
            (stored,) = connection.execute(
                "SELECT deck FROM decks WHERE deck_id = ?", (deck.deck_id,)
            ).fetchone()
        loaded: LoadedDeck = decode(stored, LoadedDeck)
        return loaded


# @spec STOR-001, STOR-011, STOR-012
class SqliteRecordStore:
    """Log entries, turn snapshots and call records, each a row holding one JSON document.

    Nothing here deletes or updates a row: records are kept indefinitely.
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def append_entry(self, game_id: str, entry: LogEntry) -> None:
        with self._database.writing() as connection:
            connection.execute(
                "INSERT INTO log_entries (game_id, seq, entry) VALUES (?, ?, ?)",
                (game_id, entry.seq, encode(entry, LogEntry)),
            )

    def add_snapshot(self, game_id: str, snapshot: TurnSnapshot) -> None:
        with self._database.writing() as connection:
            connection.execute(
                "INSERT INTO snapshots (game_id, turn, written_by, snapshot) VALUES (?, ?, ?, ?)",
                (game_id, snapshot.turn, snapshot.written_by, encode(snapshot, TurnSnapshot)),
            )

    def add_call(self, record: CallRecord) -> None:
        """Store a call record; it is given the next id, which it carries when read."""
        with self._database.writing() as connection:
            connection.execute(
                "INSERT INTO calls (game_id, tool, arguments, status, response, is_override,"
                " change, time, record) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.game_id,
                    record.tool,
                    encode(record.arguments, dict[str, object]),
                    record.status,
                    record.response,
                    int(record.is_override),
                    record.change,
                    record.time.isoformat(),
                    encode(record, CallRecord),
                ),
            )

    def read(self, game_id: str, *, since: int | None = None) -> GameRecords:
        """Entries with seq > since, calls with change > since, snapshots written after since."""
        connection = self._database.connection()
        after = (game_id, since, since)
        entries = connection.execute(
            "SELECT entry FROM log_entries WHERE game_id = ? AND (? IS NULL OR seq > ?)"
            " ORDER BY seq",
            after,
        ).fetchall()
        snapshots = connection.execute(
            "SELECT snapshot FROM snapshots WHERE game_id = ? AND (? IS NULL OR written_by > ?)"
            " ORDER BY turn",
            after,
        ).fetchall()
        calls = connection.execute(
            "SELECT id, record FROM calls WHERE game_id = ? AND (? IS NULL OR change > ?)"
            " ORDER BY id",
            after,
        ).fetchall()
        return GameRecords(
            entries=tuple(decode(entry, LogEntry) for (entry,) in entries),
            snapshots=tuple(decode(snapshot, TurnSnapshot) for (snapshot,) in snapshots),
            calls=tuple(replace(decode(record, CallRecord), id=int(id_)) for id_, record in calls),
        )


# @spec STOR-001, STOR-006, STOR-007
class SqliteUnitOfWork:
    """A transaction on the calling thread's connection.

    Every write made on that thread between `begin` and `commit` is saved together; after
    `rollback` the database is as it was at `begin`. The transaction takes the write lock
    at `begin`, so a unit of work never fails part-way for want of it.
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def begin(self) -> None:
        connection = self._database.connection()
        if connection.in_transaction:
            raise RuntimeError("a unit of work is already open on this thread")
        connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._database.connection().execute("COMMIT")

    def rollback(self) -> None:
        self._database.connection().execute("ROLLBACK")
