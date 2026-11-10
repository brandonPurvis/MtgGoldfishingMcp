"""The tools of a contested game as an agent sees them: how `new_game` takes opposing decks,
starting life and the tested seat's position, and how every seat passes its seat id."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.definitions import TOOL_DEFINITIONS
from mtg_goldfishing.adapters.mcp.parameters import Shaped, shape
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.mcp.tools import ToolSurface
from tests.support.service import a_service

M3A = "M3a: contested games are not built into the tools"
DEFINITIONS = {definition.name: definition for definition in TOOL_DEFINITIONS}
GAME_SCOPED = [d for d in TOOL_DEFINITIONS if d.name not in ("load_deck", "new_game")]


def parameter(tool: str, name: str) -> Any:
    return next(p for p in DEFINITIONS[tool].parameters if p.name == name)


# @spec TOOL-031
@pytest.mark.parametrize("definition", GAME_SCOPED, ids=lambda d: d.name)
def test_no_tool_has_a_separate_seat_id_parameter(definition: Any) -> None:
    names = [p.name for p in definition.parameters]
    assert names[0] == "game_id"
    assert "seat_id" not in names


# @spec TOOL-031
@pytest.mark.xfail(strict=True, reason=M3A)
@pytest.mark.parametrize("definition", GAME_SCOPED, ids=lambda d: d.name)
def test_game_id_is_described_as_the_id_new_game_gave_the_calling_seat(definition: Any) -> None:
    game_id = definition.parameters[0]
    assert "seat id" in game_id.meaning


# @spec TOOL-033
@pytest.mark.xfail(strict=True, reason=M3A)
def test_new_game_s_contested_parameters_follow_the_goldfish_ones_marked_contested_games() -> None:
    names = [p.name for p in DEFINITIONS["new_game"].parameters]
    assert names[-2:] == ["opponents", "position"]
    for name in ("opponents", "position"):
        assert parameter("new_game", name).meaning.startswith("Contested games: ")
    assert "Contested games: " in parameter("new_game", "starting_life").meaning


# @spec GAME-066, GAME-067
@pytest.mark.xfail(strict=True, reason=M3A)
@pytest.mark.parametrize("value", [30, [40, 30], "[40, 30]"])
def test_starting_life_is_taken_as_one_number_or_a_list(value: object) -> None:
    shaped = shape(DEFINITIONS["new_game"].parameters, {"deck_id": "d1", "starting_life": value})
    assert isinstance(shaped, Shaped), shaped


# @spec GAME-056
@pytest.mark.xfail(strict=True, reason=M3A)
def test_opponents_and_position_are_taken_by_new_game() -> None:
    shaped = shape(
        DEFINITIONS["new_game"].parameters,
        {"deck_id": "d1", "opponents": ["d2", "d3"], "position": 2},
    )
    assert isinstance(shaped, Shaped), shaped
    assert shaped.arguments["opponents"] == ["d2", "d3"]


# @spec GAME-056, GAME-074
@pytest.mark.xfail(strict=True, reason=M3A)
def test_new_game_with_opponents_answers_with_the_seats_of_a_contested_game() -> None:
    harness = a_service(
        renderer=TextRenderer(), game_ids=("abcdefghij", "seatone001", "seattwo002")
    )
    tools = ToolSurface(harness.service)
    tested, other = harness.loaded_deck_id(), harness.loaded_opposing_deck_id()
    answer = tools.call(
        "new_game", {"deck_id": tested, "opponents": [other, other], "seed": 5, "position": 1}
    )
    lines = answer.text.splitlines()
    assert lines[0] == "OK Started contested game gabcdefghij with seed 5. Seats in turn order:"
    assert lines[1] == f"S1 gabcdefghij: deck {tested}, life 40, the tested seat."
    assert sorted(lines[2:4]) == [
        f"S2 gseatone001: deck {other}, life 40.",
        f"S3 gseattwo002: deck {other}, life 40.",
    ] or sorted(lines[2:4]) == [
        f"S2 gseattwo002: deck {other}, life 40.",
        f"S3 gseatone001: deck {other}, life 40.",
    ]
