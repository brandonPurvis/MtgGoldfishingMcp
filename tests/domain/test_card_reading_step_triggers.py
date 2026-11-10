"""The card reader's reading of step triggers."""

import pytest

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.reading.reader import read_card
from mtg_goldfishing.domain.steps import Step
from tests.support.cards import a_card


def step_triggers_of(card: Card) -> tuple[Step, ...]:
    return read_card(card).faces[0].step_triggers


# @spec READ-028
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of your upkeep, you draw a card and you lose 1 life.",
        "At the beginning of each upkeep, each player loses 1 life.",
        "At the beginning of each player's upkeep, that player draws a card.",
    ],
)
def test_a_beginning_of_upkeep_phrase_that_applies_to_you_is_an_upkeep_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Upkeep Card", text, "Enchantment")) == (Step.UPKEEP,)


# @spec READ-029
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of your draw step, if this artifact is tapped, it deals 1 damage to you.",
        "At the beginning of each player's draw step, that player draws an additional card.",
    ],
)
def test_a_beginning_of_draw_step_phrase_that_applies_to_you_is_a_draw_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Draw Card", text)) == (Step.DRAW,)


# @spec READ-030
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of your precombat main phase, add {G}.",
        "At the beginning of your first main phase, remove all charge counters from this artifact.",
    ],
)
def test_a_beginning_of_first_main_phase_phrase_is_a_main1_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Main Card", text)) == (Step.MAIN1,)


# @spec READ-031
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of combat on your turn, create a 1/1 white Soldier creature token.",
        "At the beginning of each combat, untap target creature.",
    ],
)
def test_a_beginning_of_combat_phrase_is_a_begin_combat_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Combat Card", text)) == (Step.BEGIN_COMBAT,)


# @spec READ-032
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of your postcombat main phase, add {R}.",
        "At the beginning of your second main phase, add {R}.",
    ],
)
def test_a_beginning_of_second_main_phase_phrase_is_a_main2_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Main Card", text)) == (Step.MAIN2,)


# @spec READ-033
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of your end step, draw a card.",
        "At the beginning of each end step, if a creature died this turn, draw a card.",
        "At the beginning of each player's end step, that player draws a card.",
        "At the beginning of the end step, sacrifice this creature.",
        "Create a 1/1 token. Exile it at the beginning of the next end step.",
    ],
)
def test_a_beginning_of_end_step_phrase_that_applies_to_you_is_an_end_trigger(text: str) -> None:
    assert step_triggers_of(a_card("End Card", text)) == (Step.END,)


# @spec READ-034
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of each opponent's upkeep, that player loses 1 life.",
        "At the beginning of each opponent's end step, draw a card.",
    ],
)
def test_a_phrase_that_names_only_opponents_is_no_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Opponent Card", text)) == ()


# @spec READ-035
def test_several_triggers_in_one_step_are_read_once() -> None:
    card = a_card(
        "Twice at Upkeep",
        "At the beginning of your upkeep, draw a card.\n"
        "At the beginning of each upkeep, you lose 1 life.",
    )
    assert step_triggers_of(card) == (Step.UPKEEP,)


# @spec READ-035
def test_triggers_in_several_steps_are_listed_in_step_order() -> None:
    mana_vault = a_card(
        "Mana Vault",
        "This artifact doesn't untap during your untap step.\n"
        "At the beginning of your draw step, if this artifact is tapped, "
        "it deals 1 damage to you.\n"
        "At the beginning of your upkeep, you may pay {4}. If you do, untap this artifact.\n"
        "{T}: Add {C}{C}{C}.",
    )
    assert step_triggers_of(mana_vault) == (Step.UPKEEP, Step.DRAW)
