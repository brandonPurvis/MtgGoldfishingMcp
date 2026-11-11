"""`choose`: finish a look or search by saying where the revealed cards go."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play import choosing

TOOL = "choose"


def choose(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operation(game: Game, deck: LoadedDeck, seat: SeatNumber) -> Result:
        return choosing.choose(
            game,
            deck,
            seat,
            choice_id=arguments.get("choice_id"),
            selections=arguments.get("selections"),
            rest_order=arguments.get("rest_order"),
        )

    return change_game(ports, TOOL, arguments, operation)
