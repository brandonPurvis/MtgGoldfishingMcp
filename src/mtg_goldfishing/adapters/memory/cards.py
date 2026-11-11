"""The card ports in memory: a card cache, and a card catalog over a fixed set of cards."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from mtg_goldfishing.application.ports import CardCache, CardCatalog
from mtg_goldfishing.domain.cards import (
    Card,
    CardLookup,
    LookupStatus,
    resolve_name,
    same_name,
)


def _key(name: str) -> str:
    return name.strip().casefold()


# @spec CARD-006, CARD-007, CARD-017, CARD-021, CARD-022, CARD-024
class InMemoryCardCache(CardCache):
    """A card cache in a dictionary: one entry per card, keyed by its full name."""

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    def get(self, name: str) -> Card | None:
        """The cached card the name resolves to by the name-matching rule, if any."""
        return resolve_name(name, self._cards.values())

    def put(self, card: Card) -> None:
        self._cards[_key(card.name)] = card


# @spec CARD-006, CARD-007, CARD-021, CARD-022, APP-013
class InMemoryCardCatalog(CardCatalog):
    """A card catalog over a fixed set of cards, where some names can be made unavailable."""

    def __init__(self, cards: Iterable[Card], unavailable: Iterable[str] = ()) -> None:
        self._cards = InMemoryCardCache()
        for card in cards:
            self._cards.put(card)
        self._unavailable = tuple(unavailable)

    def look_up(self, names: Iterable[str], *, refresh: bool = False) -> Mapping[str, CardLookup]:
        return {name: self._look_up_one(name) for name in names}

    def _look_up_one(self, name: str) -> CardLookup:
        if any(same_name(name, unavailable) for unavailable in self._unavailable):
            return CardLookup(LookupStatus.UNAVAILABLE)
        card = self._cards.get(name)
        if card is None:
            return CardLookup(LookupStatus.NOT_FOUND)
        return CardLookup(LookupStatus.FOUND, card)
