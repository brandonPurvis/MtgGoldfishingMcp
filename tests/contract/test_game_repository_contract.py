"""What every GameRepository promises, run against each adapter that implements it."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from mtg_goldfishing.application.ports import GameRepository, StoredGame
from mtg_goldfishing.domain.game.model import GameStatus
from tests.support.builders import a_game
from tests.support.stored import a_rich_game
from tests.support.stores import STORE_ADAPTER_IDS, STORE_ADAPTERS, OpenStores


# @spec APP-012, APP-013, STOR-001
@pytest.fixture(params=STORE_ADAPTERS, ids=STORE_ADAPTER_IDS)
def games(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[GameRepository]:
    open_stores: OpenStores = request.param
    with open_stores(tmp_path) as stores:
        yield stores.games


def test_a_repository_has_no_game_under_an_id_never_added(games: GameRepository) -> None:
    assert games.get("gnothing00") is None


# @spec STOR-005
def test_an_added_game_is_returned_equal_at_version_one(games: GameRepository) -> None:
    game = a_game().with_hand("Sol Ring").with_battlefield("Forest").build().game
    games.add(game)

    assert games.get(game.game_id) == StoredGame(game, 1)


# @spec STOR-004, STOR-005
def test_a_game_with_every_kind_of_state_is_returned_equal(games: GameRepository) -> None:
    game = a_rich_game()
    games.add(game)

    stored = games.get(game.game_id)

    assert (stored and stored.game) == game


# @spec STOR-005, STOR-008
def test_saving_at_the_stored_version_keeps_the_game_and_increments_the_version(
    games: GameRepository,
) -> None:
    game = a_game().build().game
    games.add(game)
    game.life = 33
    game.change = 1

    saved = games.save(game, version=1)

    assert (saved, games.get(game.game_id)) == (True, StoredGame(game, 2))


# @spec STOR-008
def test_saving_at_a_stale_version_fails(games: GameRepository) -> None:
    game = a_game().build().game
    games.add(game)
    games.save(game, version=1)

    assert games.save(game, version=1) is False


# @spec STOR-008
def test_a_save_at_a_stale_version_writes_nothing(games: GameRepository) -> None:
    game = a_game().build().game
    games.add(game)
    first = a_game().with_life(30).build().game
    games.save(first, version=1)
    second = a_game().with_life(20).build().game

    games.save(second, version=1)

    assert games.get(game.game_id) == StoredGame(first, 2)


# @spec STOR-008
def test_saving_a_game_never_added_fails(games: GameRepository) -> None:
    assert games.save(a_game().build().game, version=1) is False


def test_changing_a_game_after_adding_it_does_not_change_the_stored_game(
    games: GameRepository,
) -> None:
    game = a_game().build().game
    games.add(game)

    game.life = 1
    game.cards.clear()

    assert games.get(game.game_id) == StoredGame(a_game().build().game, 1)


def test_changing_a_loaded_game_does_not_change_the_stored_game(games: GameRepository) -> None:
    games.add(a_game().build().game)
    loaded = games.get("gtest000001")
    assert loaded is not None

    loaded.game.status = GameStatus.ENDED

    assert games.get("gtest000001") == StoredGame(a_game().build().game, 1)


def test_saving_one_game_leaves_other_games_as_they_were(games: GameRepository) -> None:
    one = a_rich_game("gone000001")
    other = a_rich_game("gother0001")
    games.add(one)
    games.add(other)
    one.life = 12

    games.save(one, version=1)

    assert games.get("gother0001") == StoredGame(other, 1)
