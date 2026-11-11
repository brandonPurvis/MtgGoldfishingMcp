"""A call about a game is made by a seat: the use case finds the seat its id names."""

from __future__ import annotations

import inspect
import re
from typing import Any

import pytest

from mtg_goldfishing.adapters.memory import InMemoryGameRepository
from mtg_goldfishing.application import ports
from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.application.ports import GameRepository, StoredGame
from mtg_goldfishing.domain.events import ErrorKind, Refused
from mtg_goldfishing.domain.game import seats
from mtg_goldfishing.domain.game.model import Game
from tests.support.builders import a_game
from tests.support.service import GAME_ID, ServiceHarness, a_service

not_built = pytest.mark.xfail(strict=True, reason="M2: seats inside the game are not built")

# The seat model is reached untyped here, so the tests read the same before and after it exists.
SeatNumber: Any = seats.SeatNumber
SeatId: Any = seats.SeatId
PORTS: Any = ports

ANOTHER_ID = "ganotherid"


class KnownByAnotherId(GameRepository):
    """A game repository in which one more seat id names the tested seat of the stored game."""

    def __init__(self, inner: InMemoryGameRepository) -> None:
        self._inner: Any = inner

    def get(self, game_id: str) -> StoredGame | None:
        return self._inner.get(game_id)

    def find_seat(self, seat_id: Any) -> Any:
        if seat_id == SeatId(ANOTHER_ID):
            return PORTS.SeatOfGame(GAME_ID, SeatNumber(1))
        return self._inner.find_seat(seat_id)

    def add(self, game: Game) -> None:
        self._inner.add(game)

    def save(self, game: Game, *, version: int) -> bool:
        return bool(self._inner.save(game, version=version))


def a_game_known_by_another_id() -> ServiceHarness:
    harness = a_service(games=KnownByAnotherId)
    harness.holding(a_game().with_hand("Forest").build())
    return harness


# @spec APP-053
@not_built
def test_a_changing_call_is_applied_to_the_game_whose_seat_its_id_names() -> None:
    harness = a_game_known_by_another_id()

    answer = harness.service.play({"game_id": ANOTHER_ID, "card": "Forest"})

    game: Any = harness.game()
    assert answer.outcome.status is Status.OK
    assert [card.name for card in game.battlefield_of(SeatNumber(1))] == ["Forest"]


# @spec APP-053
@not_built
def test_a_read_only_call_is_answered_about_the_game_whose_seat_its_id_names() -> None:
    harness = a_game_known_by_another_id()

    answer = harness.service.get_state({"game_id": ANOTHER_ID})

    assert answer.outcome.status is Status.OK
    assert answer.outcome.game is not None
    assert answer.outcome.game.game_id == GAME_ID


# @spec APP-053
@not_built
def test_a_call_made_with_a_seat_id_is_recorded_under_the_game_it_names() -> None:
    harness = a_game_known_by_another_id()

    harness.service.play({"game_id": ANOTHER_ID, "card": "Forest"})

    assert harness.last_call().game_id == GAME_ID
    assert [entry.tool for entry in harness.records().entries] == ["play"]


# @spec APP-054
@pytest.mark.parametrize("tool", ["get_state", "get_log", "advance", "end_game"])
def test_a_call_whose_id_names_no_seat_is_an_error_with_no_game_summary(tool: str) -> None:
    harness = a_service()
    harness.holding(a_game().build())

    answer = getattr(harness.service, tool)({"game_id": "gnosuchseat", "result": "win"})

    assert isinstance(answer.outcome.summary, Refused)
    assert [error.kind for error in answer.outcome.summary.errors] == [ErrorKind.UNKNOWN_GAME]
    assert (answer.outcome.status, answer.outcome.game) == (Status.ERROR, None)


# @spec APP-054
def test_a_call_whose_id_names_no_seat_changes_no_game() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    before = harness.game()

    harness.service.end_game({"game_id": "gnosuchseat", "result": "win"})

    assert (harness.game(), harness.version()) == (before, 1)


# @spec GAME-076
@not_built
def test_a_new_goldfish_game_s_tested_seat_is_named_by_the_game_id() -> None:
    harness = a_service(game_ids=("abcdefghij",))
    harness.started_game()

    game: Any = harness.game("gabcdefghij")
    repository: Any = harness.stores.games
    found = repository.find_seat(SeatId("gabcdefghij"))

    assert game.tested.seat_id == SeatId("gabcdefghij")
    assert (found.game_id, found.seat) == ("gabcdefghij", SeatNumber(1))


# @spec APP-045
@not_built
def test_the_game_repository_port_finds_the_game_and_seat_number_a_seat_id_names() -> None:
    assert "find_seat" in ports.GameRepository.__abstractmethods__


# @spec APP-030
def test_no_port_saves_or_loads_a_seat_on_its_own() -> None:
    annotations = " ".join(
        str(annotation)
        for _, port in inspect.getmembers(ports, inspect.isclass)
        if inspect.isabstract(port)
        for name in port.__abstractmethods__
        for annotation in inspect.get_annotations(getattr(port, name)).values()
    )

    assert re.search(r"\bGame\b", annotations)
    assert not re.search(r"\bSeat\b", annotations)
