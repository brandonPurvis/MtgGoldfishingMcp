"""The filters that narrow a get_log export: `seat`, the seat whose records to keep, and
`tools`, the tools whose records to keep. A filter that cannot be applied is an error; one
that matches nothing is not."""

from __future__ import annotations

import json

from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.game.calls import SERVICE_TOOLS
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber


# @spec REC-093, REC-094
def seat_filter(game: Game, number: int | None) -> SeatNumber | Error | None:
    """The seat whose records to keep, None for no `seat`.

    A goldfish game's records name no seat, so `seat` is used only in a contested game; a
    number naming none of the game's seats is an error listing them.
    """
    if number is None:
        return None
    if not game.contested:
        return Error(ErrorKind.CONTESTED_ONLY, subject="seat")
    seats = [seat.number for seat in game.seats]
    if all(seat.value != number for seat in seats):
        return Error(
            ErrorKind.NO_SUCH_SEAT, number=number, names=tuple(str(s.value) for s in seats)
        )
    return SeatNumber(number)


# @spec REC-090, REC-095, REC-096
def tools_filter(value: object) -> frozenset[str] | Error | None:
    """The tools whose records to keep, None for no `tools`; a name listed twice counts once.

    `tools` is a list of the service's tool names, each exactly as the tool is called. An
    empty list, or one holding anything else, is an error that lists the tools.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="tools")
    if not value:
        return Error(ErrorKind.NO_TOOLS_NAMED, names=SERVICE_TOOLS)
    unknown = [item for item in value if item not in SERVICE_TOOLS]
    if unknown:
        named = ", ".join(_written(item) for item in unknown)
        return Error(ErrorKind.UNKNOWN_TOOL, subject=named, names=SERVICE_TOOLS)
    return frozenset(str(item) for item in value)


def _written(item: object) -> str:
    """A list item as it was written: text as it is, anything else as JSON (`5`, `null`)."""
    return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str)
