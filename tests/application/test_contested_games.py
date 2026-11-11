"""Contested games through the use cases: starting one, acting as a seat, the seat to act, what
each seat is shown, and the records that name seats."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.domain.events import AlreadyApplied, Refused
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from tests.support.service import ServiceHarness, a_service

IDS = ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "dddddddddd")
GAME = "gaaaaaaaaaa"
S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)


def contested(opposing: int = 1, **arguments: object) -> ServiceHarness:
    """A service holding a contested game started with the tested seat first in turn order."""
    harness = a_service(game_ids=IDS, seeds=(77,))
    game_id = harness.started_contested_game(opposing, position=1, seed=11, **arguments)
    assert game_id == GAME
    assert len(harness.game(GAME).seats) == opposing + 1
    return harness


def started(harness: ServiceHarness) -> None:
    """Every seat keeps, so seat 1 takes turn 1."""
    for seat in harness.game(GAME).seats:
        answer = harness.service.mulligan({"game_id": seat.seat_id.value, "keep": True})
        assert answer.outcome.status is Status.OK, answer


def call_as(harness: ServiceHarness, seat: int, tool: str, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME, seat)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def error_kinds(answer: Answer) -> list[str]:
    summary = answer.outcome.summary
    assert isinstance(summary, Refused), answer
    return [error.kind.value for error in summary.errors]


# ------------------------------------------------------------------ starting a contested game


# @spec APP-061, APP-087, GAME-077
def test_new_game_takes_the_game_id_then_the_seed_then_a_seat_id_per_opponent_in_order() -> None:
    harness = a_service(game_ids=IDS, seeds=(77,))
    other = harness.loaded_opposing_deck_id()
    harness.service.new_game(
        {"deck_id": harness.loaded_deck_id(), "opponents": [other, other, other]}
    )
    game = harness.game(GAME)
    ids = {seat.shuffle_key: seat.seat_id.value for seat in game.seats}
    assert game.seed == 77
    assert ids == {"": GAME, "o1": "gbbbbbbbbbb", "o2": "gcccccccccc", "o3": "gdddddddddd"}


# @spec GAME-077
def test_each_opposing_seat_id_names_its_seat_of_the_new_game() -> None:
    harness = contested(opposing=2)
    repository: Any = harness.stores.games
    for seat in harness.game(GAME).seats:
        found = repository.find_seat(SeatId(seat.seat_id.value))
        assert (found.game_id, found.seat) == (GAME, seat.number)


# @spec GAME-059
def test_an_opponent_naming_no_loaded_deck_starts_no_game() -> None:
    harness = a_service(game_ids=IDS)
    answer = harness.service.new_game(
        {"deck_id": harness.loaded_deck_id(), "opponents": ["dnosuchdeck"]}
    )
    assert error_kinds(answer) == ["unknown_deck"]
    assert harness.stores.games.get(GAME) is None


# @spec GAME-075
def test_the_new_game_outcome_of_a_contested_game_lists_seats_not_a_hand() -> None:
    harness = a_service(game_ids=IDS, seeds=(77,))
    other = harness.loaded_opposing_deck_id()
    answer = harness.service.new_game({"deck_id": harness.loaded_deck_id(), "opponents": [other]})
    summary: Any = answer.outcome.summary
    assert [seat.seat_id for seat in summary.seats] != []
    assert not hasattr(summary, "hand")


# ------------------------------------------------------------------ acting as a seat


# @spec APP-034, GAME-078
def test_the_outcome_of_a_call_made_with_a_seat_id_holds_that_seat_s_number() -> None:
    harness = contested()
    outcome: Any = call_as(harness, 2, "mulligan", keep=False).outcome
    assert outcome.seat == S2


# @spec APP-034
def test_the_outcome_of_a_goldfish_call_holds_no_seat_number() -> None:
    harness = a_service(game_ids=IDS)
    harness.started_game()
    outcome: Any = harness.service.mulligan({"game_id": GAME, "keep": False}).outcome
    assert outcome.seat is None


# @spec APP-035, GAME-078
def test_the_outcome_s_game_summary_is_the_calling_seat_s_view() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    answer = call_as(harness, 2, "get_state")
    game: Any = answer.outcome.game
    assert (game.table.seat, game.mulligans) == (S2, 1)


# @spec GAME-078
def test_a_mulligan_made_with_an_opposing_seat_id_is_that_seat_s() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    assert [seat.mulligans for seat in harness.game(GAME).seats] == [0, 1]


# ------------------------------------------------------------------ the seat to act


# @spec APP-056, GAME-118
def test_a_call_from_a_seat_that_is_not_to_act_is_an_error_that_changes_nothing() -> None:
    harness = contested()
    started(harness)
    before = harness.game(GAME)
    answer = call_as(harness, 2, "advance")
    assert answer.outcome.status is Status.ERROR
    assert error_kinds(answer) == ["not_your_call"]
    assert harness.game(GAME) == before
    assert harness.last_call().tool == "advance"
    assert [entry.tool for entry in harness.records(GAME).entries][-1] == "mulligan"


# @spec TURN-043
def test_an_advance_from_a_seat_that_is_not_the_active_seat_does_not_move_the_game() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 2, "advance", to="end")
    assert harness.game(GAME).step is not None
    assert harness.game(GAME).step.value == "main1"


# @spec APP-055
def test_a_resend_is_answered_although_the_seat_is_no_longer_to_act() -> None:
    harness = contested(draw_first_turn=False)
    started(harness)
    change = harness.game(GAME).change
    first = call_as(harness, 1, "advance", to="cleanup", after=change)
    assert first.outcome.status is Status.OK
    passing = call_as(harness, 1, "advance", after=change + 1)
    assert passing.outcome.status is Status.OK
    resent = call_as(harness, 1, "advance", after=change + 1)
    assert resent.outcome.status is Status.OK
    assert any(isinstance(event, AlreadyApplied) for event in resent.outcome.events)


# @spec APP-085
def test_a_seat_not_to_act_with_a_stale_change_number_is_told_it_is_not_its_call() -> None:
    harness = contested()
    started(harness)
    assert error_kinds(call_as(harness, 2, "advance", after=0)) == ["not_your_call"]


# @spec APP-086
def test_a_seat_to_act_with_a_stale_change_number_is_told_so_before_a_malformed_delta() -> None:
    harness = contested()
    started(harness)
    answer = call_as(harness, 1, "effect", source="x", delta={"bogus": 1}, after=0)
    assert error_kinds(answer) == ["stale_change"]


# ------------------------------------------------------------------ what each seat is shown


# @spec GAME-107, GAME-088
def test_the_seat_whose_keep_starts_the_game_is_not_told_what_the_first_seat_drew() -> None:
    harness = contested()
    call_as(harness, 1, "mulligan", keep=True)
    before = harness.game(GAME)
    drawn = before.instance(before.seat(S1).library[0]).name
    answer = call_as(harness, 2, "mulligan", keep=True)
    assert f"'{drawn}'" not in repr(answer.outcome.events)
    assert harness.game(GAME).step is not None


# @spec TURN-042, GAME-088
def test_the_seat_whose_advance_passes_the_turn_is_not_told_what_the_next_seat_drew() -> None:
    harness = contested()
    started(harness)
    before = harness.game(GAME)
    drawn = before.instance(before.seat(S2).library[0]).name
    answer = call_as(harness, 1, "advance", to="main1", discard=[before.hand_of(S1)[0].id])
    assert harness.game(GAME).active == S2
    assert f"'{drawn}'" not in repr((answer.outcome.summary, answer.outcome.events))


# ------------------------------------------------------------------ records naming seats


# @spec REC-052
def test_a_contested_game_s_call_records_name_the_calling_seat() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    call_as(harness, 1, "get_state")
    calls: Any = harness.calls()[-2:]
    assert [call.seat for call in calls] == [S2, S1]


# @spec REC-052
def test_a_malformed_call_of_a_contested_game_is_recorded_with_its_seat() -> None:
    harness = contested()
    harness.service.malformed_call("mulligan", {"game_id": harness.seat_id(GAME, 2)}, ["keep"])
    call: Any = harness.last_call()
    assert call.seat == S2


# @spec REC-051
def test_a_call_made_with_an_opposing_seat_id_is_recorded_under_the_game_id() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    assert harness.last_call().game_id == GAME


# @spec STOR-021
def test_a_goldfish_game_s_call_records_name_no_seat() -> None:
    harness = a_service(game_ids=IDS)
    harness.started_game()
    harness.service.get_state({"game_id": GAME})
    assert {getattr(call, "seat", None) for call in harness.calls()} == {None}


# @spec REC-055, GAME-152
def test_every_seat_reads_the_same_whole_log() -> None:
    harness = contested()
    started(harness)
    arguments = {"include_calls": True}
    by_tested = call_as(harness, 1, "get_log", **arguments).outcome.payload
    by_opposing = call_as(harness, 2, "get_log", **arguments).outcome.payload
    assert isinstance(by_tested, dict)
    assert isinstance(by_opposing, dict)
    assert by_tested["entries"] == by_opposing["entries"]
    assert by_tested["calls"] == by_opposing["calls"][:-1]
    hands = [e for e in by_opposing["entries"] if e["tool"] == "mulligan"]
    assert len(hands) == 2


# @spec GAME-152, REC-055
def test_every_seat_reads_the_whole_log_after_the_game_has_ended() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 1, "end_game", result="stalled")
    by_tested = call_as(harness, 1, "get_log").outcome.payload
    answer = call_as(harness, 2, "get_log")
    assert answer.outcome.status is Status.OK
    assert isinstance(by_tested, dict)
    assert answer.outcome.payload == by_tested


# @spec GAME-079
def test_no_response_but_new_game_s_names_an_opposing_seat_by_its_seat_id() -> None:
    harness = a_service(renderer=TextRenderer(), game_ids=IDS, seeds=(77,))
    harness.started_contested_game(2, position=1, seed=11)
    started(harness)
    call_as(harness, 1, "advance", to="main1", discard=[harness.game(GAME).hand_of(S1)[0].id])
    call_as(harness, 3, "get_state")
    responses = [call.response for call in harness.calls() if call.tool != "new_game"]
    opposing = [harness.seat_id(GAME, 2), harness.seat_id(GAME, 3)]
    assert len(responses) >= 5
    assert not any(seat_id in text for text in responses for seat_id in opposing)
