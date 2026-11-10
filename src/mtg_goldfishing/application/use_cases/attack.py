"""`attack`: declare attackers and which are blocked."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain.combat import attack as attacks
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber

TOOL = "attack"


def attack(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    def operate(game: Game, decks: Decks, seat: SeatNumber, override: str | None) -> Result:
        return attacks.attack(
            game,
            decks.of(seat),
            seat,
            attackers=arguments.get("attackers"),
            blocked=arguments.get("blocked"),
            commander_target=arguments.get("commander_target"),
            damage=arguments.get("damage"),
            vigilance=arguments.get("vigilance"),
            haste=arguments.get("haste"),
            override=override,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))
