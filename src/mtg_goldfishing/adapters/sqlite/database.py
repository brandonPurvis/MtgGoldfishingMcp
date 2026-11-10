"""The database file: opening it, its schema version, connections and transactions.

Connections. Each thread gets its own connection, opened on first use and closed when the
database is closed. A unit of work is a transaction on the calling thread's connection, so
the use case that begins it, makes its writes and commits it — all on one thread — owns it
alone, and calls for other games on other threads are not queued behind it. With WAL, a
reader never waits for a writer. SQLite admits one writer at a time, so a write to another
game made while a unit of work is open waits (up to the busy timeout) for that unit to end,
then goes ahead; nothing in this module holds a lock for longer than one transaction.

A single shared connection behind a lock would be simpler, but it would make every call,
reads included, wait for any other game's open unit of work.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from mtg_goldfishing.adapters.sqlite.schema import MIGRATIONS

DEFAULT_BUSY_TIMEOUT = 5.0
"""Seconds a write waits for another connection's transaction before failing."""


class SchemaTooNew(Exception):
    """The database was laid out by a newer version of the service.

    Raised while opening the database, before anything is changed. The service cannot run
    against it safely, so this is not a refusal to report to an agent: the composition root
    lets it end start-up, with this message naming both versions.
    """

    def __init__(self, path: Path, found: int, supported: int) -> None:
        super().__init__(
            f"the database {path} has schema version {found}, but this service supports "
            f"schema version {supported} at most; refusing to start so as not to damage it"
        )
        self.path = path
        self.found = found
        self.supported = supported


# @spec STOR-002, STOR-003, STOR-013, STOR-014
class SqliteDatabase:
    """One SQLite database file, created if missing and migrated to the current layout."""

    def __init__(
        self,
        path: str | Path,
        *,
        migrations: Sequence[str] = MIGRATIONS,
        busy_timeout: float = DEFAULT_BUSY_TIMEOUT,
    ) -> None:
        self.path = Path(path)
        self._migrations = tuple(migrations)
        self._busy_timeout = busy_timeout
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._guard = threading.Lock()
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._start()
        except BaseException:
            self.close()
            raise

    @property
    def supported_version(self) -> int:
        return len(self._migrations)

    def connection(self) -> sqlite3.Connection:
        """The calling thread's connection, opened on first use."""
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            with self._guard:
                if self._closed:
                    raise RuntimeError(f"the database {self.path} is closed")
                connection = sqlite3.connect(
                    self.path,
                    timeout=self._busy_timeout,
                    isolation_level=None,
                    check_same_thread=False,
                )
                connection.execute("PRAGMA foreign_keys = ON")
                self._connections.append(connection)
            self._local.connection = connection
        return connection

    @contextmanager
    def writing(self) -> Iterator[sqlite3.Connection]:
        """A connection to write through, atomically.

        Inside an open unit of work the writes join it, and its commit or rollback decides
        their fate. Otherwise they are committed together on leaving the block, or rolled
        back if it raises.
        """
        connection = self.connection()
        if connection.in_transaction:
            yield connection
            return
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    def close(self) -> None:
        with self._guard:
            self._closed = True
            for connection in self._connections:
                connection.close()
            self._connections.clear()

    def _start(self) -> None:
        connection = self.connection()
        found = _stored_version(connection)
        if found > self.supported_version:
            raise SchemaTooNew(self.path, found, self.supported_version)
        connection.execute("PRAGMA journal_mode = WAL")
        self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        """Apply each missing migration in its own transaction, recording the version reached."""
        for version, script in enumerate(self._migrations, start=1):
            connection.execute("BEGIN IMMEDIATE")
            try:
                if _stored_version(connection) < version:
                    for statement in _statements(script):
                        connection.execute(statement)
                    connection.execute("DELETE FROM schema_version")
                    connection.execute(
                        "INSERT INTO schema_version (version) VALUES (?)", (version,)
                    )
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")


def _statements(script: str) -> Iterator[str]:
    """The SQL statements of a script, one at a time.

    `executescript` would commit the open transaction first, so a migration is run statement
    by statement inside its own transaction instead.
    """
    pending = ""
    for piece in script.split(";"):
        pending += piece + ";"
        if sqlite3.complete_statement(pending):
            if _has_sql(pending):
                yield pending
            pending = ""
    if _has_sql(pending):
        yield pending


def _has_sql(text: str) -> bool:
    return bool(text.replace(";", "").strip())


def _stored_version(connection: sqlite3.Connection) -> int:
    has_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if has_table is None:
        return 0
    row = connection.execute("SELECT max(version) FROM schema_version").fetchone()
    return 0 if row is None or row[0] is None else int(row[0])
