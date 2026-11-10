"""Scryfall card objects into the card model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mtg_goldfishing.domain.cards import Card, CardSource, Face
from mtg_goldfishing.domain.mana import ManaString

_FACE_FIELDS = ("name", "mana_cost", "type_line", "oracle_text", "power", "toughness")


# @spec CARD-003, CARD-004, CARD-005
def card_from_scryfall(data: Mapping[str, Any]) -> Card:
    """The card a Scryfall card object describes.

    Raises ValueError when the object is not one the card model can hold.
    """
    listed_faces = data.get("card_faces")
    faces: tuple[Face, ...]
    if listed_faces is None:
        faces = (_face(data, data),)
    elif isinstance(listed_faces, Sequence) and listed_faces:
        faces = tuple(_face(_mapping(entry), data) for entry in listed_faces)
    else:
        raise ValueError(f"card_faces is not a list of faces: {listed_faces!r}")
    legalities = _mapping(data.get("legalities", {}))
    return Card(
        name=_text(data, "name"),
        faces=faces,
        layout=_optional_text(data, "layout") or "normal",
        mana_value=_number(data, "cmc"),
        color_identity=_texts(data, "color_identity"),
        keywords=_texts(data, "keywords"),
        produced_colors=_texts(data, "produced_mana"),
        commander_legal=legalities.get("commander") == "legal",
        source=CardSource.SCRYFALL,
    )


def read_scryfall_card(data: Mapping[str, Any]) -> Card | None:
    """The card a Scryfall card object describes, or None when the card model cannot hold it."""
    try:
        return card_from_scryfall(data)
    except ValueError:
        return None


def _face(entry: Mapping[str, Any], card: Mapping[str, Any]) -> Face:
    """A face from a face entry, taking any field the entry lacks from the card level."""
    values = {key: entry[key] if key in entry else card.get(key) for key in _FACE_FIELDS}
    merged: Mapping[str, Any] = {key: value for key, value in values.items() if value is not None}
    mana_cost = ManaString.read(_optional_text(merged, "mana_cost") or "")
    if mana_cost is None:
        raise ValueError(f"not a mana cost: {merged.get('mana_cost')!r}")
    return Face(
        name=_text(merged, "name"),
        mana_cost=mana_cost,
        type_line=_optional_text(merged, "type_line") or "",
        oracle_text=_optional_text(merged, "oracle_text") or "",
        power=_optional_text(merged, "power"),
        toughness=_optional_text(merged, "toughness"),
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"not an object: {value!r}")
    return value


def _text(data: Mapping[str, Any], key: str) -> str:
    value = _optional_text(data, key)
    if value is None:
        raise ValueError(f"missing {key}")
    return value


def _optional_text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{key} is not text: {value!r}")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} is not a number: {value!r}")
    return float(value)


def _texts(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} is not a list of text: {value!r}")
    return tuple(value)
