"""The tool surface: which tools an agent sees, their parameters, and how calls are shaped."""

import json

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.mcp.tools import ToolSurface
from tests.support.builders import a_game
from tests.support.service import ServiceHarness, a_service

TOOLS = (
    "load_deck",
    "new_game",
    "mulligan",
    "get_state",
    "play",
    "effect",
    "choose",
    "attack",
    "advance",
    "pass",
    "wait",
    "end_game",
    "get_log",
)
GAME_SCOPED = tuple(name for name in TOOLS if name not in ("load_deck", "new_game"))
CHANGING = ("mulligan", "play", "effect", "choose", "attack", "advance", "pass", "end_game")
NOT_CHANGING = tuple(name for name in TOOLS if name not in CHANGING)


def _surface() -> tuple[ToolSurface, ServiceHarness]:
    harness = a_service(renderer=TextRenderer())
    return ToolSurface(harness.service), harness


def _in_main_step_with_forests(harness: ServiceHarness) -> str:
    situation = (
        a_game().with_battlefield("Forest", "Forest").with_hand("Grizzly Bears", "Forest", "Forest")
    )
    return harness.holding(situation.with_library("Island", "Plains", "Swamp").build())


def _parameters(surface: ToolSurface, tool: str) -> list[str]:
    return [parameter.name for parameter in surface.definition(tool).parameters]


# @spec TOOL-007
def test_the_surface_offers_exactly_the_thirteen_tools() -> None:
    surface, _ = _surface()

    assert sorted(surface.names) == sorted(TOOLS)


# @spec TOOL-008
@pytest.mark.parametrize("tool", GAME_SCOPED)
def test_a_game_scoped_tool_takes_game_id_first(tool: str) -> None:
    surface, _ = _surface()

    assert _parameters(surface, tool)[0] == "game_id"


# @spec TOOL-008
@pytest.mark.parametrize("tool", GAME_SCOPED)
def test_a_game_scoped_tool_declares_game_id_first_in_its_input_schema(tool: str) -> None:
    surface, _ = _surface()

    assert next(iter(surface.definition(tool).input_schema["properties"])) == "game_id"


# @spec TOOL-009, TOOL-032
@pytest.mark.parametrize("tool", CHANGING)
def test_a_changing_tool_accepts_an_optional_after(tool: str) -> None:
    surface, _ = _surface()
    after = next(p for p in surface.definition(tool).parameters if p.name == "after")

    assert not after.required


# @spec TOOL-009
@pytest.mark.parametrize("tool", NOT_CHANGING)
def test_a_tool_that_changes_no_game_takes_no_after(tool: str) -> None:
    surface, _ = _surface()

    assert "after" not in _parameters(surface, tool)


# @spec TOOL-009
def test_after_on_a_changing_call_answers_a_resend_once() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    change = harness.game(game_id).change

    first = surface.call("play", {"game_id": game_id, "card": "Forest", "after": change})
    again = surface.call("play", {"game_id": game_id, "card": "Forest", "after": change})

    assert harness.game(game_id).change == change + 1
    assert again.text.splitlines()[0] == first.text.splitlines()[0]


# @spec TOOL-010
@pytest.mark.parametrize(
    ("tool", "arguments", "encoded"),
    [
        ("effect", {"source": "Sylvan Library", "delta": {"draw": 1}}, "delta"),
        ("play", {"card": "Grizzly Bears", "choices": {"notes": "first threat"}}, "choices"),
        ("play", {"card": "Grizzly Bears", "pay": {"with": ["Forest"]}}, "pay"),
        ("play", {"card": "Grizzly Bears", "expect": {"hand": 1}}, "expect"),
        pytest.param(
            "play",
            {"card": "Grizzly Bears", "cast_triggers": [{"source": "x", "delta": {"draw": 1}}]},
            "cast_triggers",
        ),
    ],
)
def test_an_object_parameter_sent_as_a_json_string_is_decoded(
    tool: str, arguments: dict[str, object], encoded: str
) -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    sent = {"game_id": game_id, **arguments, encoded: json.dumps(arguments[encoded])}

    surface.call(tool, sent)

    assert harness.last_call().arguments[encoded] == arguments[encoded]


# @spec TOOL-010
def test_a_value_inside_a_list_parameter_is_not_decoded_again() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    triggers = [{"source": "x", "delta": json.dumps({"draw": 1})}]

    response = surface.call(
        "play", {"game_id": game_id, "card": "Grizzly Bears", "cast_triggers": triggers}
    )

    assert response.text.startswith("ERROR Argument cast_triggers[0].delta is malformed.")


# @spec TOOL-010
def test_selections_sent_as_a_json_string_are_decoded() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    look = {"look": {"n": 1, "from": "top", "rest": "library_bottom"}}
    surface.call("effect", {"game_id": game_id, "source": "Ponder", "delta": look})
    choice_id = harness.game(game_id).waiting_choice
    assert choice_id is not None

    response = surface.call(
        "choose",
        {
            "game_id": game_id,
            "choice_id": choice_id.choice_id,
            "selections": '{"hand": ["Island"]}',
        },
    )

    assert response.text.startswith("OK")


