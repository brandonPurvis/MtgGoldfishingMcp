"""`effect`: record anything that happens without playing a card."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play import playing

TOOL = "effect"


def effect(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operate(game: Game, decks: Decks, seat: SeatNumber, override: str | None) -> Result:
        return playing.effect(
            game,
            decks.of(seat),
            seat,
            source=arguments.get("source"),
            delta=arguments.get("delta"),
            choices=arguments.get("choices"),
            pay=arguments.get("pay"),
            expect=arguments.get("expect"),
            reason=arguments.get("reason"),
            override=override,
            immediate=arguments.get("immediate"),
            decks=decks,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))
