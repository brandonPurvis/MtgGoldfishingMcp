"""The tool-call listener: the MCP server tells it the tool, the status and the duration of
every call its call handler receives, and never lets it change how a call is answered."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any, cast

import anyio
import anyio.from_thread
import anyio.lowlevel
import pytest
from mcp import Client
from mcp.server import Server
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolRequestParams, CallToolResult
from starlette.testclient import TestClient

from mtg_goldfishing.adapters.mcp.app import create_app
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.mcp.server import ToolCallListener, mcp_server
from mtg_goldfishing.adapters.mcp.tools import ToolSurface
from mtg_goldfishing.application.outcome import Outcome
from mtg_goldfishing.application.ports import Rendered
from tests.support.builders import a_game
from tests.support.service import ServiceHarness, a_service
from tests.support.telemetry import Readings, SteppedClock

LOCAL = "http://127.0.0.1:8000"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}
NO_SUCH_GAME = {"game_id": "gnosuchgame"}


class Heard:
    """A tool-call listener keeping every call it hears of."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []
        self.threads: list[int] = []

    def __call__(self, tool: str, status: str, seconds: float) -> None:
        self.calls.append((tool, status, seconds))
        self.threads.append(threading.get_ident())

    @property
    def outcomes(self) -> list[tuple[str, str]]:
        return [(tool, status) for tool, status, _ in self.calls]

    @property
    def durations(self) -> list[float]:
        return [seconds for _, _, seconds in self.calls]


class ListenerBroke(Exception):
    """The listener's own failure."""


class FailingListener:
    """A tool-call listener that raises whenever it hears of a call."""

    def __init__(self) -> None:
        self.failure = ListenerBroke()

    def __call__(self, tool: str, status: str, seconds: float) -> None:
        raise self.failure


class RendererBroke(Exception):
    """A defect inside the tool: rendering the answer failed."""


class BrokenRenderer(TextRenderer):
    """The text renderer, failing every time it renders: the tool raises instead of answering."""

    def __init__(self, before: Callable[[], None] = lambda: None) -> None:
        self.failure = RendererBroke()
        self._before = before

    def render(self, tool: str, outcome: Outcome) -> Rendered:
        self._before()
        raise self.failure


class WatchedRenderer(TextRenderer):
    """The text renderer, doing something first each time it renders, on the tool's thread."""

    def __init__(self, before: Callable[[], None]) -> None:
        self._before = before

    def render(self, tool: str, outcome: Outcome) -> Rendered:
        self._before()
        return super().render(tool, outcome)


def _harness() -> ServiceHarness:
    return a_service(renderer=TextRenderer())


def _server(
    harness: ServiceHarness,
    listener: ToolCallListener | None = None,
    timer: Callable[[], float] | None = None,
) -> Server[Any]:
    return mcp_server(
        ToolSurface(harness.service), on_tool_call=listener, timer=timer or SteppedClock()
    )


CallHandler = Callable[[str, dict[str, object]], Awaitable[CallToolResult]]


def _call_handler(server: Server[Any]) -> CallHandler:
    """The function the MCP server registered with the SDK to answer tool calls."""
    entry = server.get_request_handler("tools/call")
    assert entry is not None

    async def call(name: str, arguments: dict[str, object]) -> CallToolResult:
        params = CallToolRequestParams(name=name, arguments=arguments)
        result: CallToolResult = await entry.handler(cast(Any, None), params)
        return result

    return call


async def _answer(server: Server[Any], name: str, arguments: dict[str, object]) -> object:
    """What the client is told: the result's texts and error flag, or the protocol error."""
    async with Client(server) as client:
        try:
            result = await client.call_tool(name, arguments)
        except MCPError as error:
            return ("protocol error", error.code, error.message)
    texts = [getattr(item, "text", None) for item in result.content]
    return ("result", texts, result.is_error)


async def _heard_of(harness: ServiceHarness, name: str, arguments: dict[str, object]) -> Heard:
    heard = Heard()
    async with Client(_server(harness, heard)) as client:
        await client.call_tool(name, arguments)
    return heard


def _in_main_step_with_forests(harness: ServiceHarness) -> str:
    situation = (
        a_game().with_battlefield("Forest", "Forest").with_hand("Grizzly Bears", "Forest", "Forest")
    )
    return harness.holding(situation.with_library("Island", "Plains", "Swamp").build())


async def _cancelled_before_the_result(server: Server[Any]) -> bool:
    """Call `get_state` in a scope cancelled before the call; whether the cancellation went on."""
    call = _call_handler(server)
    with anyio.CancelScope() as cancel_scope:
        cancel_scope.cancel()
        await call("get_state", NO_SUCH_GAME)
    return cancel_scope.cancelled_caught


# ------------------------------------------------------------------ every call heard once


# @spec TEL-001
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_tool_call_is_heard_once_with_its_tool_and_status() -> None:
    heard = await _heard_of(_harness(), "get_state", NO_SUCH_GAME)

    assert heard.outcomes == [("get_state", "ERROR")]


