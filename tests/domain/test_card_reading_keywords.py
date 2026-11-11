"""The card reader's reading of haste, vigilance and flash, and of evasion and reach."""

import pytest

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


# @spec READ-044
def test_allies_you_control_have_a_keyword_is_a_grant_limited_to_ally() -> None:
    card = a_card(
        "Ally Captain", "Allies you control have vigilance.", "Creature — Human Soldier Ally"
    )
    assert face_reading(card).vigilance == KeywordReading(grant=KeywordGrant(subtype="Ally"))


# @spec READ-044
def test_elves_you_control_have_a_keyword_is_a_grant_limited_to_elf() -> None:
    card = a_card("Elf Chieftain", "Elves you control have haste.", "Creature — Elf")
    assert face_reading(card).haste == KeywordReading(grant=KeywordGrant(subtype="Elf"))


# @spec READ-044
def test_zombies_you_control_have_a_keyword_is_a_grant_limited_to_zombie() -> None:
    card = a_card("Zombie Lord", "Zombies you control have haste.", "Creature — Zombie")
    assert face_reading(card).haste == KeywordReading(grant=KeywordGrant(subtype="Zombie"))


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
def test_a_keyword_under_a_condition_that_speaks_of_this_turn_is_its_own_with_the_condition() -> (
    None
):
    card = a_card(
        "Spell-Minded Creature",
        "As long as you've cast a noncreature spell this turn, this creature has vigilance.",
        "Creature — Human Monk",
    )
    assert face_reading(card).vigilance == KeywordReading(
        own=True, assumptions=(ASSUMES_CONDITION_MET,)
    )


# @spec READ-038
def test_a_keyword_gained_this_turn_is_not_a_grant() -> None:
    card = a_card(
        "Rally Spell", "Creatures you control get +1/+0 and gain haste this turn.", "Sorcery"
    )
    assert face_reading(card).haste == NO_KEYWORD


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


# ------------------------------------------------------------------ evasion and reach

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M1: not implemented yet")


# @spec READ-055
@NOT_BUILT
def test_flying_on_a_line_of_its_own_is_the_cards_own() -> None:
    wind_drake = a_card("Wind Drake", "Flying", "Creature — Drake")
    assert face_reading(wind_drake).flying == KeywordReading(own=True)


# @spec READ-055
@NOT_BUILT
def test_flying_in_a_comma_separated_keyword_line_is_the_cards_own() -> None:
    serra_angel = a_card("Serra Angel", "Flying, vigilance", "Creature — Angel")
    assert face_reading(serra_angel).flying == KeywordReading(own=True)


# @spec READ-055
@NOT_BUILT
def test_reach_followed_by_reminder_text_is_the_cards_own() -> None:
    giant_spider = a_card(
        "Giant Spider",
        "Reach (This creature can block creatures with flying.)",
        "Creature — Spider",
    )
    assert face_reading(giant_spider).reach == KeywordReading(own=True)


# @spec READ-055
@NOT_BUILT
def test_horsemanship_followed_by_reminder_text_is_the_cards_own() -> None:
    shu_cavalry = a_card(
        "Shu Cavalry",
        "Horsemanship (This creature can't be blocked except by creatures with horsemanship.)",
        "Creature — Human Soldier",
    )
    reading = face_reading(shu_cavalry)
    assert (reading.horsemanship, reading.cant_be_blocked) == (KeywordReading(own=True), NO_KEYWORD)


# @spec READ-056
@NOT_BUILT
def test_creatures_you_control_have_flying_is_a_grant_that_includes_the_card() -> None:
    levitation = a_card("Levitation", "Creatures you control have flying.", "Enchantment")
    assert face_reading(levitation).flying == KeywordReading(grant=KeywordGrant())


# @spec READ-056
@NOT_BUILT
def test_other_subtype_creatures_get_and_have_reach_is_a_grant_limited_to_the_subtype() -> None:
    card = a_card(
        "Spider Matriarch",
        "Other Spider creatures you control get +1/+1 and have reach.",
        "Creature — Spider",
    )
    assert face_reading(card).reach == KeywordReading(
        grant=KeywordGrant(includes_self=False, subtype="Spider")
    )


# @spec READ-057
@NOT_BUILT
def test_spirits_you_control_have_flying_is_a_grant_limited_to_spirit() -> None:
    card = a_card("Spirit Lord", "Spirits you control have flying.", "Creature — Spirit")
    assert face_reading(card).flying == KeywordReading(grant=KeywordGrant(subtype="Spirit"))


# @spec READ-058
@NOT_BUILT
def test_this_creature_can_t_be_blocked_is_the_cards_own() -> None:
    phantom_warrior = a_card(
        "Phantom Warrior", "This creature can't be blocked.", "Creature — Illusion Warrior"
    )
    assert face_reading(phantom_warrior).cant_be_blocked == KeywordReading(own=True)


