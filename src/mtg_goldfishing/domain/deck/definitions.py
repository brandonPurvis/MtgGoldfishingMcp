"""Card definitions: reading them, applying them to card data, and the readings they imply."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace

from mtg_goldfishing.domain.cards import Card, CardSource, Face
from mtg_goldfishing.domain.deck.model import CardDefinition
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.mana import COLORS, ManaString
from mtg_goldfishing.domain.reading.model import (
    CardReading,
    Choice,
    EntersTappedReading,
    FaceReading,
    Fixed,
    ManaAbility,
)
from mtg_goldfishing.domain.reading.reader import read_card

_TEXT_FIELDS = ("face", "type_line", "oracle_text", "power", "toughness")
_FIELDS = frozenset(
    {
        "name",
        "mana_cost",
        "color_identity",
        "keywords",
        "produces",
        "enters_tapped",
        *_TEXT_FIELDS,
    }
)
_OWN_KEYWORDS = ("haste", "vigilance", "flash", "flying", "horsemanship", "reach")


def _malformed(field: str) -> Error:
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject=f"definition.{field}")


def _strings(value: object, field: str) -> tuple[str, ...] | Error:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return _malformed(field)


def _producible(text: str) -> ManaString | Error:
    mana = ManaString.read(text)
    if mana is None or not mana or not mana.can_be_produced():
        return Error(ErrorKind.UNPARSEABLE_MANA, subject=text)
    return mana


# @spec APP-028
def read_definition(data: object) -> CardDefinition | Error:
    """Read a card definition as received; a malformed one is an error."""
    if not isinstance(data, Mapping):
        return _malformed("name")
    unknown = sorted(str(key) for key in data if key not in _FIELDS)
    if unknown:
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="definition", names=tuple(unknown))
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return _malformed("name")
    texts: dict[str, str | None] = {}
    for field in _TEXT_FIELDS:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return _malformed(field)
        texts[field] = value
    mana_cost = None
    if data.get("mana_cost") is not None:
        text = data["mana_cost"]
        mana_cost = ManaString.read(text) if isinstance(text, str) else None
        if mana_cost is None:
            return Error(ErrorKind.UNPARSEABLE_MANA, subject=str(text))
    color_identity = None
    if data.get("color_identity") is not None:
        colors = _strings(data["color_identity"], "color_identity")
        if isinstance(colors, Error):
            return colors
        color_identity = tuple(color.strip().upper() for color in colors)
        if not set(color_identity) <= set(COLORS):
            return _malformed("color_identity")
    keywords = None
    if data.get("keywords") is not None:
        found = _strings(data["keywords"], "keywords")
        if isinstance(found, Error):
            return found
        keywords = found
    produces = None
    if data.get("produces") is not None:
        options = _strings(data["produces"], "produces")
        if isinstance(options, Error):
            return options
        read = [_producible(option) for option in options]
        for option in read:
            if isinstance(option, Error):
                return option
        produces = tuple(option for option in read if isinstance(option, ManaString))
        if not produces:
            return _malformed("produces")
    enters_tapped = data.get("enters_tapped")
    if enters_tapped is not None and not isinstance(enters_tapped, bool):
        return _malformed("enters_tapped")
    return CardDefinition(
        name=name.strip(),
        face=texts["face"],
        mana_cost=mana_cost,
        type_line=texts["type_line"],
        oracle_text=texts["oracle_text"],
        power=texts["power"],
        toughness=texts["toughness"],
        color_identity=color_identity,
        keywords=keywords,
        produces=produces,
        enters_tapped=enters_tapped,
    )


def _defined_face(card: Card, definition: CardDefinition) -> int | None:
    if definition.face is None:
        return 0
    return card.face_named(definition.face)


def _changed_face(face: Face, definition: CardDefinition) -> Face:
    changes: dict[str, object] = {}
    for field in ("mana_cost", "type_line", "oracle_text", "power", "toughness"):
        value = getattr(definition, field)
        if value is not None:
            changes[field] = value
    return replace(face, **changes)  # type: ignore[arg-type]


# @spec DECK-009, DECK-011, DECK-013
def apply_definition(card: Card | None, definition: CardDefinition) -> Card | Error:
    """Card data with each field the definition gives in place of the fetched value.

    With no fetched card, the definition alone makes the card, and needs a type line.
    """
    if card is None:
        if definition.type_line is None:
            return Error(ErrorKind.DEFINITION_NEEDS_TYPE_LINE, subject=definition.name)
        face = _changed_face(Face(definition.name), definition)
        return Card(
            definition.name,
            (face,),
            color_identity=definition.color_identity or (),
            keywords=definition.keywords or (),
            source=CardSource.DEFINITION,
        )
    index = _defined_face(card, definition)
    if index is None:
        return _malformed("face")
    faces = tuple(
        _changed_face(face, definition) if i == index else face for i, face in enumerate(card.faces)
    )
    return replace(
        card,
        faces=faces,
        color_identity=card.color_identity
        if definition.color_identity is None
        else definition.color_identity,
        keywords=card.keywords if definition.keywords is None else definition.keywords,
        source=CardSource.SCRYFALL_AND_DEFINITION,
    )


def _defined_reading(face: FaceReading, definition: CardDefinition) -> FaceReading:
    changes: dict[str, object] = {}
    if definition.produces is not None:
        produces = (
            Fixed(definition.produces[0])
            if len(definition.produces) == 1
            else Choice(definition.produces)
        )
        changes["mana_abilities"] = (ManaAbility(produces),)
        changes["unread_mana_abilities"] = ()
    if definition.enters_tapped is not None:
        changes["enters_tapped"] = EntersTappedReading(tapped=definition.enters_tapped)
    listed = {keyword.strip().casefold() for keyword in definition.keywords or ()}
    for keyword in _OWN_KEYWORDS:
        if keyword in listed:
            changes[keyword] = replace(getattr(face, keyword), own=True)
    return replace(face, **changes)  # type: ignore[arg-type]


# @spec DECK-014, DECK-015, DECK-016, DECK-017, DECK-040
def definition_reading(card: Card, definition: CardDefinition) -> CardReading:
    """The readings of a defined card: read from its data, then the definition's overrides.

    `produces` replaces the defined face's mana reading with a tap for that mana (a list is
    a choice), `enters_tapped` replaces its enters-tapped reading, and haste, vigilance,
    flash, flying, horsemanship or reach among the keywords become its own keywords.
    """
    return definitions_reading(card, (definition,))


# @spec DECK-014, DECK-015, DECK-016, DECK-017, DECK-040
def definitions_reading(card: Card, definitions: Iterable[CardDefinition]) -> CardReading:
    """The readings of a card with several definitions, each describing one of its faces."""
    faces = list(read_card(card).faces)
    for definition in definitions:
        index = _defined_face(card, definition) or 0
        if index < len(faces):
            faces[index] = _defined_reading(faces[index], definition)
    return CardReading(tuple(faces))
