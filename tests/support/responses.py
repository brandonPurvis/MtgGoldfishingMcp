"""Reading a text response: a contested game's response may begin with digest lines, before
the line that starts with the status word."""

from __future__ import annotations

import re

HEADLINE = re.compile(r"^(OK|REJECTED|ERROR|CHOICE)\b")


def headline(text: str) -> str:
    """The status-and-summary line: the first line that begins with a status word."""
    return next((line for line in text.splitlines() if HEADLINE.match(line)), text)


def digest_lines(text: str) -> list[str]:
    """The digest lines a response begins with: every line before its headline."""
    lines = text.splitlines()
    first = next((i for i, line in enumerate(lines) if HEADLINE.match(line)), 0)
    return lines[:first]
