"""A tool's parameters, and shaping a call's arguments to them before the service sees them.

Shaping checks only the gross shape a JSON schema would: that every required parameter is
there, that each value has the JSON type its parameter declares, and that no unknown
parameter is given. A list or object sent as a JSON string is decoded. What the values
mean — whether a delta's keys exist, whether a card is in the zone named — is for the
service to judge, so a well-shaped call is passed on as received, absent and null alike.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum


class Kind(Enum):
    """The JSON shape a parameter's value takes."""

    TEXT = "text"
    WHOLE_NUMBER = "whole number"
    FLAG = "flag"
    OBJECT = "object"
    LIST = "list"
    TEXT_OR_LIST = "text or list"
    WHOLE_NUMBER_OR_OBJECT = "whole number or object"
    WHOLE_NUMBER_OR_LIST = "whole number or list"

    @property
    def json_types(self) -> tuple[str, ...]:
        """The JSON Schema types declared to clients; lists and objects admit a JSON string."""
        return _JSON_TYPES[self]


_JSON_TYPES: dict[Kind, tuple[str, ...]] = {
    Kind.TEXT: ("string",),
    Kind.WHOLE_NUMBER: ("integer",),
    Kind.FLAG: ("boolean",),
    Kind.OBJECT: ("object", "string"),
    Kind.LIST: ("array", "string"),
    Kind.TEXT_OR_LIST: ("string", "array"),
    Kind.WHOLE_NUMBER_OR_OBJECT: ("integer", "object", "string"),
    Kind.WHOLE_NUMBER_OR_LIST: ("integer", "array", "string"),
}


@dataclass(frozen=True)
class Parameter:
    """One parameter of a tool: its name, shape, meaning, and an example value."""

    name: str
    kind: Kind
    meaning: str
    example: object
    required: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.meaning:
            raise ValueError("a parameter needs a name and a meaning")
        if _value_is_shaped(self.kind, self.example) is None:
            raise ValueError(f"the example for {self.name} does not have its shape")

    @property
    def schema(self) -> dict[str, object]:
        types = self.kind.json_types
        return {"type": types[0] if len(types) == 1 else list(types)}


@dataclass(frozen=True)
class Shaped:
    """A call whose arguments have the shape of the tool's parameters, decoded where sent as
    JSON strings."""

    arguments: dict[str, object]


@dataclass(frozen=True)
class Misshapen:
    """A call the adapter cannot shape; `problems` names each argument at fault.

    `arguments` holds the call's arguments as received, with each one that has its
    parameter's shape decoded where it was sent as a JSON string.
    """

    problems: tuple[str, ...] = field(default=())
    arguments: dict[str, object] = field(default_factory=dict)


# @spec REC-017
def shape(parameters: Sequence[Parameter], arguments: Mapping[str, object]) -> Shaped | Misshapen:
    """The call's arguments shaped to `parameters`, or every argument that could not be."""
    known = {parameter.name: parameter for parameter in parameters}
    problems = [name for name in arguments if name not in known]
    shaped: dict[str, object] = {}
    for parameter in parameters:
        value = arguments.get(parameter.name)
        if value is None:
            if parameter.required:
                problems.append(parameter.name)
            elif parameter.name in arguments:
                shaped[parameter.name] = None
            continue
        fitted = _value_is_shaped(parameter.kind, value)
        if fitted is None:
            problems.append(parameter.name)
        else:
            shaped[parameter.name] = fitted.value
    if problems:
        received = {name: shaped.get(name, value) for name, value in arguments.items()}
        return Misshapen(tuple(problems), received)
    return Shaped(shaped)


@dataclass(frozen=True)
class _Fitted:
    value: object


def _value_is_shaped(kind: Kind, value: object) -> _Fitted | None:
    """The value as its parameter takes it, or None when it does not have the kind's shape."""
    if kind is Kind.TEXT:
        return _Fitted(value) if isinstance(value, str) else None
    if kind is Kind.WHOLE_NUMBER:
        return _Fitted(value) if _is_whole_number(value) else None
    if kind is Kind.FLAG:
        return _Fitted(value) if isinstance(value, bool) else None
    if kind is Kind.OBJECT:
        decoded = _decoded(value)
        return _Fitted(decoded) if isinstance(decoded, dict) else None
    if kind is Kind.LIST:
        decoded = _decoded(value)
        return _Fitted(decoded) if isinstance(decoded, list) else None
    if kind is Kind.TEXT_OR_LIST:
        if isinstance(value, str) and value.lstrip().startswith("["):
            decoded = _decoded(value)
            return _Fitted(decoded) if isinstance(decoded, list) else None
        return _Fitted(value) if isinstance(value, str | list) else None
    decoded = _decoded(value)
    if kind is Kind.WHOLE_NUMBER_OR_LIST:
        return _Fitted(decoded) if _is_whole_number(decoded) or isinstance(decoded, list) else None
    return _Fitted(decoded) if _is_whole_number(decoded) or isinstance(decoded, dict) else None


def _is_whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _decoded(value: object) -> object:
    """A JSON string's content; any other value as it is. An undecodable string stays a
    string, which then fits no list or object."""
    if not isinstance(value, str):
        return value
    try:
        decoded: object = json.loads(value)
    except json.JSONDecodeError:
        return value
    return decoded
