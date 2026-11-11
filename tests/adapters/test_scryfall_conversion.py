"""Turning a Scryfall card object into the card model."""

from typing import Any

import pytest

from mtg_goldfishing.adapters.scryfall import card_from_scryfall, read_scryfall_card
from mtg_goldfishing.domain.cards import CardSource, Face
from mtg_goldfishing.domain.mana import ManaString
from tests.support.card_data import recorded_card, recorded_scryfall_card


def _two_faced_object(**card_level: Any) -> dict[str, Any]:
    """A Scryfall card object whose faces lack some fields the card level has."""
    return {
        "name": "Front // Back",
        "layout": "transform",
        "cmc": 3.0,
        "color_identity": ["G"],
        "keywords": [],
        "legalities": {"commander": "legal"},
        "card_faces": [
            {"name": "Front", "mana_cost": "{2}{G}", "type_line": "Creature — Wolf"},
            {"name": "Back", "type_line": "Creature — Werewolf", "oracle_text": "Trample"},
        ],
        **card_level,
    }


# @spec CARD-003
def test_a_card_with_listed_faces_gets_one_face_per_listed_face() -> None:
    valki = recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor")

    assert [face.name for face in valki.faces] == ["Valki, God of Lies", "Tibalt, Cosmic Impostor"]


# @spec CARD-003
def test_each_listed_face_takes_its_own_cost_type_text_power_and_toughness() -> None:
    delver = recorded_card("Delver of Secrets // Insectile Aberration")

    assert delver.faces[1] == Face(
        name="Insectile Aberration",
        mana_cost=ManaString(),
        type_line="Creature — Human Insect",
        oracle_text="Flying",
        power="3",
        toughness="2",
    )


# @spec CARD-003
def test_a_split_card_face_takes_its_own_mana_cost() -> None:
    fire_ice = recorded_card("Fire // Ice")

    assert [str(face.mana_cost) for face in fire_ice.faces] == ["{1}{R}", "{1}{U}"]


# @spec CARD-003
def test_each_half_of_a_split_card_takes_its_own_cost_and_type_line() -> None:
    gallifrey = recorded_card("Gallifrey Falls // No More")

    assert [(face.name, str(face.mana_cost), face.type_line) for face in gallifrey.faces] == [
        ("Gallifrey Falls", "{4}{R}{R}", "Instant"),
        ("No More", "{2}{W}", "Instant"),
    ]


# @spec CARD-003
def test_a_face_lacking_power_and_toughness_takes_the_card_level_values() -> None:
    card = card_from_scryfall(_two_faced_object(power="3", toughness="3"))

    assert (card.faces[1].power, card.faces[1].toughness) == ("3", "3")


# @spec CARD-003
def test_a_face_lacking_rules_text_takes_the_card_level_rules_text() -> None:
    card = card_from_scryfall(_two_faced_object(oracle_text="Card-level text"))

    assert card.faces[0].oracle_text == "Card-level text"


# @spec CARD-003
def test_a_face_lacking_a_mana_cost_takes_the_card_level_mana_cost() -> None:
    card = card_from_scryfall(_two_faced_object(mana_cost="{G}"))

    assert str(card.faces[1].mana_cost) == "{G}"


# @spec CARD-003
def test_a_face_lacking_a_value_the_card_level_also_lacks_has_none() -> None:
    card = card_from_scryfall(_two_faced_object())

    assert (card.faces[1].mana_cost, card.faces[1].power, card.faces[0].oracle_text) == (
        ManaString(),
        None,
        "",
    )


# @spec CARD-004
def test_a_card_with_no_listed_faces_gets_one_face_from_the_card_level_values() -> None:
    tarmogoyf = recorded_card("Tarmogoyf")

    assert tarmogoyf.faces == (
        Face(
            name="Tarmogoyf",
            mana_cost=ManaString.parse("{1}{G}"),
            type_line="Creature — Lhurgoyf",
            oracle_text=recorded_scryfall_card("Tarmogoyf")["oracle_text"],
            power="*",
            toughness="1+*",
        ),
    )


# @spec CARD-004
def test_a_card_with_no_mana_cost_gets_an_empty_mana_cost() -> None:
    assert recorded_card("Forest").front.mana_cost == ManaString()


# @spec CARD-005
def test_a_card_legal_in_commander_is_commander_legal() -> None:
    assert recorded_card("Sol Ring").commander_legal


# @spec CARD-005
def test_a_card_banned_in_commander_is_not_commander_legal() -> None:
    assert not recorded_card("Black Lotus").commander_legal


# @spec CARD-005
@pytest.mark.parametrize("legality", ["not_legal", "banned", "restricted", "Legal", None])
def test_only_the_commander_legality_legal_makes_a_card_commander_legal(
    legality: str | None,
) -> None:
    legalities = {} if legality is None else {"commander": legality}

    assert not card_from_scryfall(_two_faced_object(legalities=legalities)).commander_legal


def test_a_converted_card_keeps_the_full_name_and_layout() -> None:
    card = recorded_card("Bonecrusher Giant // Stomp")

    assert (card.name, card.layout) == ("Bonecrusher Giant // Stomp", "adventure")


def test_a_converted_card_takes_its_mana_value_from_the_card_level() -> None:
    assert recorded_card("Craterhoof Behemoth").mana_value == 8


def test_a_converted_card_keeps_its_color_identity() -> None:
    assert set(recorded_card("Atraxa, Praetors' Voice").color_identity) == {"W", "U", "B", "G"}


def test_a_converted_card_keeps_its_keywords() -> None:
    assert "Flying" in recorded_card("Serra Angel").keywords


def test_a_converted_card_takes_its_produced_colors_from_the_produced_mana() -> None:
    assert set(recorded_card("City of Brass").produced_colors) == {"W", "U", "B", "R", "G"}


def test_a_card_that_makes_no_mana_produces_no_colors() -> None:
    assert recorded_card("Lightning Bolt").produced_colors == ()


def test_a_converted_card_comes_from_scryfall() -> None:
    assert recorded_card("Sol Ring").source is CardSource.SCRYFALL


@pytest.mark.parametrize(
    "broken",
    [
        {"layout": "normal"},
        {"name": "Odd Card", "mana_cost": "{Q}", "legalities": {}},
        {"name": "Odd Card", "color_identity": ["P"], "legalities": {}},
        {"name": "Odd Card", "cmc": "three", "legalities": {}},
    ],
)
def test_an_object_the_card_model_cannot_hold_is_read_as_no_card(broken: dict[str, Any]) -> None:
    assert read_scryfall_card(broken) is None
