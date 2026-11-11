"""What GameChanges promises: an announced change wakes a wait for that game, and a wait with
no change returns when its timeout passes. Run against its one implementation."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from mtg_goldfishing.adapters import system
from mtg_goldfishing.application import ports

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
GAME = "gtest000001"
OTHER = "gother00001"
SHORT = 0.05


def game_changes() -> Any:
    """The in-process game changes, the one implementation the service and the tests share."""
    return system.InProcessGameChanges()  # type: ignore[attr-defined]


def announced_soon(changes: Any, game_id: str, change: int) -> threading.Thread:
    def announce() -> None:
        time.sleep(SHORT)
        changes.announce(game_id, change)

    thread = threading.Thread(target=announce, daemon=True)
    thread.start()
    return thread


# @spec APP-041, APP-048
@NOT_BUILT
def test_the_in_process_game_changes_implement_the_port() -> None:
    port: Any = ports.GameChanges  # type: ignore[attr-defined]
    assert isinstance(game_changes(), port)


# @spec APP-041
@NOT_BUILT
def test_a_wait_returns_at_once_when_a_later_change_was_already_announced() -> None:
    changes = game_changes()
    changes.announce(GAME, 5)
    started = time.monotonic()
    assert changes.wait_for_change(GAME, 4, 5.0)
    assert time.monotonic() - started < 1


# @spec APP-041
@NOT_BUILT
def test_a_wait_with_no_change_returns_false_when_its_timeout_passes() -> None:
    changes = game_changes()
    assert not changes.wait_for_change(GAME, 4, SHORT)


# @spec APP-041
@NOT_BUILT
def test_a_change_announced_during_a_wait_wakes_it() -> None:
    changes = game_changes()
    thread = announced_soon(changes, GAME, 5)
    assert changes.wait_for_change(GAME, 4, 5.0)
    thread.join()


# @spec APP-041
@NOT_BUILT
def test_a_change_to_another_game_does_not_wake_a_wait() -> None:
    changes = game_changes()
    thread = announced_soon(changes, OTHER, 5)
    assert not changes.wait_for_change(GAME, 4, SHORT * 4)
    thread.join()


# @spec APP-041
@NOT_BUILT
def test_an_announced_change_no_later_than_the_one_waited_after_does_not_end_the_wait() -> None:
    changes = game_changes()
    changes.announce(GAME, 4)
    assert not changes.wait_for_change(GAME, 4, SHORT)
