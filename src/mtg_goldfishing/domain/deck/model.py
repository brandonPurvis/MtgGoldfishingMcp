"""The loaded deck: a validated deck list, its card data and readings. Never changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from mtg_goldfishing.domain.cards import Card, same_name
from mtg_goldfishing.domain.events import FailedCheck
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import CardReading


@dataclass(frozen=True)
class CardDefinition:
    """An agent-supplied description of a card that replaces fetched card data field by field."""

    name: str
    face: str | None = None
    mana_cost: ManaString | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    color_identity: tuple[str, ...] | None = None
    keywords: tuple[str, ...] | None = None
    produces: tuple[ManaString, ...] | None = None
    enters_tapped: bool | None = None


@dataclass(frozen=True)
class DeckEntry:
    name: str
    count: int


@dataclass(frozen=True)
class OverriddenChecks:
    """Deck checks that failed and were overridden, with the reason given."""

    checks: tuple[FailedCheck, ...]
    reason: str


@dataclass(frozen=True)
class DeckCard:
    """One distinct card of a loaded deck: its resolved data and readings."""

    card: Card
    reading: CardReading


@dataclass(frozen=True)
class LoadedDeck:
    deck_id: str
    commanders: tuple[str, ...]
    entries: tuple[DeckEntry, ...]
    cards: tuple[DeckCard, ...]
    definitions: tuple[CardDefinition, ...] = ()
    overrides: tuple[OverriddenChecks, ...] = field(default=())

    @cached_property
    def _by_name(self) -> dict[str, DeckCard]:
        found: dict[str, DeckCard] = {}
        for deck_card in self.cards:
            found.setdefault(deck_card.card.name.casefold(), deck_card)
            for face in deck_card.card.faces:
                found.setdefault(face.name.casefold(), deck_card)
        return found

    def card(self, name: str) -> DeckCard | None:
        """The deck's card whose full name or a face name matches, ignoring case."""
        return self._by_name.get(name.strip().casefold())

    @property
    def card_count(self) -> int:
        return len(self.commanders) + sum(entry.count for entry in self.entries)

    def is_commander(self, name: str) -> bool:
        return any(same_name(name, commander) for commander in self.commanders)
