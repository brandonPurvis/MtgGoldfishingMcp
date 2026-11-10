"""`end_game`: end the game with a result and verdict."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game import ending
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result

TOOL = "end_game"


def end_game(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operation(game: Game, deck: LoadedDeck) -> Result:
        return ending.end_game(
            game, deck, result=arguments.get("result"), notes=arguments.get("notes")
        )

    return change_game(ports, TOOL, arguments, operation)
