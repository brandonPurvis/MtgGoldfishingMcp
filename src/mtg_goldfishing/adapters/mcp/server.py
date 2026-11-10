"""The MCP server: lists the tools and answers each call with one text content item.

Built on the SDK's low-level server so that the input schemas it lists are the adapter's
own and nothing in the SDK validates arguments before the tools shape them: a call of the
wrong shape is answered as an `ERROR` in the text format, never as a protocol fault.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

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


def _service_version() -> str:
    try:
        return version("mtg-goldfishing")
    except PackageNotFoundError:
        return ""


# @spec TOOL-001, TOOL-007, TOOL-012, TOOL-027
def mcp_server(tools: ToolSurface) -> Server[Any]:
    """The `goldfishing` MCP server over the tool surface."""
    listed = [
        Tool(name=d.name, description=d.description, input_schema=d.input_schema)
        for d in tools.definitions
    ]

    async def list_tools(
        context: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=listed)

    async def call_tool(
        context: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult:
        if not tools.offers(params.name):
            raise MCPError(INVALID_PARAMS, f"Unknown tool: {params.name}")
        function = tools.function(params.name)
        arguments: Mapping[str, object] = params.arguments or {}
        response = await anyio.to_thread.run_sync(function, arguments)
        return CallToolResult(content=[TextContent(text=response.text)], is_error=response.is_error)

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
