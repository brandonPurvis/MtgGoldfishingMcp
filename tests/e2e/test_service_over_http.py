"""End to end: start the real process, play a short game over HTTP with the SDK's MCP client.

Excluded from the pre-commit run (`-m "not e2e"`); run with `uv run pytest -m e2e`.
"""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from tests.e2e.running_service import RunningService, running_service
from tests.support.decks import ATRAXA, a_deck_list

pytestmark = pytest.mark.e2e


@pytest.fixture
def service(tmp_path: Path) -> Iterator[RunningService]:
    """The real service, with recorded card data in place of Scryfall."""
    with running_service(tmp_path) as running:
        yield running


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


def _change(text: str) -> int:
    return int(text.splitlines()[-1].rsplit("#", 1)[1])


# @spec TOOL-005
def test_uv_run_mtg_goldfishing_starts_the_service(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on the PATH")

    with running_service(tmp_path, [uv, "run", "--no-sync", "mtg-goldfishing"]) as running:
        health = httpx.get(running.url.removesuffix("/mcp") + "/health", timeout=5.0)

    assert health.status_code == 200


# @spec TOOL-001, TOOL-004, TOOL-027
async def test_a_short_game_is_played_over_http(service: RunningService) -> None:
    async with Client(service.url) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 13

        loaded = await client.call_tool(
            "load_deck", {"cards": a_deck_list().text(), "commander": ATRAXA}
        )
        deck_id = _text(loaded).split()[3].rstrip(":")

        started = _text(await client.call_tool("new_game", {"deck_id": deck_id, "seed": 42}))
        game_id = started.split()[3]
        assert "Hand: " in started

        kept = _text(await client.call_tool("mulligan", {"game_id": game_id, "keep": True}))
        assert kept.splitlines()[-1].startswith("T1 main1")

        land = await client.call_tool(
            "play", {"game_id": game_id, "card": "Forest", "after": _change(kept)}
        )
        assert _text(land).startswith("OK Played Forest.")

        refused = await client.call_tool("play", {"game_id": game_id, "card": ["Forest"]})
        assert refused.is_error

        moved = _text(await client.call_tool("advance", {"game_id": game_id, "to": "main2"}))
        assert moved.splitlines()[-1].startswith("T1 main2")

        ended = await client.call_tool(
            "end_game", {"game_id": game_id, "result": "stalled", "notes": "end-to-end check"}
        )
        assert _text(ended).startswith("OK")

        log = json.loads(_text(await client.call_tool("get_log", {"game_id": game_id})))

    assert (log["game"]["status"], service.database.exists()) == ("ended", True)
