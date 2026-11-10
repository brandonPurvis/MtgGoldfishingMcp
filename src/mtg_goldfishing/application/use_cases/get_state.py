"""`get_state`: list the zones when the status line is not enough. Changes nothing."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer, Outcome, Status
from mtg_goldfishing.application.use_cases.handling import (
    Call,
    Loaded,
    Ports,
    an_error,
    answer_read_only,
)
from mtg_goldfishing.domain.events import Error, StateListed
from mtg_goldfishing.domain.game.listing import list_state

TOOL = "get_state"


# @spec REC-002
def get_state(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def read(call: Call, loaded: Loaded) -> Outcome:
        listing = list_state(loaded.game, loaded.deck, arguments.get("detail"))
        if isinstance(listing, Error):
            return an_error(listing, loaded.summary)
        detail = "summary" if listing.library_size is None else "full"
        return Outcome(Status.OK, StateListed(detail), (), loaded.summary, listing)

    return answer_read_only(ports, TOOL, arguments, read)
