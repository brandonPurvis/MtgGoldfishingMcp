"""What an agent reads before its first call: tool descriptions and the server instructions."""

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.mcp.definitions import PLAY, TOOL_DEFINITIONS, ToolDefinition
from mtg_goldfishing.adapters.mcp.instructions import SERVER_INSTRUCTIONS, SERVER_NAME

PURPOSES = {
    "load_deck": "Load a Commander deck list once and get a deck id to start games with.",
    "new_game": "Start a goldfish game on a loaded deck: shuffles and deals seven.",
    "mulligan": "Keep the opening hand or take a mulligan.",
    "get_state": (
        "List the hand, battlefield and other zones when the status line is not enough,"
        " or give cards' rules text."
    ),
    "play": "Play a land or cast a spell, stating what it does.",
    "effect": "Record anything that happens without playing a card.",
    "choose": "Finish a look or search by saying where the revealed cards go.",
    "attack": "Declare attackers and which are blocked.",
    "advance": "Move to the next step, or forward to a named step.",
    "pass": "Decline to respond when your seat is asked (contested games).",
    "wait": "Wait until your seat has something to do, then say what it is (contested games).",
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


DESCRIBED = [pytest.param(d, id=d.name) for d in TOOL_DEFINITIONS]
"""Every tool's definition; `get_state` gains `card` and a purpose that names rules text."""


# @spec TOOL-011
@pytest.mark.parametrize("definition", DESCRIBED)
def test_a_description_opens_with_the_tools_purpose_in_one_sentence(
    definition: ToolDefinition,
) -> None:
    assert definition.description.splitlines()[0] == PURPOSES[definition.name]


# @spec TOOL-011
@pytest.mark.parametrize("definition", DESCRIBED)
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


# ------------------------------------------------------------------ contested games

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDFISH_DESCRIPTIONS: dict[str, str] = json.loads(
    (FIXTURES / "goldfish_tool_descriptions.json").read_text(encoding="utf-8")
)
"""Each tool's description as an agent playing a goldfish game reads it: the descriptions the
service gave before contested games existed, with `new_game`'s `starting_life`, `choose`'s
optional `selections`, `get_state`'s `card` and `get_log`'s `tools`, which goldfish games also
take (with the errors `tools` can meet), and with
`attack`'s `attackers` not marked required, since a contested game's `attack` stating trample
damage gives none."""
GOLDFISH_GUIDE = (FIXTURES / "goldfish_server_instructions.txt").read_text(encoding="utf-8")
"""The guide for every game, as the service gives it to a goldfish agent."""
CONTESTED = "Contested games:"
CONTESTED_TOOLS = ("pass", "wait")
"""Tools that exist for contested games, and say so in their purpose."""


def _goldfish_part(text: str) -> str:
    """A description part without its `Contested games:` sentences, which come last."""
    return text.split(CONTESTED, 1)[0].rstrip()


def _as_a_goldfish_agent_reads_it(definition: ToolDefinition) -> str:
    """The description with every part marked `Contested games:` left out: a parameter whose
    meaning begins with it, and the end of any part from the marker on."""
    parameters = tuple(
        replace(parameter, meaning=_goldfish_part(parameter.meaning))
        for parameter in definition.parameters
        if not parameter.meaning.startswith(CONTESTED)
    )
    return replace(
        definition,
        automatic=_goldfish_part(definition.automatic),
        parameters=parameters,
        overridable=_goldfish_part(definition.overridable),
    ).description


def _contested_part(text: str) -> str:
    return text.partition(CONTESTED)[2]


# @spec TOOL-033, TOOL-109
@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            name,
            marks=[pytest.mark.xfail(strict=True, reason="M5: not implemented yet")]
            if name == "get_log"
            else [],
        )
        for name in GOLDFISH_DESCRIPTIONS
    ],
)
def test_a_goldfish_agent_reads_every_description_as_before_once_contested_parts_are_left_out(
    name: str,
) -> None:
    assert _as_a_goldfish_agent_reads_it(DEFINITIONS[name]) == GOLDFISH_DESCRIPTIONS[name]


