"""Reading a deck list: one entry per line, in the formats deck sites export."""

from __future__ import annotations

import re

from mtg_goldfishing.domain.cards import same_name
from mtg_goldfishing.domain.deck.model import DeckEntry
from mtg_goldfishing.domain.events import Error, ErrorKind

_COMMENT_MARKS = ("#", "//")
_COUNTED = re.compile(r"^(?P<count>[+-]?\d+)[xX]?(?:\s+(?P<name>.*))?$")
_PRINTING_DETAILS = re.compile(r"\s*\(.*$")


def _is_ignored(line: str) -> bool:
    return not line or line.startswith(_COMMENT_MARKS)


def _read_line(line: str, number: int) -> DeckEntry | Error:
    """One entry from a line: `<count> <name>`, `<count>x <name>` or a bare `<name>`."""
    counted = _COUNTED.match(line)
    count, name = (int(counted["count"]), counted["name"] or "") if counted else (1, line)
    name = _PRINTING_DETAILS.sub("", name).strip()
    if counted and count <= 0:
        return Error(ErrorKind.COUNT_NOT_POSITIVE, subject=line, number=number)
    if not name:
        return Error(ErrorKind.LINE_UNREADABLE, subject=line, number=number)
    return DeckEntry(name, count)


# @spec DECK-001, DECK-002, DECK-003, DECK-004, DECK-005
def parse_deck_list(text: str) -> tuple[DeckEntry, ...] | Error:
    """The entries of a deck list, in the order their cards first appear.

    Blank and comment lines are ignored, printing details from a parenthesised set code on
    are dropped, and the counts of a name given on several lines (in any letter case) are
    added together under its first spelling. A line is named by its text and line number.
    """
    entries: list[DeckEntry] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if _is_ignored(line):
            continue
        entry = _read_line(line, number)
        if isinstance(entry, Error):
            return entry
        for index, earlier in enumerate(entries):
            if same_name(earlier.name, entry.name):
                entries[index] = DeckEntry(earlier.name, earlier.count + entry.count)
                break
        else:
            entries.append(entry)
    return tuple(entries)
