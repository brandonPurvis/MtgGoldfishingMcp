"""The ports: interfaces the application reaches the outside world through.

Ports speak in domain types. Adapters implement them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Protocol

from mtg_goldfishing.domain.cards import Card, CardLookup


class CardCatalog(Protocol):
    """Supplies card data by exact name."""

    def look_up(self, names: Iterable[str], *, refresh: bool = False) -> Mapping[str, CardLookup]:
        """For each requested name, as given: the card, not found, or unavailable."""
        ...


class CardCache(Protocol):
    """Keeps fetched card data so no card is fetched twice."""

    def get(self, name: str) -> Card | None:
        """The cached card whose full name or a face name matches, ignoring case."""
        ...

    def put(self, card: Card) -> None:
        """Store a card, replacing any cached card with the same full name."""
        ...


class IdSource(Protocol):
    """Supplies what must be random."""

    def new_game_id(self) -> str:
        """Ten random characters for a game id."""
        ...

    def new_seed(self) -> int: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
