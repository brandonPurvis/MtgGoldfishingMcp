"""`new_game`: draw a game id, any seed and a seat id per opposing seat, let the domain deal,
keep the game."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer, Outcome, Status
from mtg_goldfishing.application.use_cases.arguments import errors_in, malformed, whole_number
from mtg_goldfishing.application.use_cases.handling import Call, Ports, refused
from mtg_goldfishing.domain.events import Error
from mtg_goldfishing.domain.game import creation
from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.results import Refusal
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.records.log import log_entry

TOOL = "new_game"
GAME_ID_PREFIX = "g"


def _opponents(arguments: Mapping[str, object]) -> list[str] | Error:
    """The opposing decks' ids as given: a list of text; absent, none."""
    value = arguments.get("opponents")
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(deck_id, str) for deck_id in value):
        return list(value)
    return malformed("opponents")


# @spec GAME-004, GAME-006, APP-017, APP-061, APP-087, REC-059, REC-060
def new_game(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """Start a game on a loaded deck, against the loaded decks of `opponents` if any.

    The id source gives the game id first — `g` and ten characters — then a seed when the
    call gave none, then one seat id per opposing seat in `opponents` order, so the seat ids
    a seat receives do not depend on the turn order the seed draws. The new game, its first
    log entry and the call record are saved in one unit of work. The call record of a
    contested game keeps the response with every opposing seat's seat id redacted, and
    names no seat: whoever starts the game is none of them.
    """
    call = Call(ports, TOOL, arguments, None)
    return call.guarded(lambda: _start(call, arguments))


def _start(call: Call, arguments: Mapping[str, object]) -> Answer:
    deck_id = arguments.get("deck_id")
    seed = whole_number(arguments, "seed")
    opponents = _opponents(arguments)
    if not isinstance(deck_id, str) or isinstance(seed, Error) or isinstance(opponents, Error):
        no_deck_id = () if isinstance(deck_id, str) else (malformed("deck_id"),)
        errors = (*no_deck_id, *errors_in(seed, opponents))
        return call.finish(refused(Refusal(errors=errors), None))
    ports = call.ports
    game_id = GAME_ID_PREFIX + ports.ids.new_game_id()
    with ports.locks.hold(game_id):
        deck = ports.decks.get(deck_id)
        seed_used = ports.ids.new_seed() if seed is None else seed
        opposing = [
            creation.OpposingDeck(
                opponent, ports.decks.get(opponent), GAME_ID_PREFIX + ports.ids.new_seat_id()
            )
            for opponent in opponents
        ]
        result = creation.new_game(
            deck,
            deck_id=deck_id,
            game_id=game_id,
            seed=seed_used,
            turn_limit=arguments.get("turn_limit"),
            draw_first_turn=arguments.get("draw_first_turn"),
            opposing=opposing,
            starting_life=arguments.get("starting_life"),
            position=arguments.get("position"),
        )
        if isinstance(result, Refusal):
            return call.finish(refused(result, None))
        assert deck is not None, "the domain refuses a game on a deck that is not loaded"
        tested = result.game.tested.number
        applied = accept_change(result, tested, TOOL, arguments)
        game = applied.game
        entry = log_entry(
            tool=TOOL,
            arguments=arguments,
            before=None,
            after=game,
            summary=applied.summary,
            events=applied.events,
            seat=None,
        )
        call.game_id = game.game_id
        call.about(game)
        outcome = Outcome(Status.OK, applied.summary, applied.events, summarize(game, deck, tested))

        def write() -> Outcome | None:
            ports.games.add(game)
            ports.records.append_entry(game.game_id, entry)
            for snapshot in applied.snapshots:
                ports.records.add_snapshot(game.game_id, snapshot)
            call.announcement = (game.game_id, game.change)
            return None

        return call.finish(outcome, write)
