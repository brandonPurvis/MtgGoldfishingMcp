"""`mulligan`: keep the opening hand or take a mulligan."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game import mulligan as mulligans
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result

TOOL = "mulligan"


def mulligan(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operate(game: Game, deck: LoadedDeck, override: str | None) -> Result:
        return mulligans.mulligan(
            game,
            deck,
            keep=arguments.get("keep"),
            bottom=arguments.get("bottom"),
            override=override,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))
