"""`effect`: record anything that happens without playing a card."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.play import playing

TOOL = "effect"


def effect(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operate(game: Game, deck: LoadedDeck, override: str | None) -> Result:
        return playing.effect(
            game,
            deck,
            source=arguments.get("source"),
            delta=arguments.get("delta"),
            choices=arguments.get("choices"),
            pay=arguments.get("pay"),
            expect=arguments.get("expect"),
            reason=arguments.get("reason"),
            override=override,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))
