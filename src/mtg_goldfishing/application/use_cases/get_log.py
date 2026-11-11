"""`get_log`: the game's records as data for analysis. Accepted in every status; changes nothing."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer, Outcome, Status
from mtg_goldfishing.application.use_cases.arguments import errors_in, flag, whole_number
from mtg_goldfishing.application.use_cases.handling import (
    Call,
    Loaded,
    Ports,
    answer_read_only,
    refused,
)
from mtg_goldfishing.domain.events import Error, LogExported
from mtg_goldfishing.domain.game.results import Refusal
from mtg_goldfishing.domain.records.export import export
from mtg_goldfishing.domain.records.filters import seat_filter, tools_filter

TOOL = "get_log"


# @spec REC-002, REC-018, REC-023, REC-055, GAME-152, REC-089, REC-090, REC-093, REC-094
# @spec REC-095, REC-096
def get_log(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """Export the game's records; the export is the outcome's payload. Any seat of a
    contested game reads the same record, every seat's hidden zones included, narrowed only
    by the filters it gives. Every argument that is malformed or a filter that cannot be
    applied is named in one error response, in parameter order.

    The call record keeps what `Renderer` gives as the record's text, a note of the
    export's size, in place of the export itself.
    """

    def read(call: Call, loaded: Loaded) -> Outcome:
        since = whole_number(arguments, "since")
        number = whole_number(arguments, "seat")
        seat = number if isinstance(number, Error) else seat_filter(loaded.game, number)
        tools = tools_filter(arguments.get("tools"))
        include_snapshots = flag(arguments, "include_snapshots", default=True)
        include_calls = flag(arguments, "include_calls", default=False)
        if (
            isinstance(since, Error)
            or isinstance(seat, Error)
            or isinstance(tools, Error)
            or isinstance(include_snapshots, Error)
            or isinstance(include_calls, Error)
        ):
            errors = errors_in(since, seat, tools, include_snapshots, include_calls)
            return refused(Refusal(errors=errors), loaded.summary)
        records = call.ports.records.read(loaded.game.game_id)
        document = export(
            loaded.game,
            records.entries,
            records.snapshots,
            records.calls,
            since=since,
            seat=seat,
            tools=tools,
            include_snapshots=include_snapshots,
            include_calls=include_calls,
        )
        exported = LogExported(
            entries=_count(document, "entries"),
            snapshots=_count(document, "snapshots"),
            calls=_count(document, "calls"),
        )
        return Outcome(Status.OK, exported, (), loaded.summary, document)

    return answer_read_only(ports, TOOL, arguments, read)


def _count(document: Mapping[str, object], section: str) -> int:
    """How many records a section of the export holds; 0 for a section left out."""
    records = document.get(section)
    return len(records) if isinstance(records, list) else 0
