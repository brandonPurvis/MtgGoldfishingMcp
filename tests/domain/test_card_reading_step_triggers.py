"""The card reader's reading of step triggers."""

from dataclasses import fields

import pytest

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.reading.reader import read_card
from mtg_goldfishing.domain.steps import Step
from tests.support.cards import a_card


def step_triggers_of(card: Card) -> tuple[Step, ...]:
    """The steps a face's step triggers belong to, in the order read."""
    return tuple(trigger.step for trigger in read_card(card).faces[0].step_triggers)


def whose_of(card: Card) -> list[tuple[str, str]]:
    """Each step trigger read from a face, as its step and whose turns it happens on."""
    triggers = read_card(card).faces[0].step_triggers
    return [(trigger.step.value, trigger.whose.value) for trigger in triggers]


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
    ("text", "step"),
    [
        ("At the beginning of each opponent's upkeep, that player loses 1 life.", "upkeep"),
        ("At the beginning of each opponent's draw step, that player draws a card.", "draw"),
        ("At the beginning of each opponent's end step, draw a card.", "end"),
    ],
)
def test_a_phrase_that_names_only_opponents_is_a_trigger_on_opponents_turns(
    text: str, step: str
) -> None:
    assert whose_of(a_card("Opponent Card", text)) == [(step, "opponents")]


# @spec READ-052
@pytest.mark.parametrize(
    "text",
    [
        "At the beginning of combat on each opponent's turn, untap target creature.",
        "At the beginning of each other player's upkeep, that player loses 1 life.",
    ],
)
def test_any_other_phrase_naming_opponents_or_other_players_is_no_trigger(text: str) -> None:
    assert step_triggers_of(a_card("Other Player Card", text)) == ()


# @spec READ-035
def test_several_triggers_in_one_step_of_the_same_whose_are_read_once() -> None:
    card = a_card(
        "Twice at Upkeep",
        "At the beginning of your upkeep, draw a card.\n"
        "At the beginning of your upkeep, you lose 1 life.",
    )
    assert whose_of(card) == [("upkeep", "controller")]


# @spec READ-035
def test_triggers_in_one_step_that_differ_in_whose_are_read_separately() -> None:
    card = a_card(
        "Upkeep Both Ways",
        "At the beginning of your upkeep, draw a card.\n"
        "At the beginning of each opponent's upkeep, that player loses 1 life.",
    )
    assert sorted(whose_of(card)) == [("upkeep", "controller"), ("upkeep", "opponents")]


# @spec READ-046, READ-047
@pytest.mark.parametrize(
    ("text", "step"),
    [
        ("At the beginning of your upkeep, draw a card.", "upkeep"),
        ("At the beginning of your draw step, draw a card.", "draw"),
        ("At the beginning of your precombat main phase, add {G}.", "main1"),
        ("At the beginning of your first main phase, add {G}.", "main1"),
        ("At the beginning of combat on your turn, untap target creature.", "begin_combat"),
        ("At the beginning of your postcombat main phase, add {R}.", "main2"),
        ("At the beginning of your second main phase, add {R}.", "main2"),
        ("At the beginning of your end step, draw a card.", "end"),
    ],
)
def test_a_phrase_naming_the_controllers_own_step_is_a_trigger_on_its_turn(
    text: str, step: str
) -> None:
    assert whose_of(a_card("Own Turn Card", text)) == [(step, "controller")]


# @spec READ-046, READ-048
@pytest.mark.parametrize(
    ("text", "step"),
    [
        ("At the beginning of each upkeep, each player loses 1 life.", "upkeep"),
        ("At the beginning of each player's upkeep, that player draws a card.", "upkeep"),
        ("At the beginning of each player's draw step, that player draws a card.", "draw"),
        ("At the beginning of each combat, untap target creature.", "begin_combat"),
        ("At the beginning of each end step, draw a card.", "end"),
        ("At the beginning of each player's end step, that player draws a card.", "end"),
        ("At the beginning of the end step, sacrifice this creature.", "end"),
    ],
)
def test_a_phrase_naming_every_turn_is_a_trigger_on_each_turn(text: str, step: str) -> None:
    assert whose_of(a_card("Each Turn Card", text)) == [(step, "each")]


# @spec READ-053, READ-050
@pytest.mark.parametrize(
    ("text", "step"),
    [
        ("Create a 1/1 token. Exile it at the beginning of the next end step.", "end"),
        ("Return it to the battlefield at the beginning of the next upkeep.", "upkeep"),
    ],
)
def test_a_delayed_phrase_naming_the_next_step_is_a_trigger_on_each_turn(
    text: str, step: str
) -> None:
    assert whose_of(a_card("Delayed Card", text)) == [(step, "each")]


# @spec READ-054, READ-050
@pytest.mark.parametrize(
    ("text", "step"),
    [
        ("Return it to your hand at the beginning of your next upkeep.", "upkeep"),
        ("Sacrifice it at the beginning of your next end step.", "end"),
    ],
)
def test_a_delayed_phrase_naming_your_next_step_is_a_trigger_on_the_controllers_turn(
    text: str, step: str
) -> None:
    assert whose_of(a_card("Delayed Card", text)) == [(step, "controller")]


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


# @spec READ-049
def test_a_step_trigger_reading_carries_no_assumptions() -> None:
    card = a_card(
        "Hedged Upkeep Card",
        "At the beginning of your upkeep, if you control a Forest, draw a card.",
    )
    [trigger] = read_card(card).faces[0].step_triggers
    assert "assumptions" not in {field.name for field in fields(trigger)}
