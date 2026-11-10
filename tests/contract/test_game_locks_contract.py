"""What every GameLocks promises. Add another adapter's locks as one more fixture param."""

import threading
from collections.abc import Callable

import pytest

from mtg_goldfishing.adapters.memory import InProcessGameLocks
from mtg_goldfishing.application.ports import GameLocks

WAIT = 5.0
"""Seconds to wait for something that should happen."""

MOMENT = 0.1
"""Seconds to wait for something that should not happen."""


# @spec APP-012, APP-013
@pytest.fixture(params=[InProcessGameLocks], ids=["in-process"])
def locks(request: pytest.FixtureRequest) -> GameLocks:
    new_locks: Callable[[], GameLocks] = request.param
    return new_locks()


def _held_in_another_thread(
    locks: GameLocks, game_id: str
) -> tuple[threading.Event, threading.Thread]:
    """Start a thread that holds `game_id`'s lock; the event is set once it has it."""
    holding = threading.Event()

    def hold() -> None:
        with locks.hold(game_id):
            holding.set()

    thread = threading.Thread(target=hold)
    thread.start()
    return holding, thread


# @spec APP-015
def test_a_game_s_lock_held_by_one_call_makes_another_call_for_that_game_wait(
    locks: GameLocks,
) -> None:
    with locks.hold("g1"):
        holding, thread = _held_in_another_thread(locks, "g1")
        assert not holding.wait(MOMENT)
    assert holding.wait(WAIT)
    thread.join(WAIT)


# @spec APP-016
def test_a_game_s_lock_held_by_one_call_does_not_make_another_game_wait(
    locks: GameLocks,
) -> None:
    with locks.hold("g1"):
        holding, thread = _held_in_another_thread(locks, "g2")
        assert holding.wait(WAIT)
    thread.join(WAIT)


def test_a_game_s_lock_is_released_when_the_call_holding_it_fails(locks: GameLocks) -> None:
    with pytest.raises(RuntimeError), locks.hold("g1"):
        raise RuntimeError("a defect")
    holding, thread = _held_in_another_thread(locks, "g1")
    assert holding.wait(WAIT)
    thread.join(WAIT)


def test_a_game_s_lock_can_be_held_again_after_it_is_released(locks: GameLocks) -> None:
    with locks.hold("g1"):
        pass
    with locks.hold("g1"):
        pass
    holding, thread = _held_in_another_thread(locks, "g1")
    assert holding.wait(WAIT)
    thread.join(WAIT)
