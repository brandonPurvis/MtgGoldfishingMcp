"""The persistence ports in memory: games, loaded decks and records in dictionaries.

The game repository shares the games it keeps, as the SQLite repository does: it returns
the kept object itself and keeps the object it is given. Since no caller may change such a
game, it holds a private copy of each kept game and raises when a kept game no longer
equals it. The deck and record stores keep deep copies, taken on the way in and on the way
out, so nothing a caller holds is shared with what they store.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol

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


class _Checkpointed(Protocol):
    """A store whose whole contents can be set aside and put back by a unit of work."""

    def checkpoint(self) -> object: ...

    def restore(self, checkpoint: object) -> None: ...


class KeptGameChanged(Exception):
    """A game the in-memory game repository keeps was changed after it was kept.

    No caller may change a game the repository returned or was handed to add or save, so
    this is a defect in the caller, never a refusal.
    """

    def __init__(self, game_id: str) -> None:
        super().__init__(
            f"the game {game_id} was changed after the in-memory game repository kept it"
        )
        self.game_id = game_id


@dataclass(frozen=True)
class _KeptGame:
    """A kept game at its version, beside a private copy taken when it was kept."""

    stored: StoredGame
    copy: Game

    @classmethod
    def of(cls, game: Game, version: int) -> _KeptGame:
        return cls(StoredGame(game, version), game.copy())

    def changed(self) -> bool:
        return self.stored.game != self.copy


# @spec APP-013, APP-045, APP-100, APP-101, APP-104
class InMemoryGameRepository(GameRepository):
    """Games by id, each with the version counter it was stored at, and the game and seat
    number each seat id names, written when the game is added and never changed.

    The game object given to `add` or `save` is the one kept and returned. Beside it is a
    private copy taken when it was kept, against which the kept game is checked whenever it
    is asked for or saved over; a rolled-back unit of work restores each game with its copy.
    """

    def __init__(self) -> None:
        self._games: dict[str, _KeptGame] = {}
        self._seats: dict[SeatId, SeatOfGame] = {}

    def get(self, game_id: str) -> StoredGame | None:
        kept = self._unchanged(game_id)
        return None if kept is None else kept.stored

    def find_seat(self, seat_id: SeatId) -> SeatOfGame | None:
        return self._seats.get(seat_id)

    def add(self, game: Game) -> None:
        if game.game_id in self._games:
            raise ValueError(f"a game is already stored under {game.game_id}")
        self._games[game.game_id] = _KeptGame.of(game, 1)
        for seat in game.seats:
            self._seats[seat.seat_id] = SeatOfGame(game.game_id, seat.number)

    def save(self, game: Game, *, version: int) -> bool:
        kept = self._unchanged(game.game_id)
        if kept is None or kept.stored.version != version:
            return False
        self._games[game.game_id] = _KeptGame.of(game, version + 1)
        return True

    def changed_games(self) -> tuple[str, ...]:
        """The id of every kept game that no longer equals its private copy."""
        return tuple(game_id for game_id, kept in self._games.items() if kept.changed())

    def checkpoint(self) -> object:
        return dict(self._games), dict(self._seats)

    def restore(self, checkpoint: object) -> None:
        assert isinstance(checkpoint, tuple)
        games, seats = checkpoint
        self._games = dict(games)
        self._seats = dict(seats)

    def _unchanged(self, game_id: str) -> _KeptGame | None:
        """The game kept under this id, if any, raising if it was changed since kept."""
        kept = self._games.get(game_id)
        if kept is not None and kept.changed():
            raise KeptGameChanged(game_id)
        return kept


# @spec APP-013
class InMemoryDeckRepository(DeckRepository):
    """Loaded decks by id. A deck once added is never replaced."""

    def __init__(self) -> None:
        self._decks: dict[str, LoadedDeck] = {}

    def get(self, deck_id: str) -> LoadedDeck | None:
        return copy.deepcopy(self._decks.get(deck_id))

    def add(self, deck: LoadedDeck) -> LoadedDeck:
        stored = self._decks.setdefault(deck.deck_id, copy.deepcopy(deck))
        return copy.deepcopy(stored)

    def checkpoint(self) -> object:
        return dict(self._decks)

    def restore(self, checkpoint: object) -> None:
        assert isinstance(checkpoint, dict)
        self._decks = dict(checkpoint)


@dataclass
class _Records:
    entries: dict[str, list[LogEntry]] = field(default_factory=dict)
    snapshots: dict[str, list[TurnSnapshot]] = field(default_factory=dict)
    calls: list[CallRecord] = field(default_factory=list)
    next_call_id: int = 1


def _after(number: int | None, since: int | None) -> bool:
    return since is None or (number is not None and number > since)


class SnapshotAlreadyKept(Exception):
    """A second snapshot for a table turn of a game: a defect, never a replacement."""


# @spec APP-013, APP-046, APP-092
class InMemoryRecordStore(RecordStore):
    """Log entries and turn snapshots per game, and every call record, numbered as added."""

    def __init__(self) -> None:
        self._records = _Records()

    def append_entry(self, game_id: str, entry: LogEntry) -> None:
        self._records.entries.setdefault(game_id, []).append(copy.deepcopy(entry))

    def add_snapshot(self, game_id: str, snapshot: TurnSnapshot) -> None:
        kept = self._records.snapshots.setdefault(game_id, [])
        if any(held.table_turn == snapshot.table_turn for held in kept):
            raise SnapshotAlreadyKept(
                f"game {game_id} has a snapshot of turn {snapshot.table_turn}"
            )
        kept.append(copy.deepcopy(snapshot))

    def add_call(self, record: CallRecord) -> None:
        self._records.calls.append(copy.deepcopy(replace(record, id=self._records.next_call_id)))
        self._records.next_call_id += 1

    def read(self, game_id: str, *, since: int | None = None) -> GameRecords:
        entries = self._records.entries.get(game_id, [])
        snapshots = self._records.snapshots.get(game_id, [])
        return copy.deepcopy(
            GameRecords(
                entries=tuple(
                    sorted((e for e in entries if _after(e.seq, since)), key=lambda e: e.seq)
                ),
                snapshots=tuple(
                    sorted(
                        (s for s in snapshots if _after(s.written_by, since)),
                        key=lambda s: s.table_turn,
                    )
                ),
                calls=tuple(
                    c
                    for c in self._records.calls
                    if c.game_id == game_id and _after(c.change, since)
                ),
            )
        )

    def digest_baseline(self, game_id: str, seat: SeatNumber) -> int | None:
        latest = [
            call.change
            for call in self._records.calls
            if call.game_id == game_id and call.seat == seat and call.tool != "get_log"
        ]
        return latest[-1] if latest else None

    def change_time(self, game_id: str, change: int) -> datetime | None:
        return next(
            (
                call.time
                for call in self._records.calls
                if call.game_id == game_id and call.change == change
            ),
            None,
        )

    def calls(self) -> tuple[CallRecord, ...]:
        """Every call record in the order added, whatever game it names or none."""
        return copy.deepcopy(tuple(self._records.calls))

    def checkpoint(self) -> object:
        return copy.deepcopy(self._records)

    def restore(self, checkpoint: object) -> None:
        assert isinstance(checkpoint, _Records)
        self._records = copy.deepcopy(checkpoint)


# @spec APP-013
class InMemoryUnitOfWork(UnitOfWork):
    """Sets aside the contents of its stores on `begin` and puts them back on `rollback`."""

    def __init__(self, *stores: _Checkpointed) -> None:
        self._stores = stores
        self._checkpoints: list[object] | None = None

    def begin(self) -> None:
        if self._checkpoints is not None:
            raise RuntimeError("a unit of work is already open")
        self._checkpoints = [store.checkpoint() for store in self._stores]

    def commit(self) -> None:
        self._open_checkpoints()
        self._checkpoints = None

    def rollback(self) -> None:
        for store, checkpoint in zip(self._stores, self._open_checkpoints(), strict=True):
            store.restore(checkpoint)
        self._checkpoints = None

    def _open_checkpoints(self) -> list[object]:
        if self._checkpoints is None:
            raise RuntimeError("no unit of work is open")
        return self._checkpoints


class InMemoryStores:
    """The in-memory game, deck and record stores with a unit of work spanning all three."""

    def __init__(self) -> None:
        self.games = InMemoryGameRepository()
        self.decks = InMemoryDeckRepository()
        self.records = InMemoryRecordStore()
        self.unit_of_work = InMemoryUnitOfWork(self.games, self.decks, self.records)
