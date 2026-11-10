"""The card reader as a whole: readings per face, assumptions, and the report on a set of cards."""

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import (
    ASSUMES_UNTAPPED_PREFIX,
    IGNORES_ACTIVATION_CONDITION,
    CardReading,
    EntersTappedReading,
    EntersTappedReport,
    Fixed,
    KeywordGrant,
    KeywordReading,
    KeywordReport,
    ManaAbility,
    ReadAbility,
    UnreadAbility,
)
from mtg_goldfishing.domain.reading.reader import read_card, read_face, report
from mtg_goldfishing.domain.steps import Step
from tests.support.cards import a_card, a_card_with_faces, a_face


def reported(*cards: Card) -> list[tuple[Card, CardReading]]:
    return [(card, read_card(card)) for card in cards]


BALA_GED_RECOVERY = a_face(
    "Bala Ged Recovery", "Return target card from your graveyard to your hand.", "Sorcery"
)
LLANOWAR_ELVES = a_card("Llanowar Elves", "{T}: Add {G}.", "Creature — Elf Druid")
TEMPLE_OF_THE_FALSE_GOD = a_card(
    "Temple of the False God",
    "{T}: Add {C}{C}. Activate only if you control five or more lands.",
    "Land",
)
PENTAD_PRISM = a_card(
    "Pentad Prism",
    "Remove a charge counter from this artifact: Add one mana of any color.",
    produced_colors=("W", "U", "B", "R", "G"),
)
PHYREXIAN_ARENA = a_card(
    "Phyrexian Arena",
    "At the beginning of your upkeep, you draw a card and you lose 1 life.",
    "Enchantment",
)
GOBLIN_GUIDE = a_card("Goblin Guide", "Haste", "Creature — Goblin Scout")
FIRES_OF_YAVIMAYA = a_card("Fires of Yavimaya", "Creatures you control have haste.", "Enchantment")
SERRA_ANGEL = a_card("Serra Angel", "Flying, vigilance", "Creature — Angel")
TEMPLE_OF_PLENTY = a_card(
    "Temple of Plenty", "This land enters tapped.\n{T}: Add {G} or {W}.", "Land"
)
GLACIAL_FORTRESS = a_card(
    "Glacial Fortress",
    "This land enters tapped unless you control a Plains or an Island.\n{T}: Add {W} or {U}.",
    "Land",
)


# @spec READ-001
def test_a_reading_depends_only_on_the_card() -> None:
    first = a_card("Llanowar Elves", "{T}: Add {G}.", "Creature — Elf Druid")
    second = a_card("Llanowar Elves", "{T}: Add {G}.", "Creature — Elf Druid")
    assert read_card(first) == read_card(second)


# @spec READ-001
def test_a_face_is_read_from_its_own_text_and_type_line() -> None:
    back = a_face("Bala Ged Sanctuary", "This land enters tapped.\n{T}: Add {G}.", "Land")
    card = a_card_with_faces(
        BALA_GED_RECOVERY,
        back,
    )
    assert read_face(back, card) == read_card(card).faces[1]


# @spec READ-001
def test_a_card_has_one_reading_per_face_in_face_order() -> None:
    card = a_card_with_faces(
        BALA_GED_RECOVERY,
        a_face("Bala Ged Sanctuary", "This land enters tapped.\n{T}: Add {G}.", "Land"),
    )
    front, back = read_card(card).faces
    assert (front.is_mana_source, back.is_mana_source) == (False, True)


# @spec READ-002
def test_a_reading_of_text_that_matched_known_forms_exactly_has_no_assumptions() -> None:
    reading = read_card(LLANOWAR_ELVES).faces[0]
    assumptions = [
        *(ability.assumptions for ability in reading.mana_abilities),
        reading.haste.assumptions,
        reading.vigilance.assumptions,
        reading.flash.assumptions,
        reading.enters_tapped.assumptions,
    ]
    assert assumptions == [()] * 5


# @spec READ-002
def test_a_reading_that_rests_on_a_guess_carries_its_assumption() -> None:
    (ability,) = read_card(TEMPLE_OF_THE_FALSE_GOD).faces[0].mana_abilities
    assert ability.assumptions == (IGNORES_ACTIVATION_CONDITION,)


# @spec READ-027
def test_the_report_lists_mana_abilities_read_exactly() -> None:
    result = report(reported(LLANOWAR_ELVES, TEMPLE_OF_THE_FALSE_GOD))
    assert result.read_exactly == (
        ReadAbility(
            "Llanowar Elves",
            ManaAbility(produces=Fixed(ManaString.parse("{G}")), text="{T}: Add {G}."),
        ),
    )


# @spec READ-027
def test_the_report_lists_mana_abilities_read_with_assumptions_with_each_assumption() -> None:
    result = report(reported(LLANOWAR_ELVES, TEMPLE_OF_THE_FALSE_GOD))
    assert [(read.card, read.ability.assumptions) for read in result.read_with_assumptions] == [
        ("Temple of the False God", (IGNORES_ACTIVATION_CONDITION,))
    ]


# @spec READ-027
def test_the_report_lists_unread_mana_abilities() -> None:
    result = report(reported(LLANOWAR_ELVES, PENTAD_PRISM))
    assert result.unread == (
        UnreadAbility(
            "Pentad Prism",
            "Remove a charge counter from this artifact: Add one mana of any color.",
        ),
    )


# @spec READ-027
def test_the_report_lists_cards_with_step_triggers() -> None:
    result = report(reported(LLANOWAR_ELVES, PHYREXIAN_ARENA))
    assert result.step_triggers == (("Phyrexian Arena", Step.UPKEEP),)


# @spec READ-027
def test_the_report_lists_cards_that_have_or_grant_haste_or_vigilance() -> None:
    result = report(reported(LLANOWAR_ELVES, GOBLIN_GUIDE, FIRES_OF_YAVIMAYA, SERRA_ANGEL))
    assert result.keywords == (
        KeywordReport("Goblin Guide", "haste", KeywordReading(own=True)),
        KeywordReport("Fires of Yavimaya", "haste", KeywordReading(grant=KeywordGrant())),
        KeywordReport("Serra Angel", "vigilance", KeywordReading(own=True)),
    )


# @spec READ-027
def test_the_report_lists_cards_that_enter_tapped() -> None:
    result = report(reported(LLANOWAR_ELVES, TEMPLE_OF_PLENTY, GLACIAL_FORTRESS))
    assert result.enters_tapped == (
        EntersTappedReport("Temple of Plenty", EntersTappedReading(tapped=True)),
    )


# @spec READ-027
def test_the_report_lists_cards_assumed_to_enter_untapped() -> None:
    result = report(reported(LLANOWAR_ELVES, TEMPLE_OF_PLENTY, GLACIAL_FORTRESS))
    assert result.assumed_untapped == (
        EntersTappedReport(
            "Glacial Fortress",
            EntersTappedReading(
                assumptions=(ASSUMES_UNTAPPED_PREFIX + "unless you control a Plains or an Island",)
            ),
        ),
    )


# @spec READ-027
def test_the_report_names_the_face_of_a_card_with_several_faces() -> None:
    card = a_card_with_faces(
        BALA_GED_RECOVERY,
        a_face("Bala Ged Sanctuary", "This land enters tapped.\n{T}: Add {G}.", "Land"),
    )
    result = report(reported(card))
    assert [entry.card for entry in result.enters_tapped] == ["Bala Ged Sanctuary"]
