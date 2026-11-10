"""Builders for cards and faces, for arranging tests in the glossary's words."""

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.mana import ManaString


def a_face(
    name: str,
    text: str = "",
    type_line: str = "Artifact",
    *,
    mana_cost: str = "",
) -> Face:
    return Face(
        name=name,
        mana_cost=ManaString.parse(mana_cost),
        type_line=type_line,
        oracle_text=text,
    )


def a_card(
    name: str,
    text: str = "",
    type_line: str = "Artifact",
    *,
    mana_cost: str = "",
    produced_colors: tuple[str, ...] = (),
    keywords: tuple[str, ...] = (),
) -> Card:
    """A single-faced card with the given Oracle text and type line."""
    return Card(
        name=name,
        faces=(a_face(name, text, type_line, mana_cost=mana_cost),),
        produced_colors=produced_colors,
        keywords=keywords,
    )


def a_card_with_faces(
    *faces: Face,
    layout: str = "modal_dfc",
    produced_colors: tuple[str, ...] = (),
) -> Card:
    """A card with several faces, named after them as Scryfall names it: `Front // Back`."""
    return Card(
        name=" // ".join(face.name for face in faces),
        faces=faces,
        layout=layout,
        produced_colors=produced_colors,
    )