# @spec READ-058
@NOT_BUILT
def test_a_card_that_says_by_name_it_can_t_be_blocked_has_it_as_its_own() -> None:
    card = a_card(
        "Invisible Stalker",
        "Hexproof\nInvisible Stalker can't be blocked.",
        "Creature — Human Rogue",
    )
    assert face_reading(card).cant_be_blocked == KeywordReading(own=True)


# @spec READ-059
@NOT_BUILT
def test_other_rogues_you_control_can_t_be_blocked_is_a_grant_limited_to_rogue() -> None:
    card = a_card(
        "Rogue Captain", "Other Rogues you control can't be blocked.", "Creature — Human Rogue"
    )
    assert face_reading(card).cant_be_blocked == KeywordReading(
        grant=KeywordGrant(includes_self=False, subtype="Rogue")
    )


# @spec READ-059
@NOT_BUILT
def test_creatures_you_control_can_t_be_blocked_is_a_grant_that_includes_the_card() -> None:
    card = a_card("Unseen Host", "Creatures you control can't be blocked.", "Enchantment")
    assert face_reading(card).cant_be_blocked == KeywordReading(grant=KeywordGrant())


# @spec READ-060
@pytest.mark.parametrize(
    "qualification",
    ["except by creatures with flying", "by Walls", "by more than one creature"],
)
def test_can_t_be_blocked_with_a_qualification_of_what_may_block_is_not_read(
    qualification: str,
) -> None:
    card = a_card(
        "Qualified Sneak", f"This creature can't be blocked {qualification}.", "Creature — Rogue"
    )
    assert face_reading(card).cant_be_blocked == NO_KEYWORD


# @spec READ-061
@pytest.mark.parametrize(
    ("text", "keyword"),
    [
        ("Creatures you control gain flying until end of turn.", "flying"),
        ("Target creature can't be blocked this turn.", "cant_be_blocked"),
        ("{2}{U}: This creature gains flying until end of turn.", "flying"),
        ("{G}: This creature gains reach.", "reach"),
        ("Whenever this creature attacks, it can't be blocked this turn.", "cant_be_blocked"),
        ("Whenever this creature attacks, it gains flying.", "flying"),
    ],
    ids=[
        "a spell until end of turn",
        "a spell this turn",
        "an activated ability until end of turn",
        "an activated ability with no duration",
        "a triggered ability this turn",
        "a triggered ability with no duration",
    ],
)
def test_evasion_or_reach_for_a_limited_time_or_from_an_ability_is_not_read(
    text: str, keyword: str
) -> None:
    card = a_card("Fleeting Wings", text, "Creature — Bird")
    assert getattr(face_reading(card), keyword) == NO_KEYWORD


# @spec READ-062
@pytest.mark.parametrize(
    ("text", "keyword"),
    [
        ("Equipped creature has flying.\nEquip {2}", "flying"),
        ("Enchant creature\nEnchanted creature gets +1/+1 and has reach.", "reach"),
        ("Enchant creature\nEnchanted creature can't be blocked.", "cant_be_blocked"),
    ],
    ids=["equipment", "an aura's keyword", "an aura's can't be blocked"],
)
def test_evasion_or_reach_conferred_through_attachment_is_not_read(text: str, keyword: str) -> None:
    card = a_card("Attached Gift", text, "Artifact — Equipment")
    assert getattr(face_reading(card), keyword) == NO_KEYWORD


# @spec READ-063
@NOT_BUILT
def test_flying_under_a_condition_before_it_is_the_cards_own_with_the_condition_assumed() -> None:
    card = a_card(
        "Island Skimmer",
        "As long as you control an Island, this creature has flying.",
        "Creature — Bird",
    )
    assert face_reading(card).flying == KeywordReading(
        own=True, assumptions=(ASSUMES_CONDITION_MET,)
    )


# @spec READ-063
@NOT_BUILT
def test_can_t_be_blocked_under_a_condition_after_it_is_the_cards_own_with_it_assumed() -> None:
    card = a_card(
        "Tidal Lurker",
        "This creature can't be blocked as long as defending player controls an Island.",
        "Creature — Fish",
    )
    assert face_reading(card).cant_be_blocked == KeywordReading(
        own=True, assumptions=(ASSUMES_CONDITION_MET,)
    )


# @spec READ-063
@NOT_BUILT
def test_a_grant_of_horsemanship_under_an_if_condition_is_a_grant_with_it_assumed() -> None:
    card = a_card(
        "Cavalry Banner",
        "If you control a commander, creatures you control have horsemanship.",
        "Artifact",
    )
    assert face_reading(card).horsemanship == KeywordReading(
        grant=KeywordGrant(), assumptions=(ASSUMES_CONDITION_MET,)
    )
