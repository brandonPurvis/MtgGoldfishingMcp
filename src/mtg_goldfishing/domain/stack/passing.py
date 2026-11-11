"""`pass`: the seat to act declines to respond, or declines to record a reminded trigger now."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.game.seats import SeatNumber


def pass_(game: Game, deck: LoadedDeck, seat: SeatNumber, *, decks: Decks | None = None) -> Result:
    """The calling seat passes. Not built yet."""
    raise NotImplementedError("M4: pass is not built")
