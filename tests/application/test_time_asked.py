"""How long the seats to act have been asked: the time a seat that is not to act is given, from
the call record of the change since which they have been asked to the clock's now."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from mtg_goldfishing.adapters.memory.clock import DEFAULT_TIME
from mtg_goldfishing.application.outcome import Answer
from tests.application.test_wait import (
    GAME,
    IDS,
    ImpatientChanges,
    call_as,
    contested,
    started,
    summary_of,
    waited,
)
from tests.support.builders import a_game
from tests.support.service import a_service

NO_FIELD = "the game summary holds no time asked at all"


def time_asked(answer: Answer) -> object:
    game: Any = answer.outcome.game
    assert game is not None, answer
    assert game.table is not None, answer
    return vars(game.table).get("time_asked", NO_FIELD)


def later(harness: Any, **elapsed: float) -> None:
    harness.clock.set(DEFAULT_TIME + timedelta(**elapsed))


# @spec APP-094
def test_a_seat_not_to_act_is_given_the_whole_seconds_the_seat_to_act_has_been_asked() -> None:
    harness = contested()
    started(harness)
    later(harness, minutes=4, seconds=30.9)

    assert time_asked(call_as(harness, 2, "get_state")) == 270


# @spec APP-094
def test_the_time_asked_counts_from_the_change_since_which_the_seat_to_act_is_asked() -> None:
    harness = contested()
    started(harness)
    later(harness, minutes=2)
    call_as(harness, 1, "effect", source="a test effect", delta={"life": 1})
    later(harness, minutes=3)

    assert time_asked(call_as(harness, 2, "get_state")) == 180


# @spec APP-094
def test_a_change_that_asks_another_seat_is_answered_with_that_seat_asked_for_no_time() -> None:
    harness = contested()
    started(harness)
    later(harness, minutes=2)

    answer = call_as(
        harness, 1, "effect", source="Duress", delta={"ask": [{"seats": [2], "text": "discard"}]}
    )

    assert time_asked(answer) == 0


# @spec APP-094
def test_a_clock_set_back_since_the_change_gives_no_less_than_no_time() -> None:
    harness = contested()
    started(harness)
    later(harness, seconds=-90)

    assert time_asked(call_as(harness, 2, "get_state")) == 0


# @spec APP-094
def test_an_error_to_a_seat_not_to_act_carries_the_time_asked() -> None:
    harness = contested()
    started(harness)
    later(harness, seconds=45)

    assert time_asked(call_as(harness, 2, "advance")) == 45


# @spec APP-094
def test_during_mulligans_a_seat_that_has_kept_is_given_the_time_since_the_game_began() -> None:
    harness = contested(opposing=2)
    later(harness, minutes=1)
    call_as(harness, 2, "mulligan", keep=True)
    later(harness, minutes=2)

    assert time_asked(call_as(harness, 2, "get_state")) == 120


# @spec APP-095
def test_a_seat_to_act_is_given_no_time_asked() -> None:
    harness = contested()
    started(harness)
    later(harness, minutes=4)

    assert time_asked(call_as(harness, 1, "get_state")) is None


# @spec APP-095
def test_a_game_that_has_ended_gives_no_time_asked() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 1, "end_game", result="win")

    assert time_asked(call_as(harness, 2, "get_state")) is None


# @spec APP-095
def test_a_game_that_holds_no_asked_since_change_gives_no_time_asked() -> None:
    harness = a_service()
    game_id = harness.holding(a_game().and_an_opposing_seat().build())

    assert time_asked(call_as_seat(harness, game_id, 2)) is None


# @spec APP-095
def test_a_change_no_call_record_holds_gives_no_time_asked() -> None:
    harness = a_service()
    situation = a_game().and_an_opposing_seat().build()
    held: Any = situation.game
    held.asked_since = 3
    game_id = harness.holding(situation)

    assert time_asked(call_as_seat(harness, game_id, 2)) is None


def call_as_seat(harness: Any, game_id: str, seat: int) -> Answer:
    answer: Answer = harness.service.get_state({"game_id": harness.seat_id(game_id, seat)})
    return answer


# @spec APP-095
def test_a_goldfish_game_s_summary_holds_no_table_and_so_no_time_asked() -> None:
    harness = a_service(game_ids=IDS)
    harness.started_game()

    answer = harness.service.get_state({"game_id": GAME})

    assert answer.outcome.game is not None
    assert vars(answer.outcome.game).get("time_asked") is None
    assert answer.outcome.game.table is None


# @spec APP-096
def test_a_wait_that_times_out_says_how_long_the_seat_to_act_has_been_asked() -> None:
    harness = contested(changes=ImpatientChanges())
    started(harness)
    later(harness, minutes=4)

    _, summary = summary_of(waited(harness, 2, timeout=1))

    assert vars(summary).get("time_asked", NO_FIELD) == 240


# @spec APP-096
def test_a_wait_that_times_out_on_a_game_holding_no_asked_since_change_says_no_time() -> None:
    harness = a_service(changes=ImpatientChanges())
    game_id = harness.holding(a_game().and_an_opposing_seat().build())

    answer = harness.service.wait({"game_id": harness.seat_id(game_id, 2), "timeout": 1})

    assert vars(answer.outcome.summary).get("time_asked", NO_FIELD) is None
