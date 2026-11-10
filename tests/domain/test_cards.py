"""The card model: cards made of faces."""

import pytest

from mtg_goldfishing.domain.cards import Card, Face


# @spec CARD-001
def test_a_single_faced_card_has_one_face_named_like_the_card() -> None:
    card = Card("Grizzly Bears", (Face("Grizzly Bears"),))

    assert [face.name for face in card.faces] == [card.name]


# @spec CARD-001
def test_a_single_faced_card_cannot_have_a_face_with_another_name() -> None:
    with pytest.raises(ValueError, match="single-faced"):
        Card("Grizzly Bears", (Face("Runeclaw Bear"),))


# @spec CARD-001
def test_a_card_cannot_have_no_faces() -> None:
    with pytest.raises(ValueError, match="no faces"):
        Card("Grizzly Bears", ())


# @spec CARD-001
def test_a_multi_faced_card_holds_each_face_under_its_full_name() -> None:
    card = Card(
        "Valki, God of Lies // Tibalt, Cosmic Impostor",
        (Face("Valki, God of Lies"), Face("Tibalt, Cosmic Impostor")),
    )

    assert [face.name for face in card.faces] == ["Valki, God of Lies", "Tibalt, Cosmic Impostor"]


# @spec CARD-002
@pytest.mark.parametrize(("power", "toughness"), [("*", "1+*"), ("0", "1"), ("-1", "*")])
def test_a_face_keeps_power_and_toughness_as_written(power: str, toughness: str) -> None:
    face = Face("Tarmogoyf", power=power, toughness=toughness)

    assert (face.power, face.toughness) == (power, toughness)


# @spec CARD-006
@pytest.mark.parametrize(
    "requested",
    [
        "Valki, God of Lies // Tibalt, Cosmic Impostor",
        "Valki, God of Lies",
        "tibalt, cosmic impostor",
        "  VALKI, GOD OF LIES  ",
    ],
)
def test_a_card_matches_its_full_name_or_a_face_name_ignoring_case_and_spaces(
    requested: str,
) -> None:
    card = Card(
        "Valki, God of Lies // Tibalt, Cosmic Impostor",
        (Face("Valki, God of Lies"), Face("Tibalt, Cosmic Impostor")),
    )

    assert card.matches(requested)


# @spec CARD-006
@pytest.mark.parametrize("requested", ["Valki", "Valki God of Lies", "Valki, God of Lie", ""])
def test_a_card_matches_no_partial_or_folded_name(requested: str) -> None:
    card = Card(
        "Valki, God of Lies // Tibalt, Cosmic Impostor",
        (Face("Valki, God of Lies"), Face("Tibalt, Cosmic Impostor")),
    )

    assert not card.matches(requested)
