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

TOOL = "get_log"


# @spec REC-002, REC-018, REC-023, REC-055, GAME-152
def get_log(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """Export the game's records; the export is the outcome's payload. Any seat of a
    contested game reads the same whole record, every seat's hidden zones included.

    The call record keeps what `Renderer` gives as the record's text, a note of the
    export's size, in place of the export itself.
    """

    def read(call: Call, loaded: Loaded) -> Outcome:
        since = whole_number(arguments, "since")
        include_snapshots = flag(arguments, "include_snapshots", default=True)
        include_calls = flag(arguments, "include_calls", default=False)
        if (
            isinstance(since, Error)
            or isinstance(include_snapshots, Error)
            or isinstance(include_calls, Error)
        ):
            errors = errors_in(since, include_snapshots, include_calls)
            return refused(Refusal(errors=errors), loaded.summary)
        records = call.ports.records.read(loaded.game.game_id)
        document = export(
            loaded.game,
            records.entries,
            records.snapshots,
            records.calls,
            since=since,
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