# @spec TOOL-033
@pytest.mark.parametrize(
    ("tool", "words"),
    [
        ("mulligan", ("every seat has kept",)),
        ("get_state", ("every seat", "hand and library")),
        ("play", ("stack", "every other seat has passed")),
        ("effect", ("stack", "immediate")),
        ("choose", ("blocks", "restate")),
        ("attack", ("window", "send attack again")),
        ("advance", ("end", "next seat")),
        ("end_game", ("tested seat", "concede")),
    ],
)
def test_a_tool_that_behaves_differently_in_a_contested_game_says_so_after_its_automatic_part(
    tool: str, words: tuple[str, ...]
) -> None:
    contested = _contested_part(DEFINITIONS[tool].automatic)

    assert all(word in contested for word in words), (tool, contested)


# @spec TOOL-033
@pytest.mark.parametrize(
    ("tool", "parameter"),
    [
        ("new_game", "opponents"),
        ("new_game", "position"),
        ("effect", "immediate"),
        ("choose", "delta"),
        ("choose", "blocks"),
        ("choose", "restate"),
        ("choose", "override"),
        ("attack", "targets"),
    ],
)
def test_a_parameter_taken_only_in_a_contested_game_is_marked_contested_games(
    tool: str, parameter: str
) -> None:
    meaning = next(p.meaning for p in DEFINITIONS[tool].parameters if p.name == parameter)

    assert meaning.startswith(CONTESTED), meaning


# @spec TOOL-033
def test_the_delta_shape_names_the_counter_key_among_its_contested_keys() -> None:
    contested = _contested_part(next(p.meaning for p in PLAY.parameters if p.name == "delta"))

    assert "counter:" in contested, contested


# @spec TOOL-033
@pytest.mark.parametrize("tool", CONTESTED_TOOLS)
def test_a_tool_that_exists_for_contested_games_says_so_in_its_purpose(tool: str) -> None:
    assert PURPOSES[tool].endswith("(contested games).")


# @spec TOOL-034
def test_the_server_instructions_begin_with_the_guide_for_every_game_unchanged() -> None:
    assert SERVER_INSTRUCTIONS.startswith(GOLDFISH_GUIDE)


# @spec TOOL-034
@pytest.mark.parametrize(
    ("point", "words"),
    [
        (
            "new_game with opponents gives a seat id per seat",
            ("`opponents`", "seat id", "`game_id`"),
        ),
        ("seats act one at a time and wait", ("one at a time", "`wait`")),
        ("the stack and responding", ("stack", "every other seat has passed", "`pass`")),
        ("a CHOICE addressed to a seat", ("`CHOICE` addressed to you", "blocks", "`choose`")),
        ("the attacking seat states combat", ("`immediate: true`", "damage to seats")),
        ("the digest", ("what the other seats did",)),
        ("only the tested seat ends the game", ("tested seat ends the game", "concedes")),
    ],
)
def test_the_server_instructions_continue_with_a_section_on_contested_games(
    point: str, words: tuple[str, ...]
) -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    assert all(word in contested for word in words), point


# @spec TOOL-078
def test_the_contested_section_says_a_blocked_attacker_deals_nothing_without_trample() -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    for words in (
        "A blocked attacker deals a seat nothing",
        "`attack` and `trample`",
        "before combat damage",
    ):
        assert words in contested, words


# @spec TOOL-084
def test_the_contested_section_says_to_state_cast_triggers_in_the_play_that_casts() -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    for words in ('"whenever you cast" triggers', "`cast_triggers`", "resolves within that call"):
        assert words in contested, words


# @spec TOOL-085
def test_the_contested_section_says_to_give_a_named_card_or_guess_as_text() -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    for words in ("name a card, guess or choose a number", "`text`", "every seat sees it"):
        assert words in contested, words


# ------------------------------------------------------------------ rules text and waiting


# @spec TOOL-098
@pytest.mark.parametrize(
    "words",
    [
        "card name or instance id, or a list of them",
        "rules text",
        "in place of the listing",
        "Only cards you may see",
        "Not given together with detail",
    ],
)
def test_get_state_describes_card_for_every_game(words: str) -> None:
    meaning = next(p.meaning for p in DEFINITIONS["get_state"].parameters if p.name == "card")

    assert words in meaning
    assert not meaning.startswith(CONTESTED)


