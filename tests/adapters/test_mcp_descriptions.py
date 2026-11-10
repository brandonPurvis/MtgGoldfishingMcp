"""What an agent reads before its first call: tool descriptions and the server instructions."""

import ast
import json
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.mcp.definitions import TOOL_DEFINITIONS, ToolDefinition
from mtg_goldfishing.adapters.mcp.instructions import SERVER_INSTRUCTIONS, SERVER_NAME

PURPOSES = {
    "load_deck": "Load a Commander deck list once and get a deck id to start games with.",
    "new_game": "Start a goldfish game on a loaded deck: shuffles and deals seven.",
    "mulligan": "Keep the opening hand or take a mulligan.",
    "get_state": "List the hand, battlefield and other zones when the status line is not enough.",
    "play": "Play a land or cast a spell, stating what it does.",
    "effect": "Record anything that happens without playing a card.",
    "choose": "Finish a look or search by saying where the revealed cards go.",
    "attack": "Declare attackers and which are blocked.",
    "advance": "Move to the next step, or forward to a named step.",
    "end_game": "End the game with a result and verdict.",
    "get_log": "Return the game's records as JSON for analysis.",
}
DELTA_KEYS = (
    "untap",
    "tap",
    "mana",
    "tokens",
    "counters",
    "move",
    "commander_stays",
    "discard",
    "fetch",
    "draw",
    "life",
    "damage",
    "shuffle",
    "look",
    "search",
)
DEFINITIONS = {definition.name: definition for definition in TOOL_DEFINITIONS}
MCP_ADAPTER = Path(__file__).resolve().parents[2] / "src" / "mtg_goldfishing" / "adapters" / "mcp"
RENDERER_MODULES = ("rendering.py", "listing_lines.py", "refusal_lines.py")


def _ids(definition: ToolDefinition) -> str:
    return definition.name


# @spec TOOL-011
@pytest.mark.parametrize("definition", TOOL_DEFINITIONS, ids=_ids)
def test_a_description_opens_with_the_tools_purpose_in_one_sentence(
    definition: ToolDefinition,
) -> None:
    assert definition.description.splitlines()[0] == PURPOSES[definition.name]


# @spec TOOL-011
@pytest.mark.parametrize("definition", TOOL_DEFINITIONS, ids=_ids)
def test_a_description_says_what_the_service_does_automatically_after_its_purpose(
    definition: ToolDefinition,
) -> None:
    description = definition.description

    assert description.index(PURPOSES[definition.name]) < description.index("Automatically:")


# @spec TOOL-011
@pytest.mark.parametrize("definition", TOOL_DEFINITIONS, ids=_ids)
def test_a_description_gives_every_parameter_an_example_after_the_automatic_part(
    definition: ToolDefinition,
) -> None:
    description = definition.description
    automatic = description.index("Automatically:")
    places = [description.index(f"\n- {p.name}") for p in definition.parameters]
    examples = [
        f"Example: {json.dumps(p.example, ensure_ascii=False)}" for p in definition.parameters
    ]

    assert all(place > automatic for place in places)
    assert all(example in description for example in examples)


# @spec TOOL-011
@pytest.mark.parametrize("definition", TOOL_DEFINITIONS, ids=_ids)
def test_a_description_ends_with_what_can_be_overridden(definition: ToolDefinition) -> None:
    description = definition.description
    last_parameter = description.index(f"\n- {definition.parameters[-1].name}")

    assert description.index("Override:") > last_parameter


# @spec TOOL-011
@pytest.mark.parametrize("definition", TOOL_DEFINITIONS, ids=_ids)
def test_a_description_marks_its_required_parameters(definition: ToolDefinition) -> None:
    required = [p.name for p in definition.parameters if p.required]

    assert all(f"\n- {name} (required)" in definition.description for name in required)


# @spec TOOL-011
def test_the_delta_shape_is_described_in_play() -> None:
    description = DEFINITIONS["play"].description

    assert all(f"{key}" in description for key in DELTA_KEYS)


# @spec TOOL-011
def test_effect_refers_to_the_delta_shape_in_play_instead_of_repeating_it() -> None:
    description = DEFINITIONS["effect"].description

    assert "delta shape described under play" in description
    assert "commander_stays" not in description


# @spec TOOL-001
def test_the_mcp_server_is_named_goldfishing() -> None:
    assert SERVER_NAME == "goldfishing"


# @spec TOOL-012
@pytest.mark.parametrize(
    ("point", "words"),
    [
        ("loading a deck once and starting games on it", ("load_deck` once", "new_game")),
        ("mulligans", ("mulligan` until you keep",)),
        ("the shape of a turn", ("Each turn:", "play", "effect", "attack", "advance")),
        ("stating what a card does in a delta", ("in `delta`", "pays costs")),
        ("overriding a REJECTED response", ("`REJECTED`", "override", "`ERROR` cannot")),
        ("answering a CHOICE response with choose", ("`CHOICE`", "call `choose`")),
        ("why advance may stop early", ("`advance` may stop early", "trigger", "discard")),
        ("the status line", ("status line", "`get_state` only when")),
        ("passing the change number as after", ("change number", "as `after`")),
        ("ending the game", ("end condition", "`end_game`")),
    ],
)
def test_the_server_instructions_describe_each_part_of_playing_a_game(
    point: str, words: tuple[str, ...]
) -> None:
    assert all(word in SERVER_INSTRUCTIONS for word in words), point


def _imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


# @spec TOOL-013
def test_the_tool_adapter_reaches_the_service_only_through_its_use_cases() -> None:
    allowed_application = (
        "mtg_goldfishing.application.service",
        "mtg_goldfishing.application.outcome",
    )
    reaching_in = [
        f"{path.name} imports {imported}"
        for path in sorted(MCP_ADAPTER.glob("*.py"))
        if path.name not in RENDERER_MODULES
        for imported in _imports(path)
        if imported.startswith("mtg_goldfishing.domain")
        or (
            imported.startswith("mtg_goldfishing.application")
            and imported not in allowed_application
        )
    ]

    assert reaching_in == []
