"""`get_state`: list the zones when the status line is not enough, or give cards' rules text.
Changes nothing."""

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
from mtg_goldfishing.domain.events import Error, RulesTextGiven, StateListed
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.rules_text import rules_text

TOOL = "get_state"


# @spec REC-002, GAME-186
def get_state(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """The listing at the detail asked for, or, when `card` is given, the rules text of the
    cards it names in place of the listing."""

    def read(call: Call, loaded: Loaded) -> Outcome:
        card = arguments.get("card")
        if card is not None:
            text = rules_text(
                loaded.game, loaded.decks, loaded.seat, card, detail=arguments.get("detail")
            )
            if isinstance(text, Error):
                return an_error(text, loaded.summary)
            return Outcome(Status.OK, RulesTextGiven(len(text.cards)), (), loaded.summary, text)
        listing = list_state(
            loaded.game, loaded.deck, loaded.seat, arguments.get("detail"), loaded.decks
        )
        if isinstance(listing, Error):
            return an_error(listing, loaded.summary)
        detail = "summary" if listing.library_size is None else "full"
        return Outcome(Status.OK, StateListed(detail), (), loaded.summary, listing)

    return answer_read_only(ports, TOOL, arguments, read)
