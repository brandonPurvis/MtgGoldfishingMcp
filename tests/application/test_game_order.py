"""One game's calls are applied one at a time; different games never wait on each other."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

from mtg_goldfishing.adapters.memory import InMemoryGameRepository, InMemoryRecordStore
from mtg_goldfishing.adapters.system import InProcessGameLocks
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.application.ports import (
    GameLocks,
    GameRecords,
    GameRepository,
    RecordStore,
    SeatOfGame,
    StoredGame,
)
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot
from tests.support.builders import a_game
from tests.support.service import GAME_ID, a_service

OTHER_GAME = "gtest000002"
LOSE_A_LIFE = {"game_id": GAME_ID, "source": "Phyrexian Arena", "delta": {"life": -1}}


class Journal:
    """What happened, in order, across the locks and the stores."""

    def __init__(self) -> None:
        self.happened: list[str] = []

    def locks(self) -> JournaledLocks:
        return JournaledLocks(self)

    def games(self, inner: InMemoryGameRepository) -> JournaledGames:
        return JournaledGames(self, inner)

    def records(self, inner: InMemoryRecordStore) -> JournaledRecords:
        return JournaledRecords(self, inner)


class JournaledLocks(GameLocks):
    def __init__(self, journal: Journal) -> None:
        self._journal = journal
        self._inner = InProcessGameLocks()

    @contextmanager
    def _hold(self, game_id: str) -> Iterator[None]:
        with self._inner.hold(game_id):
            self._journal.happened.append("lock held")
            try:
                yield
            finally:
                self._journal.happened.append("lock released")

    def hold(self, game_id: str) -> AbstractContextManager[None]:
        return self._hold(game_id)


class JournaledGames(GameRepository):
    def __init__(self, journal: Journal, inner: InMemoryGameRepository) -> None:
        self._journal = journal
        self._inner = inner

    def get(self, game_id: str) -> StoredGame | None:
        self._journal.happened.append("game loaded")
        return self._inner.get(game_id)

    def find_seat(self, seat_id: SeatId) -> SeatOfGame | None:
        return self._inner.find_seat(seat_id)

    def add(self, game: Game) -> None:
        self._inner.add(game)

    def save(self, game: Game, *, version: int) -> bool:
        self._journal.happened.append("game saved")
        return self._inner.save(game, version=version)


class JournaledRecords(RecordStore):
    def __init__(self, journal: Journal, inner: InMemoryRecordStore) -> None:
        self._journal = journal
        self._inner = inner

    def append_entry(self, game_id: str, entry: LogEntry) -> None:
        self._journal.happened.append("entry appended")
        self._inner.append_entry(game_id, entry)

    def add_snapshot(self, game_id: str, snapshot: TurnSnapshot) -> None:
        self._inner.add_snapshot(game_id, snapshot)

    def add_call(self, record: CallRecord) -> None:
        self._journal.happened.append("call recorded")
        self._inner.add_call(record)

    def read(self, game_id: str, *, since: int | None = None) -> GameRecords:
        return self._inner.read(game_id, since=since)

    def digest_baseline(self, game_id: str, seat: SeatNumber) -> int | None:
        return self._inner.digest_baseline(game_id, seat)


class SlowToLoad(GameRepository):
    """A game repository that takes a moment to load, widening any race between two calls."""

    def __init__(self, inner: InMemoryGameRepository) -> None:
        self._inner = inner

    def get(self, game_id: str) -> StoredGame | None:
        stored = self._inner.get(game_id)
        time.sleep(0.05)
        return stored

    def find_seat(self, seat_id: SeatId) -> SeatOfGame | None:
        return self._inner.find_seat(seat_id)

    def add(self, game: Game) -> None:
        self._inner.add(game)

    def save(self, game: Game, *, version: int) -> bool:
        return self._inner.save(game, version=version)


# @spec APP-014
def test_a_call_holds_the_game_s_lock_from_before_loading_until_its_records_are_saved() -> None:
    journal = Journal()
    harness = a_service(locks=journal.locks(), games=journal.games, records=journal.records)
    harness.holding(a_game().build())
    harness.service.effect(LOSE_A_LIFE)
    assert journal.happened == [
        "lock held",
        "game loaded",
        "game saved",
        "entry appended",
        "call recorded",
        "lock released",
    ]


# @spec APP-014
def test_a_read_only_call_holds_the_game_s_lock_until_its_call_record_is_saved() -> None:
    journal = Journal()
    harness = a_service(locks=journal.locks(), games=journal.games, records=journal.records)
    harness.holding(a_game().build())
    harness.service.get_state({"game_id": GAME_ID})
    assert journal.happened == ["lock held", "game loaded", "call recorded", "lock released"]


# @spec APP-015
def test_two_calls_for_one_game_at_once_are_applied_one_after_the_other() -> None:
    harness = a_service(games=SlowToLoad)
    harness.holding(a_game().with_life(40).build())
    answers: list[Answer] = []

    def call() -> None:
        answers.append(harness.service.effect(LOSE_A_LIFE))

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(a.outcome.game.change for a in answers if a.outcome.game) == [1, 2]
    assert [a.outcome.status for a in answers] == [Status.OK, Status.OK]
    assert harness.game().tested.life == 38


# @spec APP-016
def test_a_call_for_one_game_does_not_wait_for_another_game_s_lock() -> None:
    harness = a_service()
    harness.holding(a_game().build(), GAME_ID)
    harness.holding(a_game().build(), OTHER_GAME)
    answered = threading.Event()

    def call_other_game() -> None:
        harness.service.get_state({"game_id": OTHER_GAME})
        answered.set()

    with harness.locks.hold(GAME_ID):
        thread = threading.Thread(target=call_other_game)
        thread.start()
        assert answered.wait(timeout=5)
    thread.join(timeout=5)


# @spec APP-015
def test_a_call_for_a_game_whose_lock_is_held_waits_for_it() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    answered = threading.Event()

    def call() -> None:
        harness.service.get_state({"game_id": GAME_ID})
        answered.set()

    with harness.locks.hold(GAME_ID):
        thread = threading.Thread(target=call)
        thread.start()
        assert not answered.wait(timeout=0.1)
    assert answered.wait(timeout=5)
    thread.join(timeout=5)
