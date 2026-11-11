"""Builders for loading decks: deck lists, card catalog answers and a store of loaded decks.

result = a_deck_list().with_cards("Lightning Bolt").load()
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from typing import Any

from mtg_goldfishing.domain.cards import Card, CardLookup, LookupStatus, resolve_name, same_name
from mtg_goldfishing.domain.deck.loading import DeckLoad, load_deck, read_deck_request
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.results import Refusal
from tests.support.card_data import recorded_cards

ATRAXA = "Atraxa, Praetors' Voice"
OMNATH = "Omnath, Locus of Mana"

# Singletons legal in Commander and within Atraxa's color identity.
STAPLES = (
    "Sol Ring",
    "Arcane Signet",
    "Command Tower",
    "Azorius Signet",
    "Gilded Lotus",
    "City of Brass",
    "Ancient Tomb",
    "Evolving Wilds",
    "Llanowar Elves",
    "Elvish Mystic",
    "Birds of Paradise",
    "Elvish Archdruid",
    "Cultivate",
    "Rampant Growth",
    "Kodama's Reach",
    "Counterspell",
    "Brainstorm",
    "Ponder",
    "Demonic Tutor",
    "Dismember",
    "Phyrexian Arena",
    "Rhystic Study",
    "Sylvan Library",
    "Craterhoof Behemoth",
    "Grizzly Bears",
    "Tarmogoyf",
)
FILLER = "Forest"
DECK_SIZE = 100


def catalog_answers(
    names: Iterable[str],
    cards: Iterable[Card],
    *,
    unavailable: Iterable[str] = (),
) -> dict[str, CardLookup]:
    """What a card catalog over `cards` answers for each name, as the use case passes it on."""
    known = tuple(cards)
    down = tuple(unavailable)
    answers: dict[str, CardLookup] = {}
    for name in names:
        card = resolve_name(name, known)
        if any(same_name(name, gone) for gone in down):
            answers[name] = CardLookup(LookupStatus.UNAVAILABLE)
        elif card is not None:
            answers[name] = CardLookup(LookupStatus.FOUND, card)
        else:
            answers[name] = CardLookup(LookupStatus.NOT_FOUND)
    return answers


class DeckStore:
    """Loaded decks by id, as a deck repository would hold them."""

    def __init__(self, *decks: LoadedDeck) -> None:
        self.decks = {deck.deck_id: deck for deck in decks}

    def get(self, deck_id: str) -> LoadedDeck | None:
        return self.decks.get(deck_id)


def no_decks(deck_id: str) -> LoadedDeck | None:
    return None


class DeckListBuilder:
    """A Commander deck list of exactly 100 cards, topped up with Forests, unless told otherwise."""

    def __init__(self) -> None:
        self._commander: object = ATRAXA
        self._commander_count = 1
        self._entries: dict[str, int] = dict.fromkeys(STAPLES, 1)
        self._size = DECK_SIZE
        self._definitions: list[dict[str, Any]] = []
        self._cards: list[Card] = recorded_cards()
        self._unavailable: list[str] = []
        self._override: str | None = None

    def with_commander(self, *names: str) -> DeckListBuilder:
        self._commander = names[0] if len(names) == 1 else list(names)
        self._commander_count = len(names)
        return self

    def with_cards(self, *names: str, count: int = 1) -> DeckListBuilder:
        for name in names:
            self._entries[name] = count
        return self

    def without(self, *names: str) -> DeckListBuilder:
        for name in names:
            del self._entries[name]
        return self

    def of_size(self, size: int) -> DeckListBuilder:
        self._size = size
        return self

    def with_definition(self, **fields: Any) -> DeckListBuilder:
        self._definitions.append(fields)
        return self

    def with_card_data(self, *cards: Card) -> DeckListBuilder:
        """Card data the catalog knows, replacing any recorded card of the same name."""
        names = {card.name for card in cards}
        self._cards = [card for card in self._cards if card.name not in names] + list(cards)
        return self

    def with_changed_card_data(self, name: str, **changes: Any) -> DeckListBuilder:
        changed = replace(next(card for card in self._cards if card.name == name), **changes)
        return self.with_card_data(changed)

    def with_unavailable(self, *names: str) -> DeckListBuilder:
        self._unavailable.extend(names)
        return self

    def with_override(self, reason: str) -> DeckListBuilder:
        self._override = reason
        return self

    def lines(self) -> list[str]:
        filler = self._size - self._commander_count - sum(self._entries.values())
        lines = [f"{count} {name}" for name, count in self._entries.items()]
        if filler > 0:
            lines.append(f"{filler} {FILLER}")
        return lines

    def text(self) -> str:
        return "\n".join(self.lines())

    def load(
        self,
        text: str | None = None,
        *,
        existing: Callable[[str], LoadedDeck | None] = no_decks,
    ) -> DeckLoad | Refusal:
        """Load the list (or `text` in its place) as the `load_deck` use case would."""
        request = read_deck_request(
            cards=self.text() if text is None else text,
            commander=self._commander,
            definitions=self._definitions or None,
            override=self._override,
        )
        if isinstance(request, Refusal):
            return request
        lookups: Mapping[str, CardLookup] = catalog_answers(
            request.names_to_look_up, self._cards, unavailable=self._unavailable
        )
        return load_deck(request, lookups, existing)

    def loaded(
        self,
        text: str | None = None,
        *,
        existing: Callable[[str], LoadedDeck | None] = no_decks,
    ) -> DeckLoad:
        result = self.load(text, existing=existing)
        assert isinstance(result, DeckLoad), result
        return result

    def refused(self, text: str | None = None) -> Refusal:
        result = self.load(text)
        assert isinstance(result, Refusal), result
        return result


def a_deck_list() -> DeckListBuilder:
    return DeckListBuilder()


OUTSIDE_OMNATH = (
    "Azorius Signet",
    "Counterspell",
    "Brainstorm",
    "Ponder",
    "Demonic Tutor",
    "Dismember",
    "Phyrexian Arena",
    "Rhystic Study",
)
"""The staples outside Omnath's color identity."""


def an_opposing_deck_list() -> DeckListBuilder:
    """A second legal deck, for an opposing seat: Omnath with the green and colorless staples."""
    return a_deck_list().with_commander(OMNATH).without(*OUTSIDE_OMNATH)
