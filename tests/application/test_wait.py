"""`wait`: a seat of a contested game waits, holding no lock, until it is a seat to act, it is
eliminated, the game ends, or the timeout passes; and every applied change is announced."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from mtg_goldfishing.adapters import system
from mtg_goldfishing.application import ports
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.application.service import Service
from mtg_goldfishing.domain.events import AskedKind
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.application.test_game_order import Journal
from tests.support.rendering import PlainRenderer
from tests.support.service import ServiceHarness, a_service

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
IDS = ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "dddddddddd")
GAME = "gaaaaaaaaaa"
S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)
GameChanges: Any = getattr(ports, "GameChanges", object)


class ImpatientChanges(GameChanges):  # type: ignore[misc]
    """Game changes that never see a change in time: every wait times out at once. It keeps
    the waits it was asked for and the announcements it was given."""

    def __init__(self) -> None:
        self.waits: list[tuple[str, int, float]] = []
        self.announced: list[tuple[str, int]] = []

    def announce(self, game_id: str, change: int) -> None:
        self.announced.append((game_id, change))

    def wait_for_change(self, game_id: str, after: int, timeout: float) -> bool:
        self.waits.append((game_id, after, timeout))
        return False


class WatchedChanges(GameChanges):  # type: ignore[misc]
    """The in-process game changes, telling the test when a wait has begun."""

    def __init__(self) -> None:
        self._inner: Any = system.InProcessGameChanges()  # type: ignore[attr-defined]
        self.waiting = threading.Event()

    def announce(self, game_id: str, change: int) -> None:
        self._inner.announce(game_id, change)

    def wait_for_change(self, game_id: str, after: int, timeout: float) -> bool:
        self.waiting.set()
        changed: bool = self._inner.wait_for_change(game_id, after, timeout)
        return changed


class JournaledUnitOfWork(ports.UnitOfWork):
    def __init__(self, inner: ports.UnitOfWork, journal: list[str]) -> None:
        self._inner = inner
        self._journal = journal

    def begin(self) -> None:
        self._inner.begin()

    def commit(self) -> None:
        self._inner.commit()
        self._journal.append("committed")

    def rollback(self) -> None:
        self._inner.rollback()


class JournaledChanges(GameChanges):  # type: ignore[misc]
    def __init__(self, journal: list[str]) -> None:
        self._journal = journal

    def announce(self, game_id: str, change: int) -> None:
        self._journal.append(f"announced {game_id} #{change}")

    def wait_for_change(self, game_id: str, after: int, timeout: float) -> bool:
        return False


def contested(opposing: int = 1, **options: Any) -> ServiceHarness:
    """A contested game started with the tested seat first in turn order."""
    harness = a_service(game_ids=IDS, seeds=(77,), **options)
    assert harness.started_contested_game(opposing, position=1, seed=11) == GAME
    return harness


def call_as(harness: ServiceHarness, seat: int, tool: str, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME, seat)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def started(harness: ServiceHarness) -> None:
    for seat in harness.game(GAME).seats:
        call_as(harness, seat.number.value, "mulligan", keep=True)


def waited(harness: ServiceHarness, seat: int, **arguments: object) -> Answer:
    return call_as(harness, seat, "wait", **arguments)


def summary_of(answer: Answer) -> tuple[str, Any]:
    summary: Any = answer.outcome.summary
    return type(summary).__name__, summary


class Waiter:
    """A seat's `wait` call, made on a thread of its own."""

    def __init__(self, harness: ServiceHarness, seat: int, **arguments: object) -> None:
        self.answers: list[Answer] = []
        self.thread = threading.Thread(
            target=lambda: self.answers.append(waited(harness, seat, **arguments)), daemon=True
        )
        self.thread.start()

    def answer(self) -> Answer:
        self.thread.join(timeout=10)
        assert not self.thread.is_alive(), "the wait did not return"
        (answer,) = self.answers
        return answer


def ends_its_turn(harness: ServiceHarness, seat: int) -> None:
    call_as(harness, seat, "advance", to="cleanup")
    call_as(harness, seat, "advance")


def watched_and_started() -> tuple[ServiceHarness, WatchedChanges]:
    changes = WatchedChanges()
    harness = contested(changes=changes)
    started(harness)
    return harness, changes


