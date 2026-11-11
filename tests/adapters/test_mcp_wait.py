"""The `wait` tool as an agent sees it: its parameters, and a timeout of the wrong shape."""

from __future__ import annotations

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.mcp.tools import ToolSurface
from tests.support.builders import a_game
from tests.support.service import ServiceHarness, a_service

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")


def _surface() -> tuple[ToolSurface, ServiceHarness]:
    harness = a_service(renderer=TextRenderer())
    return ToolSurface(harness.service), harness


# @spec APP-072
@NOT_BUILT
def test_wait_takes_the_seat_s_id_first_and_an_optional_timeout() -> None:
    surface, _ = _surface()
    parameters = surface.definition("wait").parameters
    assert [(p.name, p.required) for p in parameters] == [("game_id", True), ("timeout", False)]


# @spec APP-090
@NOT_BUILT
def test_wait_declares_its_timeout_as_any_json_number() -> None:
    surface, _ = _surface()
    schema = surface.definition("wait").input_schema
    assert schema["properties"]["timeout"] == {"type": "number"}  # type: ignore[index]


# @spec APP-090
@NOT_BUILT
def test_a_wait_whose_timeout_is_not_a_number_is_a_malformed_argument() -> None:
    surface, harness = _surface()
    game_id = harness.holding(a_game().build())
    response = surface.call("wait", {"game_id": game_id, "timeout": "soon"})
    assert response.is_error
    assert response.text.startswith("ERROR ")
    assert "timeout" in response.text.splitlines()[0]
    assert harness.last_call().tool == "wait"


# @spec APP-090, APP-074
@NOT_BUILT
def test_a_goldfish_wait_with_a_fractional_timeout_answers_at_once() -> None:
    surface, harness = _surface()
    game_id = harness.holding(a_game().build())
    response = surface.call("wait", {"game_id": game_id, "timeout": 1.5})
    assert response.text.startswith("OK You are asked to take your turn.")
