"""Rules text on request: `get_state` with `card` gives the rules text of the cards a seat names."""

from __future__ import annotations

from dataclasses import dataclass

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.events import Error
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, TokenSpec
from mtg_goldfishing.domain.game.seats import SeatNumber


@dataclass(frozen=True)
class RulesText:
    """What `get_state` answers for `card`: the card data of each card named, or the spec of
    each token named, once each, in the order first named. It says nothing of where any
    card is, nor which instance it is."""

    cards: tuple[Card | TokenSpec, ...]


def rules_text(
    game: Game, decks: Decks, seat: SeatNumber, card: object, *, detail: object = None
) -> RulesText | Error:
    """The rules text of the cards `card` names, for the calling seat."""
    raise NotImplementedError("M3: rules text on request is not built yet")
