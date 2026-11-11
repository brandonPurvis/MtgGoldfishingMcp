"""`choose`: answer the pending choice addressed to the calling seat."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play import choosing

TOOL = "choose"


def choose(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operate(game: Game, decks: Decks, seat: SeatNumber, override: str | None) -> Result:
        return choosing.choose(
            game,
            decks.of(seat),
            seat,
            choice_id=arguments.get("choice_id"),
            selections=arguments.get("selections"),
            rest_order=arguments.get("rest_order"),
            delta=arguments.get("delta"),
            blocks=arguments.get("blocks"),
            override=override,
            decks=decks,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))
