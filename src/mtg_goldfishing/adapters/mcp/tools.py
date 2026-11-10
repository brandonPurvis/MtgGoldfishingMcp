"""The tools as plain functions: shape a call's arguments, hand it to its use case, answer.

Each tool takes the call's arguments as a dictionary and returns the response text with
the MCP error flag. A call whose arguments cannot be shaped goes to the service as a
malformed call, so it too is answered in the text format and kept as a call record. No
rule of play is decided here; every call reaches the service through one of its use cases.

The functions are what the MCP server calls, and what feature tests drive in-process.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from mtg_goldfishing.adapters.mcp.definitions import TOOL_DEFINITIONS, ToolDefinition
from mtg_goldfishing.adapters.mcp.parameters import Misshapen, shape
from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.application.service import Service

UseCase = Callable[[Service, Mapping[str, object]], Answer]

USE_CASES: dict[str, UseCase] = {
    "load_deck": Service.load_deck,
    "new_game": Service.new_game,
    "mulligan": Service.mulligan,
    "get_state": Service.get_state,
    "play": Service.play,
    "effect": Service.effect,
    "choose": Service.choose,
    "attack": Service.attack,
    "advance": Service.advance,
    "end_game": Service.end_game,
    "get_log": Service.get_log,
}


@dataclass(frozen=True)
class ToolResponse:
    """What a tool call returns to the agent: one text, and whether it is an `ERROR`."""

    text: str
    is_error: bool


ToolFunction = Callable[[Mapping[str, object]], ToolResponse]


class ToolSurface:
    """The eleven tools over one service."""

    def __init__(self, service: Service) -> None:
        self._service = service
        self._definitions = {definition.name: definition for definition in TOOL_DEFINITIONS}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())

    def definition(self, name: str) -> ToolDefinition:
        return self._definitions[name]

    def offers(self, name: str) -> bool:
        return name in self._definitions

    def function(self, name: str) -> ToolFunction:
        """The tool as a plain function of its arguments."""
        definition = self._definitions[name]
        return lambda arguments: self._call(definition, arguments)

    # @spec TOOL-010, TOOL-013, TOOL-027, TOOL-028
    def call(self, name: str, arguments: Mapping[str, object]) -> ToolResponse:
        """Answer one call of the tool `name`."""
        return self._call(self._definitions[name], arguments)

    def _call(self, definition: ToolDefinition, arguments: Mapping[str, object]) -> ToolResponse:
        shaped = shape(definition.parameters, arguments)
        if isinstance(shaped, Misshapen):
            answer = self._service.malformed_call(definition.name, arguments, shaped.problems)
        else:
            answer = USE_CASES[definition.name](self._service, shaped.arguments)
        return ToolResponse(answer.response, answer.outcome.status is Status.ERROR)
