"""The card reader's reading of haste, vigilance and flash."""

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.reading.model import (
    ASSUMES_CONDITION_MET,
    NO_KEYWORD,
    FaceReading,
    KeywordGrant,
    KeywordReading,
)
from mtg_goldfishing.domain.reading.reader import read_card
from tests.support.cards import a_card


def face_reading(card: Card) -> FaceReading:
    return read_card(card).faces[0]


# @spec READ-036
def test_a_keyword_on_a_line_of_its_own_is_the_cards_own() -> None:
    goblin_guide = a_card(
        "Goblin Guide",
        "Haste\nWhenever this creature attacks, defending player reveals the top card of their "
        "library. If it's a land card, that player puts it into their hand.",
        "Creature — Goblin Scout",
    )
    assert face_reading(goblin_guide).haste == KeywordReading(own=True)


# @spec READ-036
def test_a_keyword_in_a_comma_separated_keyword_line_is_the_cards_own() -> None:
    serra_angel = a_card("Serra Angel", "Flying, vigilance", "Creature — Angel")
    assert face_reading(serra_angel).vigilance == KeywordReading(own=True)


# @spec READ-036
def test_flash_on_a_line_of_its_own_is_the_cards_own() -> None:
    restoration_angel = a_card(
        "Restoration Angel",
        "Flash\nFlying\nWhen this creature enters, exile target non-Angel creature you control, "
        "then return that card to the battlefield under your control.",
        "Creature — Angel",
    )
    assert face_reading(restoration_angel).flash == KeywordReading(own=True)


# @spec READ-036
def test_a_keyword_mentioned_inside_an_ability_is_not_the_cards_own() -> None:
    card = a_card(
        "Haste Mention",
        "Target creature gains haste until end of turn.",
        "Instant",
    )
    assert face_reading(card).haste == NO_KEYWORD


# @spec READ-037
def test_creatures_you_control_have_a_keyword_is_a_grant_that_includes_the_card() -> None:
    fires = a_card(
        "Fires of Yavimaya",
        "Creatures you control have haste.\n"
        "Sacrifice this enchantment: Target creature gets +2/+2 until end of turn.",
        "Enchantment",
    )
    assert face_reading(fires).haste == KeywordReading(grant=KeywordGrant(includes_self=True))


# @spec READ-037
def test_other_creatures_you_control_have_a_keyword_is_a_grant_that_excludes_the_card() -> None:
    card = a_card(
        "Vigilance Lord", "Other creatures you control have vigilance.", "Creature — Human"
    )
    assert face_reading(card).vigilance == KeywordReading(grant=KeywordGrant(includes_self=False))


# @spec READ-037
def test_subtype_creatures_you_control_have_a_keyword_is_a_grant_limited_to_that_subtype() -> None:
    card = a_card("Goblin Lord", "Goblin creatures you control have haste.", "Creature — Goblin")
    assert face_reading(card).haste == KeywordReading(grant=KeywordGrant(subtype="Goblin"))


# @spec READ-037
def test_a_plural_subtype_you_control_have_a_keyword_is_a_grant_limited_to_that_subtype() -> None:
    goblin_warchief = a_card(
        "Goblin Warchief",
        "Goblin spells you cast cost {1} less to cast.\nGoblins you control have haste.",
        "Creature — Goblin Warrior",
    )
    assert face_reading(goblin_warchief).haste == KeywordReading(
        grant=KeywordGrant(subtype="Goblin")
    )


# @spec READ-037
def test_a_keyword_in_a_longer_list_of_what_creatures_get_is_a_grant() -> None:
    card = a_card(
        "Vigilance Anthem",
        "Other Soldier creatures you control get +1/+1 and have vigilance.",
        "Creature — Human Soldier",
    )
    assert face_reading(card).vigilance == KeywordReading(
        grant=KeywordGrant(includes_self=False, subtype="Soldier")
    )


# @spec READ-037
def test_all_creatures_have_a_keyword_is_a_grant_that_includes_the_card() -> None:
    concordant_crossroads = a_card(
        "Concordant Crossroads", "All creatures have haste.", "World Enchantment"
    )
    assert face_reading(concordant_crossroads).haste == KeywordReading(grant=KeywordGrant())


# @spec READ-038
def test_a_keyword_given_until_end_of_turn_is_not_a_grant() -> None:
    goblin_bushwhacker = a_card(
        "Goblin Bushwhacker",
        "Kicker {R} (You may pay an additional {R} as you cast this spell.)\n"
        "When this creature enters, if it was kicked, creatures you control get +1/+0 and gain "
        "haste until end of turn.",
        "Creature — Goblin Warrior",
    )
    assert face_reading(goblin_bushwhacker).haste == NO_KEYWORD


# @spec READ-039
def test_a_keyword_conferred_through_equipment_is_not_read() -> None:
    lightning_greaves = a_card(
        "Lightning Greaves",
        "Equipped creature has haste and shroud.\nEquip {0}",
        "Artifact — Equipment",
    )
    assert face_reading(lightning_greaves).haste == NO_KEYWORD


# @spec READ-039
def test_a_keyword_conferred_through_an_aura_is_not_read() -> None:
    card = a_card(
        "Vigilance Aura",
        "Enchant creature\nEnchanted creature gets +1/+1 and has vigilance.",
        "Enchantment — Aura",
    )
    assert face_reading(card).vigilance == NO_KEYWORD


# @spec READ-040
def test_a_keyword_the_card_has_under_a_condition_is_its_own_with_the_condition_assumed() -> None:
    bloodghast = a_card(
        "Bloodghast",
        "This creature can't block.\n"
        "This creature has haste as long as an opponent has 10 or less life.\n"
        "Landfall — Whenever a land you control enters, you may return this card from your "
        "graveyard to the battlefield.",
        "Creature — Vampire Spirit",
    )
    assert face_reading(bloodghast).haste == KeywordReading(
        own=True, assumptions=(ASSUMES_CONDITION_MET,)
    )


# @spec READ-040
def test_a_grant_under_a_condition_is_a_grant_with_the_condition_assumed() -> None:
    anger = a_card(
        "Anger",
        "Haste\nAs long as this card is in your graveyard and you control a Mountain, "
        "creatures you control have haste.",
        "Creature — Incarnation",
    )
    assert face_reading(anger).haste == KeywordReading(
        own=True, grant=KeywordGrant(), assumptions=(ASSUMES_CONDITION_MET,)
    )
