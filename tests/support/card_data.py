"""Recorded card data: real Scryfall card objects, and the cards they convert to."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from mtg_goldfishing.adapters.scryfall import card_from_scryfall
from mtg_goldfishing.domain.cards import Card

RECORDING = Path(__file__).with_name("scryfall_cards.json")


@cache
def _recording() -> tuple[dict[str, Any], ...]:
    loaded: list[dict[str, Any]] = json.loads(RECORDING.read_text(encoding="utf-8"))
    return tuple(loaded)


def recorded_scryfall_json() -> list[dict[str, Any]]:
    """The recorded Scryfall card objects, as the collection endpoint returned them."""
    return copy.deepcopy(list(_recording()))


def recorded_scryfall_card(name: str) -> dict[str, Any]:
    """The recorded Scryfall card object whose full name is `name`."""
    for card in recorded_scryfall_json():
        if card["name"] == name:
            return card
    raise KeyError(name)


def recorded_cards() -> list[Card]:
    """The recorded card data converted to the card model."""
    return [card_from_scryfall(card) for card in recorded_scryfall_json()]


def recorded_card(name: str) -> Card:
    """The recorded card whose full name is `name`."""
    return card_from_scryfall(recorded_scryfall_card(name))
