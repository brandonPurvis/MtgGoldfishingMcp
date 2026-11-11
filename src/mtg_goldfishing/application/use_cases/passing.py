"""`pass`: the seat a response window is asking declines to respond, or a reminded seat declines
to record its triggers now."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.use_cases.handling import Ports, change_game
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.stack import passing

TOOL = "pass"


# @spec STACK-055, TOOL-032
def pass_(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """A changing call like every other: accepted from the seat to act and following the
    change number given as `after`."""

    def operation(game: Game, decks: Decks, seat: SeatNumber) -> Result:
        return passing.pass_(game, decks.of(seat), seat, decks=decks)

    return change_game(ports, TOOL, arguments, operation)
