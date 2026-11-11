"""Card definitions: agent-supplied card data that replaces fetched data field by field."""

from __future__ import annotations

from mtg_goldfishing.domain.cards import Card, CardSource, Face
from mtg_goldfishing.domain.deck.definitions import (
    apply_definition,
    definition_reading,
    read_definition,
)
from mtg_goldfishing.domain.deck.model import CardDefinition
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import Choice, EntersTappedReading, Fixed, ManaAbility
from tests.support.library import card

M = ManaString.parse

MIND_STONE = Card(
    "Mind Stone",
    (Face("Mind Stone", M("{2}"), "Artifact", "{T}: Add {C}."),),
)


def defined(card_data: Card | None, **fields: object) -> Card:
    definition = read_definition({"name": card_data.name if card_data else "X", **fields})
    assert isinstance(definition, CardDefinition), definition
    result = apply_definition(card_data, definition)
    assert isinstance(result, Card), result
    return result


# @spec DECK-009
def test_a_definition_replaces_the_fields_it_gives_and_keeps_the_rest() -> None:
    result = defined(card("Grizzly Bears"), power="3", oracle_text="Trample")
    face = result.front
    assert (face.power, face.oracle_text, face.toughness, face.mana_cost) == (
        "3",
        "Trample",
        "2",
        M("{1}{G}"),
    )


# @spec DECK-009
def test_a_definition_over_fetched_data_marks_the_card_as_coming_from_both() -> None:
    assert defined(card("Grizzly Bears"), power="3").source is CardSource.SCRYFALL_AND_DEFINITION


# @spec DECK-009
def test_a_definition_for_an_unfound_card_makes_the_card_from_the_definition_alone() -> None:
    definition = read_definition({"name": "Homemade Elf", "type_line": "Creature — Elf"})
    assert isinstance(definition, CardDefinition)
    result = apply_definition(None, definition)
    assert isinstance(result, Card)
    assert (result.name, result.front.type_line, result.source) == (
        "Homemade Elf",
        "Creature — Elf",
        CardSource.DEFINITION,
    )


# @spec DECK-011
def test_a_definition_naming_a_face_changes_that_face() -> None:
    result = defined(card("Fire // Ice"), face="Ice", mana_cost="{U}")
    assert (result.faces[0].mana_cost, result.faces[1].mana_cost) == (M("{1}{R}"), M("{U}"))


# @spec DECK-011
def test_a_definition_naming_no_face_changes_the_first_face() -> None:
    result = defined(card("Fire // Ice"), mana_cost="{R}")
    assert (result.faces[0].mana_cost, result.faces[1].mana_cost) == (M("{R}"), M("{1}{U}"))


# @spec DECK-013
def test_a_definition_for_an_unfound_card_without_a_type_line_is_an_error() -> None:
    definition = read_definition({"name": "Mystery Card", "mana_cost": "{1}"})
    assert isinstance(definition, CardDefinition)
    result = apply_definition(None, definition)
    assert isinstance(result, Error)
    assert result.kind is ErrorKind.DEFINITION_NEEDS_TYPE_LINE


# @spec DECK-014
def test_produces_replaces_the_mana_reading_with_a_tap_for_that_mana() -> None:
    definition = read_definition({"name": "Mind Stone", "produces": "{G}"})
    assert isinstance(definition, CardDefinition)
    reading = definition_reading(MIND_STONE, definition)
    assert reading.face(0).mana_abilities == (ManaAbility(Fixed(M("{G}"))),)


# @spec DECK-014
def test_produces_given_as_a_list_is_a_choice_between_them() -> None:
    definition = read_definition({"name": "Mind Stone", "produces": ["{G}", "{U}"]})
    assert isinstance(definition, CardDefinition)
    reading = definition_reading(MIND_STONE, definition)
    assert reading.face(0).mana_abilities == (ManaAbility(Choice((M("{G}"), M("{U}")))),)


# @spec DECK-015
def test_enters_tapped_replaces_the_enters_tapped_reading() -> None:
    definition = read_definition({"name": "Mind Stone", "enters_tapped": True})
    assert isinstance(definition, CardDefinition)
    reading = definition_reading(MIND_STONE, definition)
    assert reading.face(0).enters_tapped == EntersTappedReading(tapped=True)


# @spec DECK-016
def test_haste_vigilance_and_flash_in_keywords_become_the_cards_own() -> None:
    definition = read_definition(
        {"name": "Grizzly Bears", "keywords": ["haste", "Vigilance", "Flash"]}
    )
    assert isinstance(definition, CardDefinition)
    face = definition_reading(card("Grizzly Bears"), definition).face(0)
    assert (face.haste.own, face.vigilance.own, face.flash.own) == (True, True, True)


# @spec DECK-040
def test_flying_horsemanship_and_reach_in_keywords_become_the_cards_own() -> None:
    definition = read_definition(
        {"name": "Grizzly Bears", "keywords": ["flying", "Horsemanship", "Reach"]}
    )
    assert isinstance(definition, CardDefinition)
    face = definition_reading(card("Grizzly Bears"), definition).face(0)
    assert (face.flying.own, face.horsemanship.own, face.reach.own) == (True, True, True)


# @spec DECK-017
def test_readings_are_made_from_the_defined_card_data() -> None:
    definition = read_definition({"name": "Grizzly Bears", "oracle_text": "{T}: Add {G}."})
    assert isinstance(definition, CardDefinition)
    defined_card = apply_definition(card("Grizzly Bears"), definition)
    assert isinstance(defined_card, Card)
    reading = definition_reading(defined_card, definition)
    assert reading.face(0).mana_abilities[0].produces == Fixed(M("{G}"))


def test_a_definition_with_an_unparseable_mana_cost_is_an_error() -> None:
    result = read_definition({"name": "Mind Stone", "mana_cost": "{Q}"})
    assert isinstance(result, Error)
    assert result.kind is ErrorKind.UNPARSEABLE_MANA


def test_a_definition_with_an_unknown_field_is_an_error() -> None:
    result = read_definition({"name": "Mind Stone", "flavor": "shiny"})
    assert isinstance(result, Error)
    assert result.kind is ErrorKind.MALFORMED_ARGUMENT
