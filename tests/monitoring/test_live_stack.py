"""The dashboard against a running monitoring stack: the real service pushes its measurements to
the stack, and every panel's queries must find them.

Needs the stack already running on the default ports
(`docker compose -f monitoring/compose.yaml up -d`). Excluded from the pre-commit run
(`-m "not monitoring"`); run with `uv run pytest -m monitoring`.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client, MCPError
from mcp.types import CallToolResult, TextContent

from tests.e2e.running_service import running_service
from tests.support.decks import ATRAXA, a_deck_list

pytestmark = pytest.mark.monitoring

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "monitoring" / "dashboards" / "mtg-goldfishing.json"
GRAFANA = "http://127.0.0.1:3000"
PROMETHEUS_QUERY = f"{GRAFANA}/api/datasources/proxy/uid/prometheus/api/v1/query"
OTLP_ENDPOINT = "http://localhost:4318"
EXPORT_INTERVAL_MS = 1000
ARRIVAL_TIMEOUT = 60.0
SERIES = re.compile(
    r"\b(?:goldfishing_tool_call_duration_seconds|http_server_request_duration_seconds)"
    r"_(?:bucket|count|sum)\b"
    r'(?P<selector>\{(?:[^}"]|"[^"]*")*\})?'
)


@pytest.fixture(autouse=True)
def _stack_is_running() -> None:
    try:
        httpx.get(f"{GRAFANA}/api/health", timeout=2.0)
    except httpx.TransportError:
        pytest.skip(
            f"the monitoring stack is not running (no Grafana at {GRAFANA}); "
            "start it with: docker compose -f monitoring/compose.yaml up -d"
        )


def _text(result: CallToolResult) -> str:
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


async def _play_a_few_calls(url: str) -> None:
    """Calls answered OK, REJECTED and ERROR, a `wait`, and a call naming no tool."""
    async with Client(url) as client:
        loaded = await client.call_tool(
            "load_deck", {"cards": a_deck_list().text(), "commander": ATRAXA}
        )
        deck_id = _text(loaded).split()[3].rstrip(":")
        game_id = _text(
            await client.call_tool("new_game", {"deck_id": deck_id, "seed": 42})
        ).split()[3]
        await client.call_tool("mulligan", {"game_id": game_id, "keep": True})
        await client.call_tool("play", {"game_id": game_id, "card": "Forest", "from": "hand"})
        await client.call_tool("play", {"game_id": game_id, "card": "Forest", "from": "hand"})
        await client.call_tool("play", {"game_id": game_id, "card": ["Forest"]})
        await client.call_tool("wait", {"game_id": game_id, "timeout": 1})
        with contextlib.suppress(MCPError):
            await client.call_tool("no_such_tool", {})


def _for_this_run(expr: str, service_name: str) -> str:
    """The panel's query with the dashboard's variables filled in and every series restricted
    to this run's service, so earlier runs' measurements cannot satisfy it."""
    filled = (
        expr.replace("${tool}", ".*")
        .replace("[[tool]]", ".*")
        .replace("$tool", ".*")
        .replace("$__range", "5m")
    )
    matcher = f'service_name="{service_name}"'

    def restrict(match: re.Match[str]) -> str:
        selector = match.group("selector")
        series = match.group(0).removesuffix(selector or "")
        if not selector or selector == "{}":
            return f"{series}{{{matcher}}}"
        return f"{series}{{{matcher},{selector[1:]}"

    return SERIES.sub(restrict, filled)


def _query(expr: str) -> list[dict[str, Any]]:
    response = httpx.get(PROMETHEUS_QUERY, params={"query": expr}, timeout=10.0)
    response.raise_for_status()
    result: list[dict[str, Any]] = response.json()["data"]["result"]
    return result


def _shows_measurements(result: list[dict[str, Any]]) -> bool:
    return any(not math.isnan(float(sample["value"][1])) for sample in result)


def _panel_queries() -> list[tuple[str, str]]:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panels = []
    for panel in dashboard["panels"]:
        panels.append(panel)
        panels.extend(panel.get("panels", []))
    return [
        (panel["title"], str(target["expr"]))
        for panel in panels
        for target in panel.get("targets", [])
        if not target.get("hide")
    ]


def _wait_until_shown(queries: list[tuple[str, str]]) -> list[str]:
    """The panels whose queries still find nothing when the arrival timeout runs out."""
    deadline = time.monotonic() + ARRIVAL_TIMEOUT
    waiting = list(queries)
    while waiting and time.monotonic() < deadline:
        waiting = [
            (title, expr) for title, expr in waiting if not _shows_measurements(_query(expr))
        ]
        if waiting:
            time.sleep(1.0)
    return [f"{title}: {expr}" for title, expr in waiting]


# @spec TEL-046
async def test_every_panel_shows_the_measurements_the_service_pushes(tmp_path: Path) -> None:
    service_name = f"mtg-goldfishing-monitoring-test-{uuid.uuid4().hex[:12]}"
    environment = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": OTLP_ENDPOINT,
        "OTEL_METRIC_EXPORT_INTERVAL": str(EXPORT_INTERVAL_MS),
        "OTEL_SERVICE_NAME": service_name,
    }
    queries = [(title, _for_this_run(expr, service_name)) for title, expr in _panel_queries()]

    with running_service(tmp_path, environment=environment) as service:
        # Two rounds of calls, the second after the first has arrived, so that every series
        # rises within a one-minute window and its rate is not zero.
        await _play_a_few_calls(service.url)
        first_push = (
            f'goldfishing_tool_call_duration_seconds_count{{service_name="{service_name}"}}'
        )
        _wait_until_shown([("first push", first_push)])
        await _play_a_few_calls(service.url)
        empty = _wait_until_shown(queries)

    assert empty == []
