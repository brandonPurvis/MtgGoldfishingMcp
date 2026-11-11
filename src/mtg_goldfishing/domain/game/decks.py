"""The loaded deck each seat of a game plays."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber


@dataclass(frozen=True)
class Decks:
    """Each seat's loaded deck, by seat number: where the rules find what a seat's cards are."""

    by_seat: Mapping[SeatNumber, LoadedDeck] = field(default_factory=dict)

    def of(self, seat: SeatNumber) -> LoadedDeck:
        """The deck a seat plays; asking for a seat the game does not have is a defect."""
        return self.by_seat[seat]

    @classmethod
    def everyone_playing(cls, game: Game, deck: LoadedDeck) -> Decks:
        """Every seat of the game playing the one deck."""
        return cls({seat.number: deck for seat in game.seats})
