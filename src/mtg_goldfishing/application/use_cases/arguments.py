"""Reading a call's plain arguments: a change number, a piece of text, a true-or-false flag.

The structured arguments (`delta`, `choices`, `pay`, `expect`, `selections`,
`definitions`) and every argument naming a card, a zone or a step are read by the domain.
What is left is whether a plain argument has the type its tool declares; a value of
another type is a malformed argument.
"""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.domain.events import Error, ErrorKind


def malformed(name: str) -> Error:
    """The error for an argument that does not have the type its tool declares."""
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject=name)


def whole_number(arguments: Mapping[str, object], name: str) -> int | Error | None:
    """The argument as a whole number, None when absent or null."""
    value = arguments.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return malformed(name)
    return value


def text(arguments: Mapping[str, object], name: str) -> str | Error | None:
    """The argument as text, None when absent or null."""
    value = arguments.get(name)
    if value is None or isinstance(value, str):
        return value
    return malformed(name)


def flag(arguments: Mapping[str, object], name: str, *, default: bool) -> bool | Error:
    """The argument as true or false, `default` when absent or null."""
    value = arguments.get(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return malformed(name)


def errors_in(*read: object) -> tuple[Error, ...]:
    """The errors among the values read, in order."""
    return tuple(value for value in read if isinstance(value, Error))
