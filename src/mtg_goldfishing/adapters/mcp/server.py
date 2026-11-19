"""The MCP server: lists the tools and answers each call with one text content item.

Built on the SDK's low-level server so that the input schemas it lists are the adapter's
own and nothing in the SDK validates arguments before the tools shape them: a call of the
wrong shape is answered as an `ERROR` in the text format, never as a protocol fault.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import anyio
import anyio.to_thread
from mcp.server import Server, ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from mtg_goldfishing.adapters.mcp.instructions import SERVER_INSTRUCTIONS, SERVER_NAME
from mtg_goldfishing.adapters.mcp.tools import ToolSurface

_log = logging.getLogger(__name__)

ToolCallListener = Callable[[str, str, float], None]
"""Told of each tool call: the tool's name, the status it ended with and its seconds."""

UNKNOWN_TOOL = "unknown"
"""The tool name a call naming a tool that does not exist is told under."""
PROTOCOL_ERROR = "PROTOCOL_ERROR"
DEFECT = "DEFECT"
CANCELLED = "CANCELLED"


def _service_version() -> str:
    try:
        return version("mtg-goldfishing")
    except PackageNotFoundError:
        return ""


# @spec TOOL-001, TOOL-007, TOOL-012, TOOL-027
# @spec TEL-001, TEL-002, TEL-003, TEL-004, TEL-005, TEL-006, TEL-007, TEL-059
def mcp_server(
    tools: ToolSurface,
    *,
    on_tool_call: ToolCallListener | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> Server[Any]:
    """The `goldfishing` MCP server over the tool surface.

    With `on_tool_call`, each call the call handler receives is timed with `timer` and told
    to the listener once, synchronously; with none, nothing is measured.
    """
    listed = [
        Tool(name=d.name, description=d.description, input_schema=d.input_schema)
        for d in tools.definitions
    ]

    async def list_tools(
        context: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=listed)

    async def answer(params: CallToolRequestParams) -> tuple[CallToolResult, str]:
        """The call's result and the status word of the tool's answer."""
        if not tools.offers(params.name):
            raise MCPError(INVALID_PARAMS, f"Unknown tool: {params.name}")
        function = tools.function(params.name)
        arguments: Mapping[str, object] = params.arguments or {}
        response = await anyio.to_thread.run_sync(function, arguments)
        result = CallToolResult(
            content=[TextContent(text=response.text)], is_error=response.is_error
        )
        return result, response.status

    async def call_tool(
        context: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult:
        if on_tool_call is None:
            return (await answer(params))[0]
        return await _measured(answer, params, tools.offers(params.name), on_tool_call, timer)

    def input_schema(name: str) -> Mapping[str, Any] | None:
        return tools.definition(name).input_schema if tools.offers(name) else None

    return Server(
        SERVER_NAME,
        version=_service_version(),
        instructions=SERVER_INSTRUCTIONS,
        get_tool_input_schema=input_schema,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


Answer = Callable[[CallToolRequestParams], Awaitable[tuple[CallToolResult, str]]]


async def _measured(
    answer: Answer,
    params: CallToolRequestParams,
    offered: bool,
    listener: ToolCallListener,
    timer: Callable[[], float],
) -> CallToolResult:
    """Answer the call, telling the listener how it ended; the result, exception or
    cancellation goes on as it would unmeasured."""
    name = params.name if offered else UNKNOWN_TOOL
    started = timer()
    try:
        result, status = await answer(params)
    except anyio.get_cancelled_exc_class():
        _tell(listener, name, CANCELLED, timer() - started)
        raise
    except Exception:
        # A tool that is not offered is refused with a protocol error; any other exception
        # is the tool raising instead of answering.
        _tell(listener, name, DEFECT if offered else PROTOCOL_ERROR, timer() - started)
        raise
    _tell(listener, name, status, timer() - started)
    return result


def _tell(listener: ToolCallListener, name: str, status: str, seconds: float) -> None:
    """Call the listener; what it raises is logged and goes no further."""
    try:
        listener(name, status, seconds)
    except Exception:
        _log.exception("the tool-call listener failed on a %s call", name)