# @spec TEL-001
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_tool_call_is_timed_from_receiving_it_until_answering_it() -> None:
    clock = SteppedClock()
    heard = Heard()
    harness = a_service(renderer=WatchedRenderer(lambda: clock.set(102.5)))

    async with Client(_server(harness, heard, clock)) as client:
        await client.call_tool("get_state", NO_SUCH_GAME)

    assert heard.durations == [2.5]


# @spec TEL-001
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_tool_call_that_raised_is_timed_until_it_raised() -> None:
    clock = SteppedClock()
    heard = Heard()
    harness = a_service(renderer=BrokenRenderer(lambda: clock.set(102.5)))

    with pytest.raises(RendererBroke):
        await _call_handler(_server(harness, heard, clock))("get_state", NO_SUCH_GAME)

    assert heard.durations == [2.5]


# @spec TEL-001
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_cancelled_tool_call_is_timed_until_it_was_cancelled() -> None:
    heard = Heard()

    await _cancelled_before_the_result(_server(_harness(), heard, Readings(100.0, 100.75)))

    assert heard.durations == [0.75]


# @spec TEL-001
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_http_application_tells_its_listener_of_each_tool_call() -> None:
    heard = Heard()
    app = create_app(_harness().service, on_tool_call=heard)
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_state", "arguments": NO_SUCH_GAME},
    }

    with TestClient(app, base_url=LOCAL) as http:
        http.post("/mcp", headers=MCP_HEADERS, json=call)

    assert heard.outcomes == [("get_state", "ERROR")]


# ------------------------------------------------------------------ a synchronous listener


# @spec TEL-059
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_the_listener_is_called_on_the_thread_answering_the_call() -> None:
    heard = await _heard_of(_harness(), "get_state", NO_SUCH_GAME)

    assert heard.threads == [threading.get_ident()]


# @spec TEL-059
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_the_listener_has_been_called_when_the_call_handler_returns() -> None:
    heard = Heard()

    await _call_handler(_server(_harness(), heard))("get_state", NO_SUCH_GAME)

    assert len(heard.calls) == 1


# @spec TEL-059
async def test_a_synchronous_listener_is_called_without_any_failure_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _heard_of(_harness(), "get_state", NO_SUCH_GAME)

    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == []


# ------------------------------------------------------------------ the status heard


# @spec TEL-002
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_an_ok_answer_is_heard_as_ok() -> None:
    harness = _harness()
    game_id = _in_main_step_with_forests(harness)

    heard = await _heard_of(harness, "play", {"game_id": game_id, "card": "Forest"})

    assert heard.outcomes == [("play", "OK")]


# @spec TEL-002
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_rejected_answer_is_heard_as_rejected() -> None:
    harness = _harness()
    game_id = _in_main_step_with_forests(harness)
    heard = Heard()
    play = {"game_id": game_id, "card": "Forest", "from": "hand"}

    async with Client(_server(harness, heard)) as client:
        await client.call_tool("play", play)
        await client.call_tool("play", play)

    assert heard.outcomes[-1] == ("play", "REJECTED")


# @spec TEL-002
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_choice_answer_is_heard_as_choice() -> None:
    harness = _harness()
    game_id = _in_main_step_with_forests(harness)
    look = {"look": {"n": 2, "from": "top", "rest": "library_bottom"}}

    heard = await _heard_of(
        harness, "effect", {"game_id": game_id, "source": "Ponder", "delta": look}
    )

    assert heard.outcomes == [("effect", "CHOICE")]


# @spec TEL-002
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_an_error_answer_is_heard_as_error() -> None:
    heard = await _heard_of(_harness(), "get_state", NO_SUCH_GAME)

    assert heard.outcomes == [("get_state", "ERROR")]


# @spec TEL-002
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_call_with_arguments_of_the_wrong_shape_is_heard_as_error() -> None:
    harness = _harness()
    game_id = _in_main_step_with_forests(harness)

    heard = await _heard_of(harness, "play", {"game_id": game_id, "card": 12})

    assert heard.outcomes == [("play", "ERROR")]


# @spec TEL-002, TEL-008
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_an_answer_that_opens_with_a_digest_is_heard_with_its_status_word() -> None:
    harness = _harness()
    game_id = harness.started_contested_game(opposing=1)
    ToolSurface(harness.service).call("mulligan", {"game_id": game_id, "keep": True})

    heard = await _heard_of(harness, "get_state", {"game_id": harness.seat_id(game_id, 2)})

    assert heard.outcomes == [("get_state", "OK")]


# ------------------------------------------------------------------ a tool that does not exist


# @spec TEL-003
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_call_naming_a_tool_that_does_not_exist_is_heard_as_an_unknown_protocol_error() -> (
    None
):
    heard = Heard()

    async with Client(_server(_harness(), heard)) as client:
        with pytest.raises(MCPError):
            await client.call_tool("cast", {"card": "Forest"})

    assert heard.outcomes == [("unknown", "PROTOCOL_ERROR")]


# @spec TEL-003
async def test_a_call_naming_a_tool_that_does_not_exist_is_answered_as_without_a_listener() -> None:
    heard = await _answer(_server(_harness(), Heard()), "cast", {"card": "Forest"})
    unheard = await _answer(_server(_harness()), "cast", {"card": "Forest"})

    assert heard == unheard


