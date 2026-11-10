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
    "end_game",
    "get_log",
)


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
