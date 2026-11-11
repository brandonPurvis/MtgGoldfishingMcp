"""The seat to act: which seats the game is waiting on, and which calls it accepts from a seat."""

from __future__ import annotations

from mtg_goldfishing.domain.events import Error
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber


def seats_to_act(game: Game) -> object:
    """The seats the game is waiting on and what they are asked; not built yet."""
    raise NotImplementedError("M3a: the seat to act is not built")


def may_call(game: Game, seat: SeatNumber, tool: str) -> Error | None:
    """The error refusing a call from `seat` now, or None when the game accepts it; not built."""
    raise NotImplementedError("M3a: the seat to act is not built")