# ------------------------------------------------------------------ returning what is asked


# @spec APP-063
@NOT_BUILT
def test_a_seat_to_act_that_waits_is_told_at_once_what_it_is_asked() -> None:
    harness = contested(changes=ImpatientChanges())
    started(harness)
    answer = waited(harness, 1)
    kind, summary = summary_of(answer)
    assert (answer.outcome.status, kind) == (Status.OK, "SeatToAct")
    assert (summary.asked.seats, summary.asked.kind) == ((S1,), AskedKind.TURN)


# @spec APP-064
@NOT_BUILT
def test_a_waiting_seat_is_answered_once_another_seat_s_change_makes_it_the_seat_to_act() -> None:
    harness, changes = watched_and_started()
    waiter = Waiter(harness, 2)
    assert changes.waiting.wait(timeout=5)
    ends_its_turn(harness, 1)
    kind, summary = summary_of(waiter.answer())
    assert (kind, summary.asked.seats) == ("SeatToAct", (S2,))


# @spec APP-065
@NOT_BUILT
def test_a_change_that_leaves_the_waiting_seat_with_nothing_to_do_does_not_end_its_wait() -> None:
    harness, changes = watched_and_started()
    waiter = Waiter(harness, 2)
    assert changes.waiting.wait(timeout=5)
    call_as(harness, 1, "effect", source="a test effect", delta={"life": 1})
    waiter.thread.join(timeout=0.3)
    assert waiter.thread.is_alive()
    ends_its_turn(harness, 1)
    assert summary_of(waiter.answer())[0] == "SeatToAct"


# @spec APP-066
@NOT_BUILT
def test_a_wait_that_times_out_names_the_seat_to_act_and_what_it_is_asked() -> None:
    harness = contested(changes=ImpatientChanges())
    started(harness)
    answer = waited(harness, 2, timeout=1)
    kind, summary = summary_of(answer)
    assert (answer.outcome.status, kind) == (Status.OK, "StillWaiting")
    assert (summary.asked.seats, summary.asked.kind) == ((S1,), AskedKind.TURN)


# @spec APP-066
@NOT_BUILT
def test_a_wait_that_times_out_during_mulligans_names_every_seat_still_to_keep() -> None:
    harness = contested(opposing=2, changes=ImpatientChanges())
    call_as(harness, 2, "mulligan", keep=True)
    _, summary = summary_of(waited(harness, 2, timeout=1))
    assert (summary.asked.seats, summary.asked.kind) == ((S1, S3), AskedKind.KEEP)


# @spec APP-067, APP-089, GAME-114
@NOT_BUILT
def test_an_eliminated_seat_s_wait_returns_at_once_saying_it_is_out() -> None:
    changes = ImpatientChanges()
    harness = contested(opposing=2, changes=changes)
    started(harness)
    call_as(harness, 2, "end_game", result="loss")
    answer = waited(harness, 2)
    kind, summary = summary_of(answer)
    assert (answer.outcome.status, kind, summary.seat) == (Status.OK, "SeatOut", S2)
    assert changes.waits == []


# @spec APP-067, APP-089
@NOT_BUILT
def test_a_seat_eliminated_while_it_waits_is_answered_that_it_is_out() -> None:
    harness, changes = watched_and_started()
    waiter = Waiter(harness, 2)
    assert changes.waiting.wait(timeout=5)
    call_as(harness, 1, "effect", source="a test effect", delta={"damage": {"2": 40}})
    assert summary_of(waiter.answer())[0] == "SeatOut"


# @spec APP-067, APP-088
@NOT_BUILT
def test_a_game_ended_while_a_seat_waits_answers_it_that_the_game_has_ended() -> None:
    harness, changes = watched_and_started()
    waiter = Waiter(harness, 2)
    assert changes.waiting.wait(timeout=5)
    call_as(harness, 1, "end_game", result="win")
    answer = waiter.answer()
    assert (answer.outcome.status, summary_of(answer)[0]) == (Status.OK, "GameHasEnded")


