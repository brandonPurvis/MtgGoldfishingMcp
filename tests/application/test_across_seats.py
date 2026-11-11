"""Effects across seats through the use cases: choices addressed to a seat, what a seat is told
of another seat's reveal, conceding, and the status a call answers with."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.domain.events import CardsRevealed
from mtg_goldfishing.domain.game.model import GameStatus
from tests.support.builders import a_game
from tests.support.service import GAME_ID, ServiceHarness, a_service


def holding_three_seats() -> ServiceHarness:
    """A service holding a game in seat 1's turn; every seat holds an Island and a Lightning
    Bolt."""
    harness = a_service(renderer=TextRenderer())
    builder: Any = a_game().with_hand("Island", "Lightning Bolt")
    builder = builder.and_an_opposing_seat().with_hand("Island", "Lightning Bolt")
    builder = builder.and_an_opposing_seat().with_hand("Island", "Lightning Bolt")
    harness.holding(builder.build())
    return harness


def call_as(harness: ServiceHarness, seat: int, tool: str, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME_ID, seat)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def asking(harness: ServiceHarness, delta: object) -> Answer:
    return call_as(harness, 1, "effect", source="Mind Rot", delta=delta)


def waiting_choice(harness: ServiceHarness) -> str:
    return harness.game().pending[0].choice_id


# @spec PLAY-097, PLAY-099, GAME-109
def test_the_asked_seat_is_told_it_is_asked_and_answers_with_its_own_delta() -> None:
    harness = holding_three_seats()
    asking(harness, {"ask": [{"seats": [2], "text": "discard a card"}]})
    state = call_as(harness, 2, "get_state")
    assert "You are asked to answer the ask choice." in state.response.splitlines()
    answer = call_as(
        harness, 2, "choose", choice_id=waiting_choice(harness), delta={"discard": ["Island"]}
    )
    assert answer.outcome.status is Status.OK
    assert harness.game().pending == []


# @spec GAME-090, PLAY-116
def test_the_seat_whose_answer_opens_a_look_at_another_hand_is_not_shown_its_cards() -> None:
    harness = holding_three_seats()
    asking(harness, {"ask": [{"seats": [2], "text": "discard a card"}], "look_at_hand": 3})
    answer = call_as(harness, 2, "choose", choice_id=waiting_choice(harness), delta={})
    assert [e for e in answer.outcome.events if isinstance(e, CardsRevealed)] == []
    assert harness.game().pending[0].kind == "hand"


# @spec GAME-090, PLAY-102
def test_the_looking_seat_is_shown_the_hand_it_looks_at_with_a_choice() -> None:
    harness = holding_three_seats()
    answer = asking(harness, {"look_at_hand": 2})
    assert answer.outcome.status is Status.CHOICE
    assert any(isinstance(e, CardsRevealed) for e in answer.outcome.events)


# @spec GAME-131
def test_an_opposing_seat_s_end_game_concedes_and_the_game_is_not_ended() -> None:
    harness = holding_three_seats()
    answer = call_as(harness, 2, "end_game", result="loss", notes="beaten")
    assert answer.outcome.status is Status.OK
    game = harness.game()
    assert game.seat(game.seats[1].number).eliminated
    assert game.status is GameStatus.ACTIVE
    assert game.result is None


# @spec GAME-148
def test_the_tested_seat_ends_the_game_while_another_seat_owes_an_answer() -> None:
    harness = holding_three_seats()
    asking(harness, {"ask": [{"seats": [2], "text": "discard a card"}]})
    assert harness.game().pending
    answer = call_as(harness, 1, "end_game", result="win")
    assert answer.outcome.status is Status.OK
    assert harness.game().status is GameStatus.ENDED


# @spec GAME-119
def test_a_seat_that_conceded_may_make_no_further_changing_call() -> None:
    harness = holding_three_seats()
    call_as(harness, 2, "end_game", result="loss")
    answer = call_as(harness, 2, "end_game", result="loss")
    assert answer.outcome.status is Status.ERROR
    assert "Your seat has been eliminated" in answer.response
