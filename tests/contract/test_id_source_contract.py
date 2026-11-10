"""What every IdSource promises. Add another adapter's id source as one more fixture param."""

import re
from collections.abc import Callable

import pytest

from mtg_goldfishing.adapters.memory import FixedIdSource
from mtg_goldfishing.adapters.system import RandomIdSource
from mtg_goldfishing.application.ports import IdSource

GAME_ID_CHARACTERS = re.compile(r"^[a-z0-9]{10}$")


# @spec APP-012, APP-013
@pytest.fixture(params=[FixedIdSource, RandomIdSource], ids=["fixed", "random"])
def ids(request: pytest.FixtureRequest) -> IdSource:
    new_ids: Callable[[], IdSource] = request.param
    return new_ids()


# @spec GAME-006
def test_a_game_id_is_ten_lower_case_letters_or_digits(ids: IdSource) -> None:
    assert GAME_ID_CHARACTERS.match(ids.new_game_id())


def test_successive_game_ids_differ(ids: IdSource) -> None:
    assert len({ids.new_game_id() for _ in range(5)}) == 5


def test_a_seed_is_a_positive_whole_number(ids: IdSource) -> None:
    seed = ids.new_seed()
    assert type(seed) is int
    assert seed > 0


# @spec APP-013
def test_a_fixed_id_source_yields_its_game_ids_in_order() -> None:
    ids = FixedIdSource(game_ids=["aaaaaaaaaa", "bbbbbbbbbb"])
    assert [ids.new_game_id(), ids.new_game_id()] == ["aaaaaaaaaa", "bbbbbbbbbb"]


# @spec APP-013
def test_a_fixed_id_source_yields_its_seeds_in_order() -> None:
    ids = FixedIdSource(seeds=[7, 3])
    assert [ids.new_seed(), ids.new_seed()] == [7, 3]


def test_a_fixed_id_source_refuses_a_game_id_that_is_not_ten_letters_or_digits() -> None:
    with pytest.raises(ValueError, match="game id"):
        FixedIdSource(game_ids=["Not-An-Id"])
