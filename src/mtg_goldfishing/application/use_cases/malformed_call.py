"""A call whose arguments the MCP adapter could not shape: answered as an error and recorded."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.arguments import malformed
from mtg_goldfishing.application.use_cases.handling import Call, Ports, refused
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.game.results import Refusal
from mtg_goldfishing.domain.game.summary import summarize


# @spec APP-027
def malformed_call(
    ports: Ports, tool: str, arguments: Mapping[str, object], problems: Sequence[str]
) -> Answer:
    """An `ERROR` with one malformed-argument error per problem, as the adapter named them.

    When the call's `game_id` names an existing game the outcome carries its summary; the
    game's lock is held while it is read. Nothing but the call record is saved.
    """
    errors = tuple(malformed(problem) for problem in problems) or (
        Error(ErrorKind.MALFORMED_ARGUMENT),
    )
    refusal = Refusal(errors=errors)
    game_id = arguments.get("game_id")
    if not isinstance(game_id, str):
        call = Call(ports, tool, arguments, None)
        return call.guarded(lambda: call.finish(refused(refusal, None)))
    call = Call(ports, tool, arguments, game_id)

    def answer() -> Answer:
        stored = ports.games.get(game_id)
        deck = None if stored is None else ports.decks.get(stored.game.deck_id)
        if stored is not None and deck is not None:
            call.game = summarize(stored.game, deck)
        return call.finish(refused(refusal, call.game))

    with ports.locks.hold(game_id):
        return call.guarded(answer)
