"""`load_deck`: look the list's cards up, let the domain build and check the deck, keep it."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer, Outcome, Status
from mtg_goldfishing.application.use_cases.arguments import flag
from mtg_goldfishing.application.use_cases.handling import Call, Ports, refused
from mtg_goldfishing.domain.deck import loading
from mtg_goldfishing.domain.events import Error
from mtg_goldfishing.domain.game.results import Refusal

TOOL = "load_deck"


# @spec DECK-018, DECK-031, APP-019
def load_deck(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """Load a deck list. A deck already loaded is answered as it is and not added again.

    The only card data touched is what the card catalog answers; nothing is written to it.
    """
    call = Call(ports, TOOL, arguments, None)
    return call.guarded(lambda: _load(call, arguments))


def _load(call: Call, arguments: Mapping[str, object]) -> Answer:
    request = loading.read_deck_request(
        cards=arguments.get("cards"),
        commander=arguments.get("commander"),
        definitions=arguments.get("definitions"),
        override=arguments.get("override"),
    )
    refresh = flag(arguments, "refresh", default=False)
    if isinstance(request, Refusal) or isinstance(refresh, Error):
        errors = request.errors if isinstance(request, Refusal) else ()
        if isinstance(refresh, Error):
            errors = (*errors, refresh)
        return call.finish(refused(Refusal(errors=errors), None))
    lookups = call.ports.catalog.look_up(request.names_to_look_up, refresh=refresh)
    loaded = loading.load_deck(request, lookups, existing=call.ports.decks.get)
    if isinstance(loaded, Refusal):
        return call.finish(refused(loaded, None))
    outcome = Outcome(Status.OK, loaded.summary, loaded.events)
    if loaded.summary.already_loaded:
        return call.finish(outcome)

    def write() -> Outcome | None:
        call.ports.decks.add(loaded.deck)
        return None

    return call.finish(outcome, write)