# @spec APP-088
@NOT_BUILT
def test_an_eliminated_seat_waiting_on_an_ended_game_is_told_the_game_has_ended() -> None:
    harness = contested(opposing=2, changes=ImpatientChanges())
    started(harness)
    call_as(harness, 2, "end_game", result="loss")
    call_as(harness, 1, "end_game", result="win")
    assert summary_of(waited(harness, 2))[0] == "GameHasEnded"


# @spec APP-074
@NOT_BUILT
def test_a_goldfish_wait_returns_at_once_saying_what_the_seat_is_asked() -> None:
    changes = ImpatientChanges()
    harness = a_service(game_ids=IDS, changes=changes)  # type: ignore[call-arg]
    harness.started_game()
    keeping = harness.service.wait({"game_id": GAME})  # type: ignore[attr-defined]
    harness.service.mulligan({"game_id": GAME, "keep": True})
    turn = harness.service.wait({"game_id": GAME})  # type: ignore[attr-defined]
    assert [summary_of(a)[1].asked.kind for a in (keeping, turn)] == [
        AskedKind.KEEP,
        AskedKind.TURN,
    ]
    assert changes.waits == []


# @spec APP-088
@NOT_BUILT
def test_a_goldfish_wait_on_an_ended_game_says_the_game_has_ended() -> None:
    harness = a_service(game_ids=IDS, changes=ImpatientChanges())  # type: ignore[call-arg]
    harness.started_game()
    harness.service.end_game({"game_id": GAME, "result": "stalled"})
    answer = harness.service.wait({"game_id": GAME})  # type: ignore[attr-defined]
    assert (answer.outcome.status, summary_of(answer)[0]) == (Status.OK, "GameHasEnded")


# @spec APP-071
@NOT_BUILT
def test_a_wait_that_times_out_carries_the_seat_s_digest_and_game_summary() -> None:
    harness = contested(changes=ImpatientChanges())
    started(harness)
    call_as(harness, 1, "effect", source="a test effect", delta={"life": 1})
    outcome: Any = waited(harness, 2, timeout=1).outcome
    assert [(element.seat, element.change) for element in outcome.digest] == [(S1, 4)]
    assert outcome.game.table.seat == S2


# ------------------------------------------------------------------ the timeout


# @spec APP-072
@NOT_BUILT
def test_a_wait_with_no_timeout_waits_30_seconds() -> None:
    changes = ImpatientChanges()
    harness = contested(changes=changes)
    started(harness)
    waited(harness, 2)
    assert [timeout for _, _, timeout in changes.waits] == [30]


# @spec APP-090
@NOT_BUILT
def test_a_wait_accepts_a_fraction_of_a_second_in_its_timeout() -> None:
    changes = ImpatientChanges()
    harness = contested(changes=changes)
    started(harness)
    answer = waited(harness, 2, timeout=1.5)
    assert answer.outcome.status is Status.OK
    assert [timeout for _, _, timeout in changes.waits] == [1.5]


# @spec APP-073
@NOT_BUILT
def test_a_timeout_over_60_seconds_is_an_error_and_nothing_is_waited_for() -> None:
    changes = ImpatientChanges()
    harness = contested(changes=changes)
    started(harness)
    assert waited(harness, 2, timeout=61).outcome.status is Status.ERROR
    assert changes.waits == []


# @spec APP-078
@NOT_BUILT
def test_a_timeout_under_1_second_is_an_error_and_nothing_is_waited_for() -> None:
    changes = ImpatientChanges()
    harness = contested(changes=changes)
    started(harness)
    assert waited(harness, 2, timeout=0.5).outcome.status is Status.ERROR
    assert changes.waits == []


# @spec APP-091
@NOT_BUILT
def test_a_timeout_outside_the_range_is_an_error_about_the_found_game_and_seat() -> None:
    harness = contested(changes=ImpatientChanges())
    started(harness)
    outcome: Any = waited(harness, 2, timeout=0).outcome
    assert outcome.status is Status.ERROR
    assert (outcome.game.table.seat, outcome.digest is not None) == (S2, True)
    assert harness.last_call().seat == S2


