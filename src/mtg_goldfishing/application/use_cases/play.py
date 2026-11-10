"""`play`: play a land or cast a spell, from any zone or from outside the game."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.ports import CardCatalog
from mtg_goldfishing.application.use_cases.handling import Ports, change_game, overridable
from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Result
from mtg_goldfishing.domain.play import playing

TOOL = "play"


# @spec APP-022
def play(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """Play a card. A card from outside the game has its card data resolved first."""

    def operate(game: Game, deck: LoadedDeck, override: str | None) -> Result:
        card = arguments.get("card")
        from_zone = arguments.get("from")
        outside = _card_data(ports.catalog, card) if playing.comes_from_outside(from_zone) else None
        return playing.play(
            game,
            deck,
            card=card,
            from_zone=from_zone,
            to=arguments.get("to"),
            delta=arguments.get("delta"),
            choices=arguments.get("choices"),
            pay=arguments.get("pay"),
            expect=arguments.get("expect"),
            reason=arguments.get("reason"),
            override=override,
            outside=outside,
        )

    return change_game(ports, TOOL, arguments, overridable(arguments, operate))


def _card_data(catalog: CardCatalog, card: object) -> Card | None:
    """The catalog's card data for the name, or None when there is none to be had."""
    if not isinstance(card, str) or not card.strip():
        return None
    name = card.strip()
    lookup = catalog.look_up([name]).get(name)
    return None if lookup is None else lookup.card
