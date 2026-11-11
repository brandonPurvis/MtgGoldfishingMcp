"""Every seat's state at the end of a contested game, through the use cases: recorded in the
tested seat's `end_game` entry, read through get_log, and shown in no response."""

from __future__ import annotations

import json
from typing import Any

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.support.decks import ATRAXA, OMNATH
from tests.support.service import ServiceHarness, a_service

IDS = ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc")
GAME = "gaaaaaaaaaa"
S1, S2 = SeatNumber(1), SeatNumber(2)


def contested() -> ServiceHarness:
    """A contested game of the tested seat's Atraxa deck against one Omnath deck."""
    harness = a_service(game_ids=IDS, seeds=(77,), renderer=TextRenderer())
    assert harness.started_contested_game(1, position=1, seed=11) == GAME
    return harness


def started(harness: ServiceHarness) -> None:
    for number in (1, 2):
        call_as(harness, number, "mulligan", keep=True)


def call_as(harness: ServiceHarness, number: int, tool: str, /, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME, number)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def end_game_entry(harness: ServiceHarness, reader: int = 2) -> dict[str, Any]:
    """The tested seat's end_game entry, as get_log gives it to seat `reader`."""
    document = json.loads(call_as(harness, reader, "get_log").response)
    (entry,) = [e for e in document["entries"] if e["tool"] == "end_game" and e["seat"] == 1]
    return dict(entry)


# @spec REC-097
def test_get_log_gives_every_seat_s_state_as_the_tested_seat_ended_the_game() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 1, "end_game", result="stalled", notes="even")
    game = harness.game(GAME)
    final = end_game_entry(harness)["outcome"]["final"]
    assert [(seat["seat"], seat["hand"]) for seat in final] == [
        (1, [card.name for card in game.hand_of(S1)]),
        (2, [card.name for card in game.hand_of(S2)]),
    ]


# @spec REC-097
def test_a_game_ended_during_mulligans_records_every_seat_s_hand() -> None:
    harness = contested()
    call_as(harness, 1, "end_game", result="stalled")
    game = harness.game(GAME)
    final = end_game_entry(harness)["outcome"]["final"]
    assert [seat["hand"] for seat in final] == [
        [card.name for card in game.hand_of(S1)],
        [card.name for card in game.hand_of(S2)],
    ]


# @spec REC-099
def test_commander_damage_taken_names_each_other_seat_s_commanders_from_its_deck() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 1, "end_game", result="stalled")
    final = end_game_entry(harness)["outcome"]["final"]
    assert [seat["commander_damage_taken"] for seat in final] == [
        {"2": {OMNATH: 0}},
        {"1": {ATRAXA: 0}},
    ]


# @spec REC-099, REC-100
def test_a_seat_that_conceded_is_recorded_with_empty_zones_and_its_commanders_still_named() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 2, "end_game", result="loss", notes="beaten")
    call_as(harness, 1, "end_game", result="win")
    tested, conceded = end_game_entry(harness)["outcome"]["final"]
    assert tested["commander_damage_taken"] == {"2": {OMNATH: 0}}
    assert conceded == {
        "seat": 2,
        "life": 40,
        "eliminated": True,
        "hand": [],
        "battlefield": [],
        "graveyard": [],
        "commander_damage_taken": {"1": {ATRAXA: 0}},
    }


# @spec REC-102
def test_the_end_game_response_does_not_show_final() -> None:
    harness = contested()
    started(harness)
    answer = call_as(harness, 1, "end_game", result="stalled", notes="even")
    assert answer.outcome.status is Status.OK
    assert answer.outcome.payload is None
    assert "final" not in answer.response


# @spec REC-055, REC-097
def test_every_seat_reads_the_same_final_through_get_log() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 1, "end_game", result="stalled")
    assert "final" in end_game_entry(harness, reader=1)["outcome"]
    assert end_game_entry(harness, reader=1) == end_game_entry(harness, reader=2)