# ------------------------------------------------------------------ a tool that raised


# @spec TEL-004
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_tool_that_raised_is_heard_as_a_defect() -> None:
    heard = Heard()
    harness = a_service(renderer=BrokenRenderer())

    with pytest.raises(RendererBroke):
        await _call_handler(_server(harness, heard))("get_state", NO_SUCH_GAME)

    assert heard.outcomes == [("get_state", "DEFECT")]


# @spec TEL-004
async def test_a_tool_s_exception_goes_on_to_the_sdk_as_the_same_exception() -> None:
    renderer = BrokenRenderer()
    harness = a_service(renderer=renderer)

    with pytest.raises(RendererBroke) as raised:
        await _call_handler(_server(harness, Heard()))("get_state", NO_SUCH_GAME)

    assert raised.value is renderer.failure


# ------------------------------------------------------------------ a cancelled call


# @spec TEL-005
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_call_cancelled_before_its_result_is_heard_as_cancelled() -> None:
    heard = Heard()

    await _cancelled_before_the_result(_server(_harness(), heard))

    assert heard.outcomes == [("get_state", "CANCELLED")]


# @spec TEL-005
async def test_a_cancellation_before_the_result_goes_on() -> None:
    assert await _cancelled_before_the_result(_server(_harness(), Heard()))


# @spec TEL-005
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_call_cancelled_after_its_result_is_heard_with_its_status_word() -> None:
    heard = Heard()
    with anyio.CancelScope() as cancel_scope:
        renderer = WatchedRenderer(lambda: anyio.from_thread.run_sync(cancel_scope.cancel))
        call = _call_handler(_server(a_service(renderer=renderer), heard))
        await call("get_state", NO_SUCH_GAME)
        await anyio.lowlevel.checkpoint()

    assert heard.outcomes == [("get_state", "ERROR")]


# ------------------------------------------------------------------ a listener that raises


# @spec TEL-006
async def test_a_call_is_answered_as_without_a_listener_when_the_listener_raises() -> None:
    heard = await _answer(_server(_harness(), FailingListener()), "get_state", NO_SUCH_GAME)
    unheard = await _answer(_server(_harness()), "get_state", NO_SUCH_GAME)

    assert heard == unheard


# @spec TEL-006
async def test_an_unknown_tool_is_answered_as_without_a_listener_when_the_listener_raises() -> None:
    heard = await _answer(_server(_harness(), FailingListener()), "cast", {"card": "Forest"})
    unheard = await _answer(_server(_harness()), "cast", {"card": "Forest"})

    assert heard == unheard


# @spec TEL-006
async def test_a_tool_s_exception_goes_on_when_the_listener_raises() -> None:
    renderer = BrokenRenderer()
    harness = a_service(renderer=renderer)

    with pytest.raises(RendererBroke) as raised:
        await _call_handler(_server(harness, FailingListener()))("get_state", NO_SUCH_GAME)

    assert raised.value is renderer.failure


# @spec TEL-006
async def test_a_cancellation_goes_on_when_the_listener_raises() -> None:
    assert await _cancelled_before_the_result(_server(_harness(), FailingListener()))


# @spec TEL-006
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
async def test_a_listener_that_raises_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    listener = FailingListener()

    await _answer(_server(_harness(), listener), "get_state", NO_SUCH_GAME)

    assert any(
        record.name.startswith("mtg_goldfishing")
        and record.exc_info is not None
        and record.exc_info[1] is listener.failure
        for record in caplog.records
    )


# ------------------------------------------------------------------ no listener


# @spec TEL-007
async def test_without_a_listener_nothing_is_timed() -> None:
    clock = SteppedClock()

    await _answer(_server(_harness(), timer=clock), "get_state", NO_SUCH_GAME)

    assert clock.reads == 0


# @spec TEL-007
async def test_a_call_is_answered_the_same_with_a_listener_and_without() -> None:
    def answered(listener: ToolCallListener | None) -> Awaitable[object]:
        harness = _harness()
        game_id = _in_main_step_with_forests(harness)
        return _answer(_server(harness, listener), "play", {"game_id": game_id, "card": "Forest"})

    assert await answered(Heard()) == await answered(None)


# @spec TEL-007
def test_the_http_application_without_a_listener_answers_tool_calls() -> None:
    app = create_app(_harness().service)
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_state", "arguments": NO_SUCH_GAME},
    }

    with TestClient(app, base_url=LOCAL) as http:
        response = http.post("/mcp", headers=MCP_HEADERS, json=call)

    assert '"isError":true' in response.text.replace(" ", "")


# ------------------------------------------------------------------ the status word stays home


# @spec TEL-008
async def test_the_status_word_is_never_sent_to_the_client_beside_the_text() -> None:
    async with Client(_server(_harness(), Heard())) as client:
        result = await client.call_tool("get_state", NO_SUCH_GAME)

    sent = result.model_dump(exclude_none=True, by_alias=True)
    sent["content"] = []
    assert "ERROR" not in json.dumps(sent)
