"""What every GameRepository promises about finding a game by a seat id, for each adapter."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.application.ports import GameRepository
from mtg_goldfishing.domain.game import seats
from tests.support.builders import a_game
from tests.support.stores import STORE_ADAPTER_IDS, STORE_ADAPTERS, OpenStores

# The seat model is reached untyped here, so the tests read the same before and after it exists.
SeatNumber: Any = seats.SeatNumber
SeatId: Any = seats.SeatId


# @spec APP-012, APP-013, STOR-001
@pytest.fixture(params=STORE_ADAPTERS, ids=STORE_ADAPTER_IDS)
def games(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    open_stores: OpenStores = request.param
    with open_stores(tmp_path) as stores:
        repository: GameRepository = stores.games
        yield repository


def a_game_of_two_seats() -> Any:
    builder: Any = a_game().with_hand("Forest")
    return builder.and_an_opposing_seat().with_hand("Island").build().game


# @spec APP-045, STOR-017
def test_a_game_id_names_the_game_and_its_tested_seat(games: Any) -> None:
    game = a_game().build().game
    games.add(game)

    found = games.find_seat(SeatId(game.game_id))

    assert (found.game_id, found.seat) == (game.game_id, SeatNumber(1))


# @spec APP-045, STOR-016, STOR-018
def test_an_opposing_seat_s_seat_id_names_its_game_and_its_seat_number(games: Any) -> None:
    game = a_game_of_two_seats()
    games.add(game)

    found = games.find_seat(game.seat(SeatNumber(2)).seat_id)

    assert (found.game_id, found.seat) == (game.game_id, SeatNumber(2))


# @spec APP-045, STOR-019
def test_an_id_that_names_no_seat_of_any_stored_game_is_reported_as_naming_none(
    games: Any,
) -> None:
    games.add(a_game().build().game)

    assert games.find_seat(SeatId("gnothing00")) is None


# @spec STOR-020
def test_a_seat_id_still_names_its_seat_after_the_game_is_saved_again(games: Any) -> None:
    game = a_game_of_two_seats()
    games.add(game)
    game.seat(SeatNumber(2)).life = 12
    games.save(game, version=1)

    found = games.find_seat(game.seat(SeatNumber(2)).seat_id)

    assert (found.game_id, found.seat) == (game.game_id, SeatNumber(2))


# @spec APP-045
def test_one_game_s_seat_ids_do_not_name_another_game(games: Any) -> None:
    one = a_game().build().game
    other = a_game().build().game
    other.game_id = "gother0001"
    other.tested.seat_id = SeatId("gother0001")
    games.add(one)
    games.add(other)

    found = games.find_seat(SeatId("gother0001"))

    assert (found.game_id, found.seat) == ("gother0001", SeatNumber(1))
