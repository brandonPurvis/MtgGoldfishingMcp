"""The MCP server as a client sees it: tools listed, instructions given, results returned."""

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import TextContent

from mtg_goldfishing.adapters.mcp.instructions import SERVER_INSTRUCTIONS
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.mcp.server import mcp_server
from mtg_goldfishing.adapters.mcp.tools import ToolSurface
from tests.support.builders import a_game
from tests.support.service import ServiceHarness, a_service


def _client() -> tuple[Client, ServiceHarness]:
    harness = a_service(renderer=TextRenderer())
    return Client(mcp_server(ToolSurface(harness.service))), harness


def _game_in_main_step(harness: ServiceHarness) -> str:
    return harness.holding(a_game().with_battlefield("Forest").with_hand("Forest").build())


# @spec TOOL-001
async def test_the_server_introduces_itself_as_goldfishing() -> None:
    client, _ = _client()

    async with client:
        assert client.server_info is not None
        assert client.server_info.name == "goldfishing"


# @spec TOOL-012
async def test_the_server_gives_its_instructions_to_a_connecting_client() -> None:
    client, _ = _client()

    async with client:
        assert client.instructions == SERVER_INSTRUCTIONS


# @spec TOOL-007
async def test_the_server_lists_the_twelve_tools() -> None:
    client, _ = _client()

    async with client:
        listed = await client.list_tools()

    assert len({tool.name for tool in listed.tools}) == 12


# @spec TOOL-010, TOOL-028
async def test_a_listed_object_parameter_also_admits_a_json_string() -> None:
    client, _ = _client()

    async with client:
        listed = await client.list_tools()

    play = next(tool for tool in listed.tools if tool.name == "play")
    assert play.input_schema["properties"]["delta"]["type"] == ["object", "string"]


# @spec TOOL-027
async def test_a_response_is_one_text_content_item() -> None:
    client, harness = _client()
    game_id = _game_in_main_step(harness)

    async with client:
        result = await client.call_tool("play", {"game_id": game_id, "card": "Forest"})

    assert [type(item) for item in result.content] == [TextContent]


# @spec TOOL-027
async def test_an_error_response_sets_the_mcp_error_flag() -> None:
    client, _ = _client()

    async with client:
        result = await client.call_tool("get_state", {"game_id": "gnosuchgame"})

    assert result.is_error


# @spec TOOL-027
async def test_an_ok_response_leaves_the_mcp_error_flag_unset() -> None:
    client, harness = _client()
    game_id = _game_in_main_step(harness)

    async with client:
        result = await client.call_tool("play", {"game_id": game_id, "card": "Forest"})

    assert not result.is_error


# @spec TOOL-028
async def test_a_malformed_call_is_answered_in_the_text_error_format_not_as_a_fault() -> None:
    client, harness = _client()
    game_id = _game_in_main_step(harness)

    async with client:
        result = await client.call_tool("play", {"game_id": game_id, "card": 12})

    text = result.content[0]
    assert isinstance(text, TextContent)
    assert text.text.startswith("ERROR Argument card is malformed.")


# @spec TOOL-028
async def test_a_malformed_call_over_mcp_is_kept_as_a_call_record() -> None:
    client, harness = _client()
    game_id = _game_in_main_step(harness)

    async with client:
        await client.call_tool("play", {"game_id": game_id})

    assert (harness.last_call().tool, harness.last_call().game_id) == ("play", game_id)


# @spec TOOL-028
async def test_a_call_naming_a_tool_that_does_not_exist_is_a_protocol_error() -> None:
    client, harness = _client()

    async with client:
        with pytest.raises(MCPError):
            await client.call_tool("cast", {"card": "Forest"})

    assert harness.calls() == ()