# @spec APP-075
@NOT_BUILT
def test_a_wait_with_an_id_naming_no_seat_is_an_error_without_a_game() -> None:
    changes = ImpatientChanges()
    harness = a_service(changes=changes)  # type: ignore[call-arg]
    answer = harness.service.wait({"game_id": "gnosuchgame"})  # type: ignore[attr-defined]
    assert (answer.outcome.status, answer.outcome.game) == (Status.ERROR, None)
    assert changes.waits == []


# ------------------------------------------------------------------ locks, changes and records


# @spec APP-068
@NOT_BUILT
def test_a_waiting_seat_holds_no_lock_so_other_seats_calls_are_answered_meanwhile() -> None:
    harness, changes = watched_and_started()
    waiter = Waiter(harness, 2, timeout=2)
    assert changes.waiting.wait(timeout=5)
    assert call_as(harness, 1, "get_state").outcome.status is Status.OK
    assert waiter.thread.is_alive()
    waiter.answer()


# @spec APP-069
@NOT_BUILT
def test_a_wait_loads_the_game_and_adds_its_call_record_only_while_holding_the_lock() -> None:
    journal = Journal()
    harness = contested(
        changes=ImpatientChanges(),
        locks=journal.locks(),
        games=journal.games,
        records=journal.records,
    )
    started(harness)
    journal.happened.clear()
    waited(harness, 2)
    held = False
    for happened in journal.happened:
        if happened in ("lock held", "lock released"):
            held = happened == "lock held"
        elif happened in ("game loaded", "call recorded"):
            assert held, journal.happened
    assert "call recorded" in journal.happened


# @spec APP-070, REC-026, REC-053
@NOT_BUILT
def test_a_wait_changes_nothing_logs_nothing_announces_nothing_and_keeps_a_call_record() -> None:
    changes = ImpatientChanges()
    harness = contested(changes=changes)
    started(harness)
    version, entries = harness.version(GAME), len(harness.records(GAME).entries)
    announced = list(changes.announced)
    waited(harness, 2)
    assert (harness.version(GAME), harness.game(GAME).change) == (version, 3)
    assert len(harness.records(GAME).entries) == entries
    assert changes.announced == announced
    assert (harness.last_call().tool, harness.last_call().seat) == ("wait", S2)


# @spec APP-059
@NOT_BUILT
def test_an_applied_change_is_announced_once_its_unit_of_work_has_committed() -> None:
    journal: list[str] = []
    harness = contested()
    stores = harness.stores
    harness.service = Service(  # type: ignore[call-arg]
        games=stores.games,
        decks=stores.decks,
        records=stores.records,
        unit_of_work=JournaledUnitOfWork(stores.unit_of_work, journal),
        catalog=harness.catalog,
        locks=harness.locks,
        ids=harness.ids,
        clock=harness.clock,
        renderer=PlainRenderer(),
        changes=JournaledChanges(journal),
    )
    call_as(harness, 1, "mulligan", keep=True)
    assert journal == ["committed", f"announced {GAME} #2"]


# @spec APP-060
@NOT_BUILT
def test_a_refused_or_read_only_call_announces_nothing() -> None:
    changes = ImpatientChanges()
    harness = contested(changes=changes)
    started(harness)
    announced = list(changes.announced)
    call_as(harness, 2, "advance")
    call_as(harness, 2, "get_state")
    call_as(harness, 2, "get_log")
    assert changes.announced == announced


# @spec GAME-114
@NOT_BUILT
def test_a_seat_that_is_not_the_seat_to_act_may_read_the_state_and_log_and_wait() -> None:
    harness = contested(changes=ImpatientChanges())
    started(harness)
    statuses = [call_as(harness, 2, tool).outcome.status for tool in ("get_state", "get_log")]
    assert [*statuses, waited(harness, 2, timeout=1).outcome.status] == [Status.OK] * 3


# @spec GAME-114
@NOT_BUILT
def test_an_eliminated_seat_may_read_the_state_and_log_and_wait() -> None:
    harness = contested(opposing=2, changes=ImpatientChanges())
    started(harness)
    call_as(harness, 3, "end_game", result="loss")
    statuses = [call_as(harness, 3, tool).outcome.status for tool in ("get_state", "get_log")]
    assert [*statuses, waited(harness, 3).outcome.status] == [Status.OK] * 3