# @spec TOOL-010
def test_definitions_sent_as_a_json_string_are_decoded() -> None:
    surface, harness = _surface()
    definitions = [{"name": "Sol Ring", "produces": "{C}{C}"}]
    deck = "1 Sol Ring\n98 Forest"

    surface.call(
        "load_deck",
        {
            "cards": deck,
            "commander": "Omnath, Locus of Mana",
            "definitions": json.dumps(definitions),
        },
    )

    assert harness.last_call().arguments["definitions"] == definitions


# @spec TOOL-010, TOOL-028
def test_a_json_string_that_does_not_decode_is_answered_as_an_error() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("effect", {"game_id": game_id, "source": "x", "delta": "{draw: 1"})

    assert response.text.startswith("ERROR Argument delta is malformed.")


# @spec TOOL-107
def test_get_state_s_card_sent_as_a_json_list_in_a_string_is_decoded_as_that_list() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call(
        "get_state", {"game_id": game_id, "card": json.dumps(["Forest", "Grizzly Bears"])}
    )

    assert response.text.splitlines()[0] == "OK Rules text of 2 cards."
    assert harness.last_call().arguments["card"] == ["Forest", "Grizzly Bears"]


# @spec TOOL-107
@pytest.mark.parametrize("card", ["Grizzly Bears", "[Grizzly Bears"])
def test_get_state_s_card_sent_as_any_other_text_is_taken_as_one_name(card: str) -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("get_state", {"game_id": game_id, "card": card})

    assert harness.last_call().arguments["card"] == card
    assert response.text.startswith(("OK Rules text of 1 card.", "ERROR [Grizzly Bears"))


# @spec TOOL-027
def test_an_error_response_sets_the_error_flag() -> None:
    surface, _ = _surface()

    response = surface.call("get_state", {"game_id": "gnosuchgame"})

    assert (response.text.split()[0], response.is_error) == ("ERROR", True)


# @spec TOOL-027
def test_an_ok_response_does_not_set_the_error_flag() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id, "card": "Forest"})

    assert (response.text.split()[0], response.is_error) == ("OK", False)


# @spec TOOL-027
def test_a_rejected_response_does_not_set_the_error_flag() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id, "card": "Forest", "from": "hand"})
    response = surface.call("play", {"game_id": game_id, "card": "Forest", "from": "hand"})

    assert (response.text.split()[0], response.is_error) == ("REJECTED", False)


# @spec TOOL-027
def test_a_choice_response_does_not_set_the_error_flag() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    look = {"look": {"n": 2, "from": "top", "rest": "library_bottom"}}

    response = surface.call("effect", {"game_id": game_id, "source": "Ponder", "delta": look})

    assert (response.text.split()[0], response.is_error) == ("CHOICE", False)


# @spec TOOL-027
def test_a_log_export_is_one_json_text_without_the_error_flag() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("get_log", {"game_id": game_id})

    assert (json.loads(response.text)["game"]["game_id"], response.is_error) == (game_id, False)


# @spec TOOL-028
def test_a_missing_required_parameter_is_answered_as_error_text() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id})

    assert response.text.startswith("ERROR Argument card is malformed.")


# @spec TOOL-028
def test_a_null_required_parameter_counts_as_missing() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id, "card": None})

    assert response.text.startswith("ERROR Argument card is malformed.")


# @spec TOOL-028
def test_a_parameter_of_the_wrong_type_is_answered_as_error_text() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("attack", {"game_id": game_id, "attackers": 3})

    assert response.text.startswith("ERROR Argument attackers is malformed.")


# @spec TOOL-028
def test_an_unknown_parameter_is_answered_as_error_text() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id, "card": "Forest", "overide": "x"})

    assert response.text.startswith("ERROR Argument overide is malformed.")


# @spec TOOL-028
def test_a_malformed_call_sets_the_error_flag() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id})

    assert response.is_error


# @spec TOOL-028
def test_a_malformed_call_about_an_existing_game_carries_its_status_line() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id})

    assert response.text.splitlines()[-1].startswith("T3 main1 · Hand 3")


# @spec TOOL-028
def test_a_malformed_call_is_kept_as_a_call_record() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    response = surface.call("play", {"game_id": game_id, "card": 7})

    record = harness.last_call()
    assert (record.tool, record.game_id, record.response) == ("play", game_id, response.text)


# @spec TOOL-028
def test_a_malformed_call_keeps_its_arguments_as_received() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)

    surface.call("effect", {"game_id": game_id, "source": "x", "delta": "not json"})

    assert harness.last_call().arguments["delta"] == "not json"


# @spec REC-017
def test_a_malformed_call_keeps_an_object_sent_as_a_json_string_decoded() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    expect = {"hand": 1}

    surface.call("play", {"game_id": game_id, "card": 7, "expect": json.dumps(expect)})

    assert harness.last_call().arguments["expect"] == expect


# @spec TOOL-028
def test_a_malformed_call_changes_nothing() -> None:
    surface, harness = _surface()
    game_id = _in_main_step_with_forests(harness)
    change = harness.game(game_id).change

    surface.call("play", {"game_id": game_id, "card": ["Forest"]})

    assert harness.game(game_id).change == change
