"""`advance`: move to the next step, or forward to a named step."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain import turn
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber

TOOL = "advance"


def advance(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operate(game: Game, decks: Decks, seat: SeatNumber, override: str | None) -> Result:
        return turn.advance(
            game,
            decks.of(seat),
            seat,
            to=arguments.get("to"),
            discard=arguments.get("discard"),
            override=override,
            decks=decks,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))
