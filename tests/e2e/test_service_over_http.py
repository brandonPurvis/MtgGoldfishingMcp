"""End to end: start the real process, play a short game over HTTP with the SDK's MCP client.

Excluded from the pre-commit run (`-m "not e2e"`); run with `uv run pytest -m e2e`.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from tests.support.decks import ATRAXA, a_deck_list

ROOT = Path(__file__).resolve().parents[2]
START_TIMEOUT = 60.0

pytestmark = pytest.mark.e2e


@dataclass(frozen=True)
class RunningService:
    url: str
    database: Path


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def _environment(port: int, database: Path) -> dict[str, str]:
    return {
        **os.environ,
        "MTG_GOLDFISHING_HOST": "127.0.0.1",
        "MTG_GOLDFISHING_PORT": str(port),
        "MTG_GOLDFISHING_DB": str(database),
    }


def _wait_until_healthy(base: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the service exited early with status {process.returncode}")
        try:
            if httpx.get(f"{base}/health", timeout=1.0).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.2)
    raise AssertionError("the service did not answer /health in time")


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Stop the process and anything it started (`uv run` starts the service as a child)."""
    if process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=30)


def _started(command: Sequence[str], tmp_path: Path) -> Iterator[RunningService]:
    port = _free_port()
    database = tmp_path / "games.sqlite3"
    process = subprocess.Popen(
        list(command),
        cwd=ROOT,
        env=_environment(port, database),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=sys.platform != "win32",
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_until_healthy(base, process)
        yield RunningService(f"{base}/mcp", database)
    finally:
        _stop(process)


@pytest.fixture
def service(tmp_path: Path) -> Iterator[RunningService]:
    """The real service, with recorded card data in place of Scryfall."""
    yield from _started([sys.executable, "-m", "tests.e2e.recorded_service"], tmp_path)


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
    started = _started([uv, "run", "--no-sync", "mtg-goldfishing"], tmp_path)

    running = next(started)
    try:
        health = httpx.get(running.url.removesuffix("/mcp") + "/health", timeout=5.0)
    finally:
        started.close()

    assert health.status_code == 200


# @spec TOOL-001, TOOL-004, TOOL-027
async def test_a_short_game_is_played_over_http(service: RunningService) -> None:
    async with Client(service.url) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 12

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
