"""The in-memory game repository shares the games it keeps, as the SQLite repository does,
and checks each kept game against a private copy so that a caller that changes one fails.

These tests change a kept game on purpose, which no caller may do, to see the check work.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from mtg_goldfishing.adapters.memory import InMemoryStores
from mtg_goldfishing.domain.game.model import Game
from tests.support.builders import a_game

not_yet_shared = pytest.mark.xfail(
    strict=True,
    reason="the in-memory game repository copies games and keeps no private copy to check yet",
)


def a_stored_game(stores: InMemoryStores) -> Game:
    game = a_game().build().game
    stores.games.add(game)
    return game


def changed(game: Game) -> Game:
    """A copy of the game with its change number moved on."""
    copy = game.copy()
    copy.change += 1
    return copy


def raises(call: Callable[[], object]) -> bool:
    """Whether the call raises an exception; which exception the check raises is not named."""
    try:
        call()
    except Exception:
        return True
    return False


# ----------------------------------------------------------------- the kept object itself


# @spec APP-100
@not_yet_shared
def test_the_game_returned_is_the_game_object_added() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert found.game is game


# @spec APP-100
@not_yet_shared
def test_the_game_returned_is_the_game_object_last_saved() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    saved = changed(game)
    stores.games.save(saved, version=1)

    found = stores.games.get(game.game_id)

    assert found is not None
    assert found.game is saved


# @spec APP-100
@not_yet_shared
def test_every_call_is_returned_the_same_kept_game() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)

    first, second = stores.games.get(game.game_id), stores.games.get(game.game_id)

    assert first is not None
    assert second is not None
    assert first.game is second.game


# ------------------------------------------------------------- the check against the copy


# @spec APP-101, APP-098, APP-103
@not_yet_shared
def test_asking_for_a_game_changed_after_it_was_added_raises() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    game.tested.life = 1

    assert raises(lambda: stores.games.get(game.game_id))


# @spec APP-101, APP-098, APP-103
@not_yet_shared
def test_asking_for_a_game_changed_after_it_was_returned_raises() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    loaded = stores.games.get(game.game_id)
    assert loaded is not None
    loaded.game.tested.life = 1

    assert raises(lambda: stores.games.get(game.game_id))


# @spec APP-101, APP-098, APP-103
@not_yet_shared
def test_asking_for_a_game_changed_after_it_was_saved_raises() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    saved = changed(game)
    stores.games.save(saved, version=1)
    saved.tested.life = 1

    assert raises(lambda: stores.games.get(game.game_id))


# @spec APP-101, APP-098, APP-103
@not_yet_shared
def test_saving_over_a_kept_game_that_was_changed_raises() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    game.tested.life = 1

    assert raises(lambda: stores.games.save(changed(a_game().build().game), version=1))


# @spec APP-101
def test_asking_for_a_kept_game_nobody_changed_does_not_raise() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    stores.games.save(changed(game), version=1)

    assert not raises(lambda: stores.games.get(game.game_id))


# ---------------------------------------------------------------------- a rolled-back unit


# @spec APP-104
@not_yet_shared
def test_a_rolled_back_unit_of_work_restores_each_game_with_its_own_copy() -> None:
    stores = InMemoryStores()
    game = a_stored_game(stores)
    stores.unit_of_work.begin()
    stores.games.save(changed(game), version=1)
    stores.unit_of_work.rollback()

    found = stores.games.get(game.game_id)

    assert found is not None
    assert found.game is game
