"""When saving goes wrong: a game changed underneath the call, or a failure inside the service."""

from __future__ import annotations

from mtg_goldfishing.adapters.memory import InMemoryGameRepository, InMemoryRecordStore
from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.application.ports import GameRecords, StoredGame
from mtg_goldfishing.domain.events import ErrorKind, Refused
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import a_game
from tests.support.service import GAME_ID, ServiceHarness, a_service


class ChangedByAnotherWriter:
    """A game repository where another writer saves each game just after it is loaded."""

    def __init__(self, inner: InMemoryGameRepository) -> None:
        self._inner = inner

    def get(self, game_id: str) -> StoredGame | None:
        stored = self._inner.get(game_id)
        if stored is not None:
            self._inner.save(stored.game, version=stored.version)
        return stored

    def add(self, game: Game) -> None:
        self._inner.add(game)

    def save(self, game: Game, *, version: int) -> bool:
        return self._inner.save(game, version=version)


class SnapshotsCannotBeWritten:
    """A record store whose disk fills up whenever a turn snapshot is added."""

    def __init__(self, inner: InMemoryRecordStore) -> None:
        self._inner = inner

    def append_entry(self, game_id: str, entry: LogEntry) -> None:
        self._inner.append_entry(game_id, entry)

    def add_snapshot(self, game_id: str, snapshot: TurnSnapshot) -> None:
        raise OSError("disk full")

    def add_call(self, record: CallRecord) -> None:
        self._inner.add_call(record)

    def read(self, game_id: str, *, since: int | None = None) -> GameRecords:
        return self._inner.read(game_id, since=since)


def errors_of(summary: object) -> list[ErrorKind]:
    assert isinstance(summary, Refused), summary
    return [error.kind for error in summary.errors]


def harness_whose_game_changes_underneath() -> ServiceHarness:
    harness = a_service(games=ChangedByAnotherWriter)
    harness.holding(a_game().with_hand("Forest").build())
    return harness


def harness_failing_at_cleanup() -> ServiceHarness:
    harness = a_service(records=SnapshotsCannotBeWritten)
    harness.holding(a_game().in_step(Step.END, turn=4).build())
    return harness


# ------------------------------------------------------------------ changed underneath


# @spec APP-021
def test_a_game_changed_since_it_was_loaded_is_an_error_asking_to_send_the_call_again() -> None:
    harness = harness_whose_game_changes_underneath()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    assert answer.outcome.status is Status.ERROR
    assert errors_of(answer.outcome.summary) == [ErrorKind.CHANGED_UNDERNEATH]


# @spec APP-021
def test_a_game_changed_since_it_was_loaded_saves_nothing_of_the_call() -> None:
    harness = harness_whose_game_changes_underneath()
    harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    assert harness.game().hand[0].name == "Forest"
    assert harness.records().entries == ()


# @spec APP-021, APP-019
def test_a_game_changed_since_it_was_loaded_still_gets_a_call_record() -> None:
    harness = harness_whose_game_changes_underneath()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    assert [(c.status, c.response) for c in harness.calls()] == [("ERROR", answer.response)]


# ------------------------------------------------------------------ failures inside the service


# @spec APP-020
def test_a_failure_inside_the_service_is_an_internal_failure_error() -> None:
    harness = harness_failing_at_cleanup()
    answer = harness.service.advance({"game_id": GAME_ID})
    assert answer.outcome.status is Status.ERROR
    assert errors_of(answer.outcome.summary) == [ErrorKind.INTERNAL_FAILURE]


# @spec APP-020, APP-017
def test_a_failure_inside_the_service_rolls_back_the_game_and_its_log_entry() -> None:
    harness = harness_failing_at_cleanup()
    harness.service.advance({"game_id": GAME_ID})
    assert (harness.game().step, harness.version()) == (Step.END, 1)
    assert harness.records().entries == ()


# @spec APP-020, APP-019
def test_a_failure_inside_the_service_still_gets_a_call_record() -> None:
    harness = harness_failing_at_cleanup()
    answer = harness.service.advance({"game_id": GAME_ID})
    assert [(c.tool, c.status, c.response) for c in harness.calls()] == [
        ("advance", "ERROR", answer.response)
    ]


def test_a_failure_inside_the_service_carries_the_game_s_summary() -> None:
    harness = harness_failing_at_cleanup()
    answer = harness.service.advance({"game_id": GAME_ID})
    assert answer.outcome.game is not None
    assert answer.outcome.game.step is Step.END
