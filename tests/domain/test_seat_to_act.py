"""The seat to act: which seats a contested game is waiting on, and which calls it accepts from
each seat."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.model import GameStatus
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import Situation, a_game

S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)
CHANGING = ("mulligan", "play", "effect", "choose", "attack", "advance")


def mulligans_of_three(*, kept: tuple[bool, bool, bool]) -> Situation:
    builder: Any = a_game().in_mulligan().with_hand("Forest").having_kept(kept[0])
    builder = builder.and_an_opposing_seat().with_hand("Island").having_kept(kept[1])
    return builder.and_an_opposing_seat().with_hand("Swamp").having_kept(kept[2]).build()


def two_seats_in_turn_of(seat: int, step: Step = Step.MAIN1) -> Situation:
    builder: Any = a_game().in_step(step).in_turn_of(seat).with_library(*("Forest",) * 4)
    return builder.and_an_opposing_seat().with_library(*("Island",) * 4).build()


def with_a_look_pending(situation: Situation, seat: SeatNumber) -> Situation:
    result = effect(
        situation.game,
        situation.deck,
        seat,
        source="a look",
        delta={"look": {"n": 2, "rest": "library_bottom"}},
    )
    assert isinstance(result, Applied), result
    situation.game = result.game
    return situation


def asked(situation: Situation) -> Any:
    return acting.seats_to_act(situation.game)


def refusal(situation: Situation, seat: SeatNumber, tool: str) -> Any:
    error: Any = acting.may_call(situation.game, seat, tool)
    assert error is not None, f"{tool} from {seat} was accepted"
    return error


def accepted(situation: Situation, seat: SeatNumber, tool: str) -> bool:
    return acting.may_call(situation.game, seat, tool) is None


# ------------------------------------------------------------------ who the game waits on


# @spec GAME-108
def test_during_mulligans_every_seat_that_has_not_kept_is_a_seat_to_act() -> None:
    waiting = asked(mulligans_of_three(kept=(False, True, False)))
    assert (waiting.seats, waiting.kind.value) == ((S1, S3), "keep")


# @spec GAME-108
def test_an_eliminated_seat_is_not_waited_on_for_its_mulligan() -> None:
    builder: Any = a_game().in_mulligan().with_hand("Forest")
    situation = builder.and_an_opposing_seat().with_hand("Island").eliminated().build()
    assert asked(situation).seats == (S1,)


# @spec GAME-113
@pytest.mark.parametrize("seat", [1, 2])
def test_with_nothing_else_waiting_the_active_seat_is_the_seat_to_act(seat: int) -> None:
    waiting = asked(two_seats_in_turn_of(seat))
    assert (waiting.seats, waiting.kind.value) == ((SeatNumber(seat),), "turn")


# @spec GAME-109
def test_a_waiting_pending_choice_makes_the_seat_it_is_addressed_to_the_seat_to_act() -> None:
    situation = with_a_look_pending(two_seats_in_turn_of(2), S2)
    waiting = asked(situation)
    assert (waiting.seats, waiting.kind.value, waiting.choice) == ((S2,), "choice", "look")


# @spec GAME-120
def test_a_contested_game_waiting_on_a_pending_choice_has_status_pending_choice() -> None:
    situation = with_a_look_pending(two_seats_in_turn_of(2), S2)
    assert situation.game.status is GameStatus.PENDING_CHOICE


# ------------------------------------------------------------------ calls from the seats


# @spec GAME-102
def test_every_seat_that_has_not_kept_may_take_its_mulligan() -> None:
    situation = mulligans_of_three(kept=(False, True, False))
    assert accepted(situation, S1, "mulligan")
    assert accepted(situation, S3, "mulligan")


# @spec GAME-104, GAME-118
def test_a_seat_that_has_kept_may_not_take_a_mulligan() -> None:
    error = refusal(mulligans_of_three(kept=(False, True, False)), S2, "mulligan")
    assert error.kind.value == "not_your_call"
    assert (error.asked.seats, error.asked.kind.value) == ((S1, S3), "keep")


# @spec GAME-118, TURN-043
@pytest.mark.parametrize("tool", CHANGING)
def test_a_seat_that_is_not_the_seat_to_act_may_make_no_changing_call(tool: str) -> None:
    error = refusal(two_seats_in_turn_of(1), S2, tool)
    assert error.kind.value == "not_your_call"
    assert (error.asked.seats, error.asked.kind.value) == ((S1,), "turn")


# @spec GAME-118
@pytest.mark.parametrize("tool", ["play", "advance", "choose"])
def test_a_seat_still_to_keep_may_only_take_its_mulligan(tool: str) -> None:
    error = refusal(mulligans_of_three(kept=(False, True, False)), S1, tool)
    assert error.kind.value == "not_accepted_now"
    assert error.asked.kind.value == "keep"


# @spec GAME-114
@pytest.mark.parametrize("tool", ["get_state", "get_log"])
def test_any_seat_may_read_the_game_whatever_it_waits_on(tool: str) -> None:
    for situation in (mulligans_of_three(kept=(True, True, False)), two_seats_in_turn_of(1)):
        assert all(accepted(situation, seat.number, tool) for seat in situation.game.seats)


# @spec GAME-114
def test_an_eliminated_seat_may_read_the_game() -> None:
    builder: Any = a_game().with_library("Forest")
    situation = builder.and_an_opposing_seat().eliminated().build()
    assert accepted(situation, S2, "get_state")
    assert accepted(situation, S2, "get_log")


# @spec GAME-115
def test_only_the_seat_a_pending_choice_is_addressed_to_may_answer_it() -> None:
    situation = with_a_look_pending(two_seats_in_turn_of(1), S1)
    assert accepted(situation, S1, "choose")
    error = refusal(situation, S2, "choose")
    assert error.kind.value == "not_your_call"
    assert (error.asked.seats, error.asked.choice) == ((S1,), "look")


# @spec GAME-116
@pytest.mark.parametrize("tool", ["play", "effect"])
def test_a_seat_other_than_the_active_seat_may_not_play_while_nothing_asks_it(tool: str) -> None:
    assert refusal(two_seats_in_turn_of(2), S1, tool).kind.value == "not_your_call"


# @spec GAME-117
@pytest.mark.parametrize("tool", ["play", "effect", "attack", "advance"])
def test_the_active_seat_may_take_its_turn_while_it_is_the_seat_to_act(tool: str) -> None:
    assert accepted(two_seats_in_turn_of(2), S2, tool)


# @spec GAME-117
@pytest.mark.parametrize("tool", ["play", "effect", "attack", "advance"])
def test_the_active_seat_answers_its_pending_choice_before_anything_else(tool: str) -> None:
    situation = with_a_look_pending(two_seats_in_turn_of(2), S2)
    error = refusal(situation, S2, tool)
    assert error.kind.value == "not_accepted_now"
    assert (error.asked.kind.value, error.asked.choice) == ("choice", "look")


# @spec GAME-119
@pytest.mark.parametrize("tool", ["mulligan", "play", "advance", "end_game"])
def test_an_eliminated_opposing_seat_may_make_no_changing_call(tool: str) -> None:
    builder: Any = a_game().with_library("Forest")
    situation = builder.and_an_opposing_seat().eliminated().build()
    assert refusal(situation, S2, tool).kind.value == "seat_eliminated"


# @spec GAME-119, GAME-149
def test_an_eliminated_tested_seat_may_still_end_the_game() -> None:
    builder: Any = a_game().eliminated().in_turn_of(2).with_library("Forest")
    situation = builder.and_an_opposing_seat().build()
    assert accepted(situation, S1, "end_game")
    assert refusal(situation, S1, "play").kind.value == "seat_eliminated"


# @spec GAME-148
def test_the_tested_seat_may_end_the_game_whatever_the_game_waits_on() -> None:
    for situation in (
        mulligans_of_three(kept=(True, False, False)),
        two_seats_in_turn_of(2),
        with_a_look_pending(two_seats_in_turn_of(2), S2),
    ):
        assert accepted(situation, S1, "end_game")


# @spec GAME-150
@pytest.mark.parametrize("tool", [*CHANGING, "end_game"])
def test_an_ended_game_accepts_no_changing_call_from_any_seat(tool: str) -> None:
    situation = two_seats_in_turn_of(1)
    situation.game.status = GameStatus.ENDED
    for seat in (S1, S2):
        assert refusal(situation, seat, tool).kind.value == "not_accepted_in_status"


# @spec GAME-150
def test_an_ended_game_is_still_read_by_every_seat() -> None:
    situation = two_seats_in_turn_of(1)
    situation.game.status = GameStatus.ENDED
    assert all(accepted(situation, seat, "get_state") for seat in (S1, S2))
    assert all(accepted(situation, seat, "get_log") for seat in (S1, S2))


# @spec GAME-170
def test_an_ended_game_is_the_first_reason_given_for_a_refused_call() -> None:
    builder: Any = a_game().with_library("Forest")
    situation = builder.and_an_opposing_seat().eliminated().build()
    situation.game.status = GameStatus.ENDED
    assert refusal(situation, S2, "advance").kind.value == "not_accepted_in_status"


# @spec GAME-170
def test_an_eliminated_seat_comes_before_not_being_the_seat_to_act() -> None:
    builder: Any = a_game().with_library("Forest")
    situation = builder.and_an_opposing_seat().eliminated().build()
    assert refusal(situation, S2, "advance").kind.value == "seat_eliminated"


# ------------------------------------------------------------------ a goldfish game is unchanged


# @spec GAME-048, GAME-049, GAME-050, GAME-051
@pytest.mark.parametrize(
    ("status", "tool", "is_accepted"),
    [
        (GameStatus.MULLIGAN, "mulligan", True),
        (GameStatus.MULLIGAN, "play", False),
        (GameStatus.ACTIVE, "advance", True),
        (GameStatus.ACTIVE, "choose", False),
        (GameStatus.PENDING_CHOICE, "choose", True),
        (GameStatus.PENDING_CHOICE, "play", False),
        (GameStatus.ENDED, "get_log", True),
        (GameStatus.ENDED, "end_game", False),
    ],
)
def test_a_goldfish_game_accepts_calls_by_its_status_alone(
    status: GameStatus, tool: str, is_accepted: bool
) -> None:
    situation = a_game().build()
    situation.game.status = status
    assert accepted(situation, S1, tool) is is_accepted
    if not is_accepted:
        assert refusal(situation, S1, tool).kind.value == "not_accepted_in_status"
