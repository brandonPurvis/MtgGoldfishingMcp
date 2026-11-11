"""get_log's filters through the use case: which arguments narrow the export, and which are
refused with an error in the text format."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.domain.events import Refused
from tests.support.builders import a_game
from tests.support.service import ServiceHarness, a_service

IDS = ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc")
GAME = "gaaaaaaaaaa"
TOOLS_IN_ORDER = (
    "load_deck, new_game, mulligan, get_state, play, effect, choose, attack, advance, pass,"
    " wait, end_game, get_log"
)


def contested() -> ServiceHarness:
    """A contested game of two seats in which seat 2 took a mulligan before both kept."""
    harness = a_service(game_ids=IDS, seeds=(77,), renderer=TextRenderer())
    assert harness.started_contested_game(1, position=1, seed=11) == GAME
    call_as(harness, 2, "mulligan", keep=False)
    call_as(harness, 1, "mulligan", keep=True)
    call_as(harness, 2, "mulligan", keep=True)
    return harness


def goldfish() -> tuple[ServiceHarness, str]:
    """A goldfish game in which a Forest was played and the game advanced to main2."""
    harness = a_service(renderer=TextRenderer())
    game_id = harness.holding(a_game().with_hand("Forest").build())
    harness.service.play({"game_id": game_id, "card": "Forest"})
    harness.service.advance({"game_id": game_id, "to": "main2"})
    return harness, game_id


def call_as(harness: ServiceHarness, number: int, tool: str, /, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME, number)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def exported(answer: Answer) -> dict[str, Any]:
    assert answer.outcome.status is Status.OK, answer.response
    document: dict[str, Any] = json.loads(answer.response)
    return document


def error_kinds(answer: Answer) -> list[str]:
    summary = answer.outcome.summary
    assert isinstance(summary, Refused), answer.response
    return [error.kind.value for error in summary.errors]


def entry_seats(document: dict[str, Any]) -> list[tuple[str, int | None]]:
    return [(entry["tool"], entry["seat"]) for entry in document["entries"]]


# ------------------------------------------------------------------ narrowing the export


# @spec REC-089
def test_seat_keeps_the_records_of_the_seat_it_names_whichever_seat_calls() -> None:
    harness = contested()
    document = exported(call_as(harness, 1, "get_log", seat=2))
    assert entry_seats(document) == [("mulligan", 2), ("mulligan", 2)]


# @spec REC-055, REC-089, REC-090
def test_every_seat_reads_the_same_filtered_record_with_the_same_arguments() -> None:
    harness = contested()
    arguments: dict[str, object] = {"seat": 1, "tools": ["mulligan", "new_game"]}
    by_tested = exported(call_as(harness, 1, "get_log", **arguments))
    by_opposing = exported(call_as(harness, 2, "get_log", **arguments))
    assert by_tested == by_opposing
    assert entry_seats(by_tested) == [("mulligan", 1)]


# @spec REC-090
def test_tools_keeps_the_records_of_the_tools_it_names_in_a_goldfish_game() -> None:
    harness, game_id = goldfish()
    document = exported(harness.service.get_log({"game_id": game_id, "tools": ["play"]}))
    assert [entry["tool"] for entry in document["entries"]] == ["play"]


# @spec REC-090
def test_a_tool_named_twice_counts_once() -> None:
    harness = contested()
    twice = exported(call_as(harness, 1, "get_log", tools=["mulligan", "mulligan"]))
    once = exported(call_as(harness, 1, "get_log", tools=["mulligan"]))
    assert twice == once


# @spec REC-089, REC-090
def test_a_filter_given_as_null_is_no_filter() -> None:
    harness = contested()
    unfiltered = exported(call_as(harness, 1, "get_log"))
    assert exported(call_as(harness, 1, "get_log", seat=None, tools=None)) == unfiltered


# @spec REC-091
def test_since_seat_and_tools_together_keep_only_what_each_keeps() -> None:
    harness = contested()
    document = exported(call_as(harness, 1, "get_log", since=2, seat=2, tools=["mulligan"]))
    assert [entry["seq"] for entry in document["entries"]] == [4]


# @spec REC-089
def test_a_seat_that_made_no_call_gives_empty_sections_and_is_no_error() -> None:
    harness = a_service(game_ids=IDS, seeds=(77,), renderer=TextRenderer())
    harness.started_contested_game(1, position=1, seed=11)
    document = exported(call_as(harness, 1, "get_log", seat=2, include_calls=True))
    assert (document["entries"], document["snapshots"], document["calls"]) == ([], [], [])


# ------------------------------------------------------------------ filters refused


# @spec REC-093
def test_seat_in_a_goldfish_game_is_an_error() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "seat": 1})
    assert error_kinds(answer) == ["contested_only"]


# @spec REC-093
def test_the_error_for_seat_in_a_goldfish_game_says_it_is_for_contested_games() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "seat": 1})
    assert answer.response.splitlines()[0] == "ERROR seat is used only in a contested game."


# @spec REC-094
@pytest.mark.parametrize("seat", [0, 3, -1])
def test_a_seat_naming_none_of_the_game_s_seats_is_an_error(seat: int) -> None:
    harness = contested()
    answer = call_as(harness, 1, "get_log", seat=seat)
    assert error_kinds(answer) == ["no_such_seat"]


# @spec REC-094
def test_the_error_for_a_seat_naming_no_seat_lists_the_game_s_seat_numbers() -> None:
    harness = contested()
    answer = call_as(harness, 1, "get_log", seat=3)
    assert answer.response.splitlines()[0] == (
        "ERROR There is no seat S3 in this game. Its seat numbers are 1, 2."
    )


# @spec REC-094, REC-024
@pytest.mark.parametrize("seat", ["2", 1.5, True])
def test_a_seat_that_is_not_a_whole_number_is_a_malformed_argument(seat: object) -> None:
    harness = contested()
    answer = call_as(harness, 1, "get_log", seat=seat)
    assert error_kinds(answer) == ["malformed_argument"]


# @spec REC-095
@pytest.mark.parametrize("tools", [["plya"], ["Play"], ["play", 5], ["get_logs", "atack"]])
def test_tools_naming_anything_but_a_tool_of_the_service_is_an_error(tools: list[object]) -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "tools": tools})
    assert error_kinds(answer) == ["unknown_tool"]


# @spec REC-095
def test_the_error_for_unknown_tools_names_each_one_and_lists_the_tools_in_order() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "tools": ["play", "plya", "atack"]})
    assert answer.response.splitlines()[0] == (
        f"ERROR tools names plya, atack, which are not tools. The tools are {TOOLS_IN_ORDER}."
    )


# @spec REC-095
def test_tools_that_is_not_a_list_is_a_malformed_argument() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "tools": "play"})
    assert error_kinds(answer) == ["malformed_argument"]


# @spec REC-096
def test_an_empty_tools_is_an_error() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "tools": []})
    assert error_kinds(answer) == ["no_tools_named"]


# @spec REC-096
def test_the_error_for_an_empty_tools_lists_the_tools() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "tools": []})
    assert answer.response.splitlines()[0] == (
        f"ERROR tools names no tool; name at least one of {TOOLS_IN_ORDER}, or leave tools out."
    )


# @spec REC-093, REC-095
def test_every_filter_that_cannot_be_applied_is_named_in_one_error_response() -> None:
    harness, game_id = goldfish()
    answer = harness.service.get_log({"game_id": game_id, "seat": 2, "tools": ["plya"]})
    assert error_kinds(answer) == ["contested_only", "unknown_tool"]


# @spec REC-023
def test_a_refused_filter_changes_nothing() -> None:
    harness = contested()
    change = harness.game(GAME).change
    call_as(harness, 1, "get_log", seat=9)
    assert harness.game(GAME).change == change
