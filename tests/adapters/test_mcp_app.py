"""The HTTP application: the MCP endpoint at /mcp, stateless, and a health check."""

import json
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from mtg_goldfishing.adapters.mcp.app import create_app
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from tests.support.service import a_service

LOCAL = "http://127.0.0.1:8000"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


@pytest.fixture
def http() -> Iterator[TestClient]:
    app = create_app(a_service(renderer=TextRenderer()).service)
    with TestClient(app, base_url=LOCAL) as client:
        yield client


def _rpc(method: str, params: dict[str, object], number: int = 1) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": number, "method": method, "params": params}


def _result(response_text: str) -> dict[str, object]:
    """The JSON-RPC message in a response, whether sent as JSON or as one server-sent event."""
    for line in response_text.splitlines():
        if line.startswith("data:"):
            message: dict[str, object] = json.loads(line.removeprefix("data:"))
            return message
    whole: dict[str, object] = json.loads(response_text)
    return whole


# @spec TOOL-002
def test_the_health_check_answers_with_success(http: TestClient) -> None:
    assert http.get("/health").status_code == 200


# @spec TOOL-001
def test_the_mcp_endpoint_lists_tools_without_a_session(http: TestClient) -> None:
    response = http.post("/mcp", headers=MCP_HEADERS, json=_rpc("tools/list", {}))

    result = _result(response.text)["result"]
    assert isinstance(result, dict)
    assert len(result["tools"]) == 11


# @spec TOOL-001
def test_the_mcp_endpoint_starts_no_session(http: TestClient) -> None:
    initialize = _rpc(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    )

    response = http.post("/mcp", headers=MCP_HEADERS, json=initialize)

    assert response.status_code == 200
    assert "mcp-session-id" not in response.headers


# @spec TOOL-001
def test_the_mcp_endpoint_answers_a_tool_call_without_a_session(http: TestClient) -> None:
    call = _rpc("tools/call", {"name": "get_state", "arguments": {"game_id": "gnosuchgame"}})

    response = http.post("/mcp", headers=MCP_HEADERS, json=call)

    result = _result(response.text)["result"]
    assert isinstance(result, dict)
    assert result["isError"] is True
