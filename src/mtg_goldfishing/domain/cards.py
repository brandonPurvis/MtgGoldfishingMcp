"""The card model: what is known about a card before any game."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from mtg_goldfishing.domain.mana import COLORS, MANA_KINDS, ManaString

_WORD = re.compile(r"[A-Za-z]+")


def type_words(type_line: str) -> frozenset[str]:
    """The lower-cased words of a type line, for matching card types and subtypes."""
    return frozenset(word.lower() for word in _WORD.findall(type_line))


@dataclass(frozen=True)
class Face:
    """One named, castable side of a card."""

    name: str
    mana_cost: ManaString = field(default_factory=ManaString)
    type_line: str = ""
    oracle_text: str = ""
    power: str | None = None
    toughness: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a face needs a name")

    def has_type(self, word: str) -> bool:
        return word.lower() in type_words(self.type_line)

    @property
    def is_land(self) -> bool:
        return self.has_type("land")

    @property
    def is_creature(self) -> bool:
        return self.has_type("creature")

    @property
    def is_instant(self) -> bool:
        return self.has_type("instant")

    @property
    def is_sorcery(self) -> bool:
        return self.has_type("sorcery")

    @property
    def is_permanent(self) -> bool:
        return not (self.is_instant or self.is_sorcery)

    @property
    def has_mana_cost(self) -> bool:
        return bool(self.mana_cost)


class CardSource(Enum):
    """Where a card's data came from."""

    SCRYFALL = "scryfall"
    DEFINITION = "definition"
    SCRYFALL_AND_DEFINITION = "scryfall+definition"


def same_name(first: str, second: str) -> bool:
    """Card names match ignoring letter case and surrounding whitespace."""
    return first.strip().casefold() == second.strip().casefold()


# @spec CARD-001, CARD-002
@dataclass(frozen=True)
class Card:
    """A card: one or more faces and the card-level facts Scryfall reports."""

    name: str
    faces: tuple[Face, ...]
    layout: str = "normal"
    mana_value: float = 0
    color_identity: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    produced_colors: tuple[str, ...] = ()
    commander_legal: bool = True
    source: CardSource = CardSource.SCRYFALL

    def __post_init__(self) -> None:
        if not self.faces:
            raise ValueError(f"{self.name} has no faces")
        if len(self.faces) == 1 and self.faces[0].name != self.name:
            raise ValueError(f"single-faced card {self.name} has a face named {self.faces[0].name}")
        if not set(self.color_identity) <= set(COLORS):
            raise ValueError(f"not a color identity: {self.color_identity}")
        if not set(self.produced_colors) <= set(MANA_KINDS):
            raise ValueError(f"not produced colors: {self.produced_colors}")

    @property
    def front(self) -> Face:
        return self.faces[0]

    # @spec CARD-006
    def matches(self, name: str) -> bool:
        """Whether a requested name is this card's full name or one of its face names."""
        return same_name(name, self.name) or any(same_name(name, f.name) for f in self.faces)

    def face_named(self, name: str) -> int | None:
        """The index of the face a name refers to: 0 for the full name, or that face's index."""
        if same_name(name, self.name):
            return 0
        for index, face in enumerate(self.faces):
            if same_name(name, face.name):
                return index
        return None


class LookupStatus(Enum):
    """What a card catalog found for one requested name."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CardLookup:
    """The result of looking up one name.

    `card` is present when the card was found, and also when a refresh failed and the
    cached card was kept; `status` then says why the refresh did not replace it.
    """

    status: LookupStatus
    card: Card | None = None