# @spec TOOL-098
def test_get_state_gives_an_example_of_card() -> None:
    (card,) = [p for p in DEFINITIONS["get_state"].parameters if p.name == "card"]

    assert f"Example: {json.dumps(card.example)}" in DEFINITIONS["get_state"].description


# @spec TOOL-099
def test_the_wait_description_says_still_waiting_means_the_seat_to_act_has_not_acted() -> None:
    contested = _contested_part(DEFINITIONS["wait"].automatic)

    for words in ("still waiting", "has not yet acted", "call wait again"):
        assert words in contested, words


# @spec TOOL-100
def test_the_guide_for_every_game_says_to_read_rules_text_rather_than_rely_on_memory() -> None:
    for words in ("rules text", "`get_state` and `card`", "rather than relying on memory"):
        assert words in GOLDFISH_GUIDE, words
        assert words in SERVER_INSTRUCTIONS, words


# @spec TOOL-101
def test_the_contested_section_says_to_call_wait_again_while_still_waiting_however_long() -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    for words in (
        "Until the game ends or your seat is eliminated",
        "call `wait` again after every answer that says you are still waiting",
        "however long",
        "not a stalled game",
    ):
        assert words in contested, words


# @spec TOOL-102
def test_the_contested_section_gives_wait_s_default_and_most_and_says_to_keep_the_default() -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    for words in (
        "30 seconds unless you give one, at most 60",
        "Leave it at the default",
        "wait longer than 60 seconds",
    ):
        assert words in contested, words


# @spec TOOL-108
def test_the_contested_section_says_a_failed_or_empty_wait_is_the_client_giving_up() -> None:
    contested = SERVER_INSTRUCTIONS.removeprefix(GOLDFISH_GUIDE)

    for words in (
        "fails or comes back empty",
        "your client stopped waiting",
        "not that the game stalled",
        "call `wait` again",
    ):
        assert words in contested, words


# ------------------------------------------------------------------ reading the records

NOT_YET = pytest.mark.xfail(strict=True, reason="M5: not implemented yet")


def _get_log_parameter(name: str) -> str:
    """The meaning of one of get_log's parameters; empty when get_log has none of that name."""
    return next((p.meaning for p in DEFINITIONS["get_log"].parameters if p.name == name), "")


# @spec TOOL-109
@NOT_YET
@pytest.mark.parametrize(
    "words",
    [
        "A list of tool names",
        "keeps only the log entries and call records of calls to those tools",
        "leaving the snapshots as they would be without it",
    ],
)
def test_get_log_describes_tools_for_every_game(words: str) -> None:
    meaning = _get_log_parameter("tools")

    assert words in meaning
    assert not meaning.startswith(CONTESTED)


# @spec TOOL-109
@NOT_YET
def test_get_log_gives_an_example_of_tools() -> None:
    (tools,) = [p for p in DEFINITIONS["get_log"].parameters if p.name == "tools"]

    assert f"Example: {json.dumps(tools.example)}" in DEFINITIONS["get_log"].description


# @spec TOOL-110
@NOT_YET
@pytest.mark.parametrize(
    "words",
    [
        "a seat number",
        "keeps only the log entries and call records of calls that seat made",
        "the snapshots of that seat's turns",
        "Refused in a goldfish game",
    ],
)
def test_the_contested_part_of_get_log_describes_seat(words: str) -> None:
    meaning = _get_log_parameter("seat")

    assert meaning.startswith(CONTESTED)
    assert words in meaning


# @spec TOOL-110
@NOT_YET
def test_get_log_gives_an_example_of_seat() -> None:
    (seat,) = [p for p in DEFINITIONS["get_log"].parameters if p.name == "seat"]

    assert f"- seat: {seat.meaning} Example: 2" in DEFINITIONS["get_log"].description


# @spec TOOL-111
@NOT_YET
@pytest.mark.parametrize(
    "words",
    [
        "When the tested seat ends the game",
        "the log records every seat's life, commander damage taken, hand, battlefield and"
        " graveyard as the game ended",
        "your verdict need not restate them",
    ],
)
def test_the_contested_part_of_end_game_says_the_log_records_every_seat_s_board(
    words: str,
) -> None:
    assert words in _contested_part(DEFINITIONS["end_game"].automatic)
