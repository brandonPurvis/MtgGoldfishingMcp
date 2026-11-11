"""What the repository carries for Claude Code: the server connection and the player brief."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIEF = ROOT / ".claude" / "agents" / "goldfish-player.md"
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
CONTESTED_SECTION = "## Contested games"


def _front_matter() -> dict[str, str]:
    text = BRIEF.read_text(encoding="utf-8")
    _, front, _ = text.split("---\n", 2)
    fields = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _body() -> str:
    return BRIEF.read_text(encoding="utf-8").split("---\n", 2)[2]


def _section(heading: str) -> str:
    """The brief's section under `heading`, up to the next heading of the same level."""
    body = _body()
    assert heading in body, f"no section {heading!r}"
    after = body.split(heading, 1)[1]
    return after.split("\n## ", 1)[0]


# @spec TOOL-006
def test_the_repository_connects_claude_code_to_the_local_service_as_goldfishing() -> None:
    servers = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]

    assert servers["goldfishing"] == {"type": "http", "url": "http://127.0.0.1:8000/mcp"}


# @spec TOOL-029
def test_the_player_brief_is_a_subagent_named_goldfish_player() -> None:
    assert _front_matter()["name"] == "goldfish-player"


# @spec TOOL-029
def test_the_player_brief_restricts_the_subagent_to_the_goldfishing_tools() -> None:
    tools = [tool.strip() for tool in _front_matter()["tools"].split(",")]

    assert sorted(tools) == sorted(f"mcp__goldfishing__{name}" for name in TOOLS)


# @spec TOOL-030
@pytest.mark.parametrize(
    ("instruction", "words"),
    [
        ("play as a strong player aiming to win fast", ("strong player", "as fast as the deck")),
        ("make every decision itself", ("Make every decision yourself",)),
        ("give a reason on non-obvious plays", ("`reason`", "not obvious")),
        ("use expect when tracking a number closely", ("`expect`", "tracking a number")),
        ("pass after on every changing call", ("Pass `after` on every changing call",)),
        ("resolve or consciously pass reminders", ("reminder", "consciously pass")),
        ("end the game with end_game and a verdict", ("`end_game`", "verdict")),
        ("return the game id, seed and verdict", ("Game id:", "Seed:", "Verdict:")),
    ],
)
def test_the_player_brief_instructs_the_subagent(instruction: str, words: tuple[str, ...]) -> None:
    body = _body()

    assert all(word in body for word in words), instruction


# @spec TOOL-052
def test_the_player_brief_says_a_subagent_may_be_given_a_seat_id_and_its_seat_instead() -> None:
    given = _section("## What you are given")

    assert all(words in given for words in ("seat id", "which seat you play")), given


# @spec TOOL-053, TOOL-072, TOOL-073, TOOL-054, TOOL-055, TOOL-080, TOOL-088, TOOL-089
@pytest.mark.parametrize(
    ("instruction", "words"),
    [
        ("TOOL-053: play its seat to win unless told otherwise", ("to win", "another goal")),
        ("TOOL-053: wait whenever not the seat to act", ("`wait`", "not the seat to act")),
        ("TOOL-053: read the digest", ("top of each response", "other seats did")),
        ("TOOL-053: respond, or pass", ("`play` or `effect`", "`pass`")),
        ("TOOL-053: answer choices addressed to it", ("`choose`", "blocks", "other seats")),
        ("TOOL-053: state combat after blocks", ("`effect`", "`immediate: true`", "after blocks")),
        ("TOOL-072: leave out the damage to seats", ("leave out", "damage to seats")),
        (
            "TOOL-072: state trample damage once blocks are known",
            ("`attack` and `trample`", "once blocks are known", "before advancing to combat"),
        ),
        (
            "TOOL-072: a blocked attacker otherwise deals nothing",
            ("blocked attacker otherwise deals the seat nothing",),
        ),
        (
            "TOOL-080: give evasion an attacker has only this turn",
            ("`evasion`", 'flying, horsemanship or "can\'t be blocked"', "only this turn"),
        ),
        (
            "TOOL-080: block only as evasion allows",
            ("block only as the attackers' evasion allows",),
        ),
        (
            "TOOL-080: override a refused block only when it is wrong for this turn",
            (
                "override a refused block only when",
                "gained flying or reach",
                "lost its evasion",
                "assumed condition",
            ),
        ),
        ("TOOL-073: attack not declared", ("not declared", "`wait`", "same `attack`")),
        pytest.param(
            "TOOL-088: state cast triggers in the play",
            ("`cast_triggers`", "`play` that casts the spell", "never in a later `effect`"),
        ),
        pytest.param(
            "TOOL-089: give a named card, guess or number as text",
            ("name a card, guess or choose a number", "`text`"),
        ),
        ("TOOL-054: the tested seat's verdict", ("tested seat", "what the opposition did")),
        ("TOOL-054: an opposing seat concedes", ("concede", "until the game ends")),
        ("TOOL-055: return the seat, the id and the verdict", ("Seat:", "Id:", "Verdict:")),
    ],
)
def test_the_player_brief_has_a_section_on_contested_games(
    instruction: str, words: tuple[str, ...]
) -> None:
    contested = _section(CONTESTED_SECTION)

    assert all(word in contested for word in words), instruction


# @spec TOOL-104, TOOL-105
@pytest.mark.parametrize(
    ("instruction", "words"),
    [
        (
            "TOOL-104: read rules text rather than rely on memory",
            ("`get_state` with `card`", "rules text", "rather than relying on memory"),
        ),
        (
            "TOOL-105: apply the legend rule, which the service does not",
            (
                "legend rule",
                "the service does not",
                "two legendary permanents with the same name",
                "owner's graveyard with `effect`",
            ),
        ),
    ],
)
def test_the_player_brief_gives_every_game_its_rules_reminders(
    instruction: str, words: tuple[str, ...]
) -> None:
    how_to_play = _section("## How to play")

    assert all(word in how_to_play for word in words), instruction


# @spec TOOL-103, TOOL-106
@pytest.mark.parametrize(
    ("instruction", "words"),
    [
        (
            "TOOL-103: keep calling wait until the game ends or the seat is eliminated",
            (
                "Keep calling `wait`",
                "still waiting",
                "however long",
                "Never report the game as stalled",
                "timed out, failed or came back empty",
                "Stop only when the game ends or your seat is eliminated",
            ),
        ),
        (
            "TOOL-106: several seats' triggers go on the stack in turn order",
            (
                "triggers of several seats",
                "turn order starting with the active seat",
                "the last seat's resolve first",
                "As the active seat",
                "when you are asked to respond",
            ),
        ),
    ],
)
def test_the_player_brief_s_contested_section_says_how_to_wait_and_order_triggers(
    instruction: str, words: tuple[str, ...]
) -> None:
    contested = _section(CONTESTED_SECTION)

    assert all(word in contested for word in words), instruction
