"""The card model: cards made of faces."""

import pytest

from mtg_goldfishing.domain.cards import Card, Face, resolve_name
from tests.support.card_data import recorded_card

FIRE_ICE = Card("Fire // Ice", (Face("Fire"), Face("Ice")), layout="split")


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


# Slash separators


# @spec CARD-021
@pytest.mark.parametrize(
    "requested",
    ["Fire/Ice", "Fire / Ice", "Fire//Ice", "fire  //  ICE", "  Fire/Ice  ", "Fire /Ice"],
)
def test_a_multi_faced_card_matches_its_full_name_written_with_slash_separators(
    requested: str,
) -> None:
    assert FIRE_ICE.matches(requested)


# @spec CARD-021
def test_a_split_card_with_long_face_names_matches_them_written_with_one_slash() -> None:
    assert recorded_card("Gallifrey Falls // No More").matches("Gallifrey Falls/No More")


# @spec CARD-021
@pytest.mark.parametrize("requested", ["Fire/Ise", "Fir/Ice", "Fire/Ice Storm", "Fire/ce"])
def test_a_name_with_slash_separators_and_a_misspelled_part_matches_nothing(
    requested: str,
) -> None:
    assert not FIRE_ICE.matches(requested)


# @spec CARD-021
def test_a_name_with_slash_separators_naming_the_faces_out_of_order_matches_nothing() -> None:
    assert not FIRE_ICE.matches("Ice/Fire")


# @spec CARD-021
@pytest.mark.parametrize("requested", ["Fire///Ice", "Fire / / Ice", "/Ice", "Fire/", "Fire//"])
def test_a_name_with_slash_separators_and_an_empty_part_matches_nothing(requested: str) -> None:
    assert not FIRE_ICE.matches(requested)


# @spec CARD-021
@pytest.mark.parametrize("requested", ["Fire/Ice/Fire", "Fire/Ice/Ice"])
def test_a_name_with_slash_separators_needs_exactly_one_part_per_face(requested: str) -> None:
    assert not FIRE_ICE.matches(requested)


# @spec CARD-021
def test_a_single_faced_card_does_not_match_its_name_split_by_a_slash() -> None:
    assert not recorded_card("Sol Ring").matches("Sol/Ring")


# @spec CARD-006, CARD-022
def test_a_card_with_a_slash_in_its_own_name_matches_that_name() -> None:
    assert recorded_card("Summon: Choco/Mog").matches("summon: choco/mog")


# Resolving a name among cards


# @spec CARD-021
def test_a_name_with_slash_separators_resolves_to_the_card_whose_faces_it_names() -> None:
    cards = [recorded_card("Sol Ring"), FIRE_ICE]

    assert resolve_name("Fire/Ice", cards) == FIRE_ICE


# @spec CARD-022
@pytest.mark.parametrize("first", [True, False], ids=["listed first", "listed last"])
def test_a_name_resolves_to_the_card_it_names_as_written_before_one_whose_faces_it_names(
    first: bool,
) -> None:
    choco = recorded_card("Summon: Choco/Mog")
    two_faced = Card("Summon: Choco // Mog", (Face("Summon: Choco"), Face("Mog")))
    cards = [choco, two_faced] if first else [two_faced, choco]

    assert resolve_name("Summon: Choco/Mog", cards) == choco


# @spec CARD-006, CARD-007
def test_a_name_resolves_to_the_card_with_that_full_name_before_one_with_that_face_name() -> None:
    ice = Card("Ice", (Face("Ice"),))

    assert resolve_name("Ice", [FIRE_ICE, ice]) == ice


# @spec CARD-007
def test_a_face_name_shared_by_two_cards_resolves_to_the_card_whose_full_name_sorts_first() -> None:
    later = Card("Zebra // Ice", (Face("Zebra"), Face("Ice")))

    assert resolve_name("ice", [later, FIRE_ICE]) == FIRE_ICE


# @spec CARD-006, CARD-021
def test_a_name_no_card_matches_resolves_to_none() -> None:
    assert resolve_name("Fire/Ise", [FIRE_ICE]) is None
