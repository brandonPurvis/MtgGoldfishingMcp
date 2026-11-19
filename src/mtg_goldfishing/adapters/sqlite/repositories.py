"""The persistence ports on SQLite: games, loaded decks, records and the unit of work.

Every stored domain value is one JSON document written by the codec, and that document is
authoritative. The other columns of a row are copies, kept to find rows by.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.adapters.sqlite.database import SqliteDatabase
from mtg_goldfishing.application.ports import (
    DeckRepository,
    GameRecords,
    GameRepository,
    RecordStore,
    SeatOfGame,
    StoredGame,
    UnitOfWork,
)
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot

Now = Callable[[], datetime]
"""Supplies the time a row is written, for its timestamp columns."""


def utc_now() -> datetime:
    return datetime.now(UTC)


GAMES_KEPT = 64
"""How many games a game repository keeps in memory: about 17 MB of four-seat games."""


# @spec STOR-001, STOR-004, STOR-005, STOR-008, STOR-016, STOR-017, STOR-018, STOR-019
# @spec STOR-020, STOR-015, STOR-066, STOR-078, STOR-083, STOR-084
class SqliteGameRepository(GameRepository):
    """Each game is one row: its state as one JSON document and a version counter.

    Each seat of a game is one `seats` row, written with the game and never changed, by
    which a seat id finds its game without reading any game's document.

    The games most recently read or written are also kept in memory, up to `GAMES_KEPT`,
    each at the version it was committed at, and answered from there while that version is
    still the stored one. A written game is kept when its transaction commits; a game read
    is kept only by a read that can see nothing uncommitted. A kept game is never replaced
    by an earlier version of it. The game returned is the kept object itself, shared with
    every caller, which the `GameRepository` port forbids changing.
    """

    def __init__(self, database: SqliteDatabase, *, now: Now = utc_now) -> None:
        self._database = database
        self._now = now
        self._kept: OrderedDict[str, StoredGame] = OrderedDict()
        self._guard = threading.Lock()

    # @spec STOR-073, STOR-074, STOR-075, STOR-076, STOR-077, STOR-079, STOR-080, STOR-081
    def get(self, game_id: str) -> StoredGame | None:
        connection = self._database.connection()
        with self._guard:
            kept = self._kept.get(game_id)
        if kept is not None:
            row = connection.execute(
                "SELECT version FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if row is None:
                self._forget(game_id, kept)
                return None
            if int(row[0]) == kept.version:
                self._mark_asked_for(game_id)
                return kept
        committed_only = not connection.in_transaction
        row = connection.execute(
            "SELECT state, version FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        if row is None:
            return None
        state, version = row
        read = StoredGame(decode(state, Game), int(version))
        if committed_only:
            self._keep(read, replacing_same_version=False)
        return read

    def find_seat(self, seat_id: SeatId) -> SeatOfGame | None:
        row = (
            self._database.connection()
            .execute("SELECT game_id, seat_number FROM seats WHERE seat_id = ?", (seat_id.value,))
            .fetchone()
        )
        if row is None:
            return None
        game_id, number = row
        return SeatOfGame(str(game_id), SeatNumber(int(number)))

    # @spec STOR-067, STOR-070, STOR-072, STOR-082
    def add(self, game: Game) -> None:
        now = self._now().isoformat()
        with self._database.writing() as connection:
            connection.execute(
                "INSERT INTO games (game_id, deck_id, seed, status, result, state, version,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (*_copied_columns(game), now, now),
            )
            connection.executemany(
                "INSERT INTO seats (seat_id, game_id, seat_number, deck_id, tested)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (seat.seat_id.value, game.game_id, seat.number.value, seat.deck_id, seat.tested)
                    for seat in game.seats
                ],
            )
            self._keep_on_commit(StoredGame(game, 1))

    # @spec STOR-067, STOR-069, STOR-070, STOR-072, STOR-082
    def save(self, game: Game, *, version: int) -> bool:
        """Save only if the stored version is still `version`, in one compare-and-set write."""
        game_id, deck_id, seed, status, result, state = _copied_columns(game)
        with self._database.writing() as connection:
            cursor = connection.execute(
                "UPDATE games SET deck_id = ?, seed = ?, status = ?, result = ?, state = ?,"
                " version = version + 1, updated_at = ? WHERE game_id = ? AND version = ?",
                (deck_id, seed, status, result, state, self._now().isoformat(), game_id, version),
            )
            saved = cursor.rowcount == 1
            if saved:
                self._keep_on_commit(StoredGame(game, version + 1))
            return saved

    def _keep_on_commit(self, written: StoredGame) -> None:
        """Keep a written game once its transaction commits, and never if it does not.

        Work runs in the order it was left, so the transaction's last write is kept.
        """
        self._database.on_commit(lambda: self._keep(written, replacing_same_version=True))

    def _keep(self, stored: StoredGame, *, replacing_same_version: bool) -> None:
        """Keep a game as the most recently asked for, forgetting the least recent if full.

        A game kept at a later version stays; one kept at the same version stays unless
        `replacing_same_version`, which a commit asks for and a read does not.
        """
        game_id = stored.game.game_id
        with self._guard:
            kept = self._kept.get(game_id)
            if kept is not None and (
                kept.version > stored.version
                or (kept.version == stored.version and not replacing_same_version)
            ):
                return
            self._kept[game_id] = stored
            self._kept.move_to_end(game_id)
            while len(self._kept) > GAMES_KEPT:
                self._kept.popitem(last=False)

    def _mark_asked_for(self, game_id: str) -> None:
        with self._guard:
            if game_id in self._kept:
                self._kept.move_to_end(game_id)

    def _forget(self, game_id: str, kept: StoredGame) -> None:
        """Forget a kept game, unless another thread has kept a different one since."""
        with self._guard:
            if self._kept.get(game_id) is kept:
                del self._kept[game_id]


def _copied_columns(game: Game) -> tuple[str, str, int, str, str | None, str]:
    result = game.result.outcome.value if game.result else None
    return (
        game.game_id,
        game.tested.deck_id,
        game.seed,
        game.status.value,
        result,
        encode(game, Game),
    )


DECKS_KEPT = 64
"""How many loaded decks a deck repository keeps in memory: every seat of 16 four-seat games."""


# @spec STOR-001, STOR-010, STOR-053, STOR-054, STOR-055, STOR-056, STOR-057, STOR-058
# @spec STOR-059, STOR-061, STOR-064, STOR-065
class SqliteDeckRepository(DeckRepository):
    """Each loaded deck is one row, written once and never replaced.

    The decks most recently found are also kept in memory, up to `DECKS_KEPT`, and answered from
    there: a loaded deck never changes once start-up migrations have run, so a copy cannot
    go stale. Only a read that can see nothing uncommitted (one made while no transaction
    is open on the reading connection) puts a deck in memory; adding a deck never does, so
    a rolled-back deck is never kept. A deck id that names no deck is not remembered.
    """

    def __init__(self, database: SqliteDatabase, *, now: Now = utc_now) -> None:
        self._database = database
        self._now = now
        self._kept: OrderedDict[str, LoadedDeck] = OrderedDict()
        self._guard = threading.Lock()

    def get(self, deck_id: str) -> LoadedDeck | None:
        connection = self._database.connection()
        committed_only = not connection.in_transaction  # raises once the database is closed
        with self._guard:
            kept = self._kept.get(deck_id)
            if kept is not None:
                self._kept.move_to_end(deck_id)
                return kept
        row = connection.execute("SELECT deck FROM decks WHERE deck_id = ?", (deck_id,)).fetchone()
        if row is None:
            return None
        deck: LoadedDeck = decode(row[0], LoadedDeck)
        if committed_only:
            self._keep(deck_id, deck)
        return deck

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

    def _keep(self, deck_id: str, deck: LoadedDeck) -> None:
        """Keep a deck as the most recently asked for, forgetting the least recent if full."""
        with self._guard:
            self._kept[deck_id] = deck
            self._kept.move_to_end(deck_id)
            while len(self._kept) > DECKS_KEPT:
                self._kept.popitem(last=False)


# @spec STOR-001, STOR-011, STOR-012, STOR-028, STOR-029
class SqliteRecordStore(RecordStore):
    """Log entries, turn snapshots and call records, each a row holding one JSON document.

    Nothing here deletes or updates a row: records are kept indefinitely. A snapshot row is
    keyed by its game and table turn (a goldfish game's turn), so a second snapshot for a
    table turn raises and writes nothing.
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
                (
                    game_id,
                    snapshot.table_turn,
                    snapshot.written_by,
                    encode(snapshot, TurnSnapshot),
                ),
            )

    # @spec STOR-021
    def add_call(self, record: CallRecord) -> None:
        """Store a call record, with the seat number it names, or null; it is given the next
        id, which it carries when read."""
        with self._database.writing() as connection:
            connection.execute(
                "INSERT INTO calls (game_id, seat, tool, arguments, status, response,"
                " is_override, change, time, record) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.game_id,
                    None if record.seat is None else record.seat.value,
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

    # @spec STOR-022
    def digest_baseline(self, game_id: str, seat: SeatNumber) -> int | None:
        """The change number on the seat's latest-stored call record other than `get_log`."""
        row = (
            self._database.connection()
            .execute(
                "SELECT change FROM calls WHERE game_id = ? AND seat = ? AND tool != 'get_log'"
                " ORDER BY id DESC LIMIT 1",
                (game_id, seat.value),
            )
            .fetchone()
        )
        return None if row is None or row[0] is None else int(row[0])

    # @spec STOR-042
    def change_time(self, game_id: str, change: int) -> datetime | None:
        """The time on the lowest-keyed row of `calls` holding the game's change number."""
        row = (
            self._database.connection()
            .execute(
                "SELECT time FROM calls WHERE game_id = ? AND change = ? ORDER BY id LIMIT 1",
                (game_id, change),
            )
            .fetchone()
        )
        return None if row is None else datetime.fromisoformat(str(row[0]))

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
class SqliteUnitOfWork(UnitOfWork):
    """A transaction on the calling thread's connection.

    Every write made on that thread between `begin` and `commit` is saved together; after
    `rollback` the database is as it was at `begin`. The transaction takes the write lock
    at `begin`, so a unit of work never fails part-way for want of it.
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def begin(self) -> None:
        if self._database.connection().in_transaction:
            raise RuntimeError("a unit of work is already open on this thread")
        self._database.begin()

    def commit(self) -> None:
        self._database.commit()

    def rollback(self) -> None:
        self._database.rollback()
