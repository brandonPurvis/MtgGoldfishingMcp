"""The records of a contested game through the use cases: one log naming each entry's seat,
the get_log header with every seat, and no opposing seat's seat id kept in any record."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.support.service import ServiceHarness, a_service

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
IDS = ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "dddddddddd")
GAME = "gaaaaaaaaaa"
SECOND = "gbbbbbbbbbb"
THIRD = "gcccccccccc"
S1, S2 = SeatNumber(1), SeatNumber(2)


def contested(opposing: int = 1, position: int = 1, **arguments: object) -> ServiceHarness:
    harness = a_service(game_ids=IDS, seeds=(77,), renderer=TextRenderer())
    started = harness.started_contested_game(opposing, position=position, seed=11, **arguments)
    assert started == GAME
    return harness


def call_as(harness: ServiceHarness, seat: int, tool: str, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME, seat)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def exported(harness: ServiceHarness, seat: int = 1, **arguments: object) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(call_as(harness, seat, "get_log", **arguments).response)
    return document


def started(harness: ServiceHarness) -> None:
    for seat in harness.game(GAME).seats:
        call_as(harness, seat.number.value, "mulligan", keep=True)


# ------------------------------------------------------------------ one log, naming seats


# @spec REC-027, REC-028, REC-060
@NOT_BUILT
def test_one_log_holds_every_seat_s_changes_in_change_order_each_naming_its_seat() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    call_as(harness, 1, "mulligan", keep=True)
    call_as(harness, 2, "mulligan", keep=True)
    entries = exported(harness)["entries"]
    assert [(entry["seq"], entry["seat"]) for entry in entries] == [
        (1, None),
        (2, 2),
        (3, 1),
        (4, 2),
    ]


# @spec REC-027
def test_the_log_keeps_what_each_seat_did_in_its_hidden_zones() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    (mulligan,) = [entry for entry in exported(harness)["entries"] if entry["tool"] == "mulligan"]
    hand = [card.name for card in harness.game(GAME).hand_of(S2)]
    assert mulligan["outcome"]["hand"] == hand


# @spec REC-060
@NOT_BUILT
def test_the_new_game_call_record_names_no_seat() -> None:
    harness = contested()
    (new_game,) = [call for call in harness.calls() if call.tool == "new_game"]
    assert new_game.seat is None
    assert exported(harness)["entries"][0]["seat"] is None


# ------------------------------------------------------------------ the get_log header


# @spec REC-056
@NOT_BUILT
def test_the_get_log_header_lists_every_seat_with_its_deck_life_and_standing() -> None:
    harness = contested(opposing=2, starting_life=[40, 30, 20])
    started(harness)
    call_as(harness, 3, "end_game", result="loss")
    header = exported(harness)["game"]
    opposing = harness.game(GAME).seats[1].deck_id
    tested = harness.game(GAME).tested.deck_id
    assert header["seats"] == [
        {
            "number": 1,
            "deck_id": tested,
            "tested": True,
            "starting_life": 40,
            "life": 40,
            "eliminated": False,
        },
        {
            "number": 2,
            "deck_id": opposing,
            "tested": False,
            "starting_life": 30,
            "life": 30,
            "eliminated": False,
        },
        {
            "number": 3,
            "deck_id": opposing,
            "tested": False,
            "starting_life": 20,
            "life": 20,
            "eliminated": True,
        },
    ]


# @spec REC-056, REC-063
@NOT_BUILT
def test_the_get_log_header_gives_the_tested_seat_s_turn_and_the_table_turn_and_round() -> None:
    harness = contested(position=2)
    started(harness)
    tested = harness.game(GAME).tested.number.value
    other = 3 - tested
    call_as(harness, other, "advance", to="cleanup")
    call_as(harness, other, "advance")
    header = exported(harness)["game"]
    assert (header["turn"], header["table_turn"], header["round"]) == (1, 2, 1)


# ------------------------------------------------------------------ no seat id in a record


# @spec REC-058
@NOT_BUILT
def test_a_call_made_with_an_opposing_seat_id_is_kept_under_the_game_id() -> None:
    harness = contested()
    call_as(harness, 2, "mulligan", keep=False)
    record = harness.last_call()
    (entry,) = [entry for entry in exported(harness)["entries"] if entry["seat"] == 2]
    assert record.arguments["game_id"] == GAME
    assert entry["arguments"]["game_id"] == GAME


# @spec REC-059
@NOT_BUILT
def test_the_new_game_call_record_keeps_its_response_with_opposing_seat_ids_redacted() -> None:
    harness = a_service(game_ids=IDS, seeds=(77,), renderer=TextRenderer())
    opposing = harness.loaded_opposing_deck_id()
    answer = harness.service.new_game(
        {"deck_id": harness.loaded_deck_id(), "opponents": [opposing], "position": 1}
    )
    (new_game,) = [call for call in harness.calls() if call.tool == "new_game"]
    assert SECOND in answer.response
    assert SECOND not in new_game.response
    assert new_game.response == answer.response.replace(SECOND, "[redacted]")


# @spec REC-057, REC-065
@NOT_BUILT
def test_an_opposing_seat_id_written_in_a_call_is_redacted_from_its_records() -> None:
    harness = contested(opposing=2)
    started(harness)
    call_as(harness, 1, "effect", source=f"note to {THIRD}", delta={"life": 1}, reason=SECOND)
    record = harness.last_call()
    entry = exported(harness)["entries"][-1]
    assert (record.arguments["source"], record.arguments["reason"]) == (
        "note to [redacted]",
        "[redacted]",
    )
    assert THIRD not in record.response
    assert (entry["reason"], entry["card"]) == ("[redacted]", "note to [redacted]")


# @spec REC-057
@NOT_BUILT
def test_no_record_of_a_contested_game_holds_an_opposing_seat_s_seat_id() -> None:
    harness = contested(opposing=2)
    started(harness)
    call_as(harness, 2, "get_state")
    call_as(harness, 3, "get_log")
    text = json.dumps(exported(harness, include_calls=True))
    assert (SECOND in text, THIRD in text) == (False, False)
