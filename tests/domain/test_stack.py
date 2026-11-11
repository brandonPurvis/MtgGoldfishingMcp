"""The stack of a contested game: what goes on it and what is checked then, resolution, a
disturbed or failing item confirmed or restated, countering, and items leaving with an
eliminated seat."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import StackItemKind, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect, play
from tests.support import tables
from tests.support.acting import (
    S1,
    S2,
    S3,
    acted,
    cast,
    error_kinds,
    events_named,
    passed,
    recorded,
    stack_ids,
    zone_of,
)
from tests.support.builders import Situation, a_game
from tests.support.tables import S1_LANDS, bolt_at, three_seats, two_seats

ATRAXA = "Atraxa, Praetors' Voice"


def card_of(situation: Situation, name: str, owner: SeatNumber = S1) -> Any:
    return tables.card_of(situation, name, owner)


def top(situation: Situation) -> Any:
    return situation.game.stack[-1]


# ------------------------------------------------------------------ goldfish games


# @spec STACK-001
def test_a_goldfish_game_applies_a_play_at_once_and_keeps_its_stack_empty() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").with_hand("Grizzly Bears").build()

    cast(situation, S1, "Grizzly Bears")

    assert situation.names_in(Zone.BATTLEFIELD).count("Grizzly Bears") == 1
    assert situation.game.stack == []
    assert situation.game.window is None


# @spec STACK-001
def test_a_goldfish_game_applies_an_effect_at_once_and_opens_no_window() -> None:
    situation = a_game().build()

    recorded(situation, S1, "Ancient Tomb", {"life": -2})

    assert situation.game.seat(S1).life == 38
    assert situation.game.stack == []
    assert situation.game.window is None


# ------------------------------------------------------------------ what goes on the stack


# @spec STACK-003
def test_a_spell_goes_on_the_stack_holding_its_controller_delta_destination_and_choices() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))

    cast(
        situation,
        S1,
        "Grizzly Bears",
        to="battlefield_tapped",
        delta={"life": 2},
        choices={"notes": "a test"},
    )

    item = top(situation)
    assert (item.kind, item.controller) == (StackItemKind.SPELL, S1)
    assert item.delta == {"life": 2}
    assert item.to is not None
    assert item.to.value == "battlefield_tapped"
    assert item.choices == {"notes": "a test"}


# @spec STACK-003
def test_a_spell_on_the_stack_has_not_applied_its_delta() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))

    cast(situation, S1, "Grizzly Bears", delta={"life": 2})

    assert situation.game.seat(S1).life == 40


# @spec STACK-004
def test_a_spell_put_on_the_stack_is_paid_for_at_once() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))

    cast(situation, S1, "Grizzly Bears")

    tapped = [c.name for c in situation.game.battlefield_of(S1) if c.tapped]
    assert len(tapped) == 2
    assert "Forest" in tapped
    assert situation.game.stack


# @spec STACK-005
def test_a_commander_cast_onto_the_stack_counts_its_tax_at_once() -> None:
    situation = two_seats(lambda b: b.with_commander(ATRAXA).with_pool("{G}{W}{U}{B}"))
    atraxa = card_of(situation, ATRAXA)

    cast(situation, S1, ATRAXA)

    assert situation.game.seat(S1).commander_casts[atraxa.id] == 1
    assert top(situation).card == atraxa.id


# @spec STACK-006
def test_a_spell_on_the_stack_has_its_card_in_the_zone_stack() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))
    bears = card_of(situation, "Grizzly Bears")

    cast(situation, S1, "Grizzly Bears")

    assert zone_of(situation, bears.id) == "stack"
    assert top(situation).card == bears.id


# @spec STACK-007
def test_an_effect_goes_on_the_stack_as_an_ability_with_no_card() -> None:
    situation = two_seats()

    recorded(situation, S1, "Phyrexian Arena", {"draw": 1, "life": -1})

    item = top(situation)
    assert (item.kind, item.controller, item.card) == (StackItemKind.ABILITY, S1, None)
    assert (item.source, item.delta) == ("Phyrexian Arena", {"draw": 1, "life": -1})
    assert situation.game.seat(S1).life == 40


# @spec STACK-008
def test_an_ability_put_on_the_stack_is_paid_for_at_once() -> None:
    situation = two_seats()

    recorded(situation, S1, "an activated ability", {"draw": 1}, pay={"cost": "{1}"})

    assert sum(1 for c in situation.game.battlefield_of(S1) if c.tapped) == 1
    assert situation.game.stack


# @spec STACK-009
def test_an_immediate_effect_is_applied_at_once_and_opens_no_window() -> None:
    situation = two_seats()

    recorded(situation, S1, "a correction", {"life": -3}, immediate=True)

    assert situation.game.seat(S1).life == 37
    assert situation.game.stack == []
    assert situation.game.window is None


# @spec STACK-010
def test_an_immediate_effect_in_an_open_window_leaves_the_asking_as_it_was() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_window("stack", asking=2),
    )
    window = situation.game.window

    recorded(situation, S2, "Island", {"mana": "{U}"}, immediate=True)

    assert situation.game.window == window
    assert stack_ids(situation) == ["s1"]


# @spec STACK-011
def test_a_land_played_in_a_contested_game_puts_nothing_on_the_stack() -> None:
    situation = two_seats(lambda b: b.with_hand("Forest"))

    cast(situation, S1, "Forest")

    assert situation.game.stack == []
    assert situation.game.window is None


# @spec STACK-012
def test_stack_items_are_numbered_across_the_game_and_never_reused() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt", "Grizzly Bears"))
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))
    first = top(situation).id
    passed(situation, S2)

    cast(situation, S1, "Grizzly Bears")

    assert (first, top(situation).id) == ("s1", "s2")


# @spec STACK-013
def test_a_spell_records_its_tool_and_the_card_played_as_its_source() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))

    cast(situation, S1, "Grizzly Bears")

    assert (top(situation).tool, top(situation).source) == ("play", "Grizzly Bears")


# @spec STACK-013
def test_an_ability_records_its_tool_and_the_calls_source() -> None:
    situation = two_seats()

    recorded(situation, S1, "Sol Ring's owner's trick", {"draw": 1})

    assert (top(situation).tool, top(situation).source) == ("effect", "Sol Ring's owner's trick")


# @spec STACK-064
@pytest.mark.parametrize(
    ("delta", "kind"),
    [
        pytest.param({"teleport": ["Forest"]}, "unknown_delta_key", id="unknown key"),
        pytest.param({"draw": "two"}, "malformed_argument", id="malformed value"),
        pytest.param(
            {"look": {"n": 1, "rest": "library_top"}, "search": {}},
            "look_and_search",
            id="two reveals",
        ),
        pytest.param({"damage": {"5": 3}}, "no_such_seat", id="no such seat"),
        pytest.param({"counter": ["s9"]}, "not_on_stack", id="nothing to counter"),
    ],
)
def test_a_held_delta_with_an_error_that_does_not_depend_on_cards_is_refused_when_cast(
    delta: dict[str, object], kind: str
) -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))

    result = play(situation.game, situation.deck, S1, card="Lightning Bolt", delta=delta)

    assert error_kinds(result) == [kind]
    assert situation.game.stack == []


# @spec STACK-064
def test_a_held_delta_naming_an_eliminated_seat_is_refused_when_cast() -> None:
    builder: Any = a_game().with_battlefield(*S1_LANDS).with_hand("Lightning Bolt")
    builder = builder.and_an_opposing_seat().with_battlefield(*tables.OTHER_LANDS)
    situation = builder.and_an_opposing_seat().eliminated().build()

    result = play(situation.game, situation.deck, S1, card="Lightning Bolt", delta=bolt_at(3))

    assert error_kinds(result) == ["seat_out"]


# @spec STACK-065
def test_a_counter_entry_is_held_as_the_id_of_the_item_it_named() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_hand("Counterspell").with_window("stack", asking=2),
    )

    cast(situation, S2, "Counterspell", delta={"counter": ["Lightning Bolt"]})

    assert top(situation).delta == {"counter": ["s1"]}


# @spec STACK-066
def test_the_cards_a_held_delta_names_are_not_looked_for_when_it_is_cast() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))

    cast(
        situation,
        S1,
        "Grizzly Bears",
        delta={"counters": {"Grizzly Bears": {"+1/+1": 1}}, "tap": ["Shivan Dragon"]},
    )

    assert stack_ids(situation) == ["s1"]


# @spec PLAY-110
def test_expect_on_a_held_spell_is_compared_when_it_is_cast() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears", "Forest"))

    result = cast(situation, S1, "Grizzly Bears", expect={"untapped_lands": 3, "hand": 1})

    assert events_named(result, "ExpectationMismatched") == []
    assert stack_ids(situation) == ["s1"]


# ------------------------------------------------------------------ resolution


# @spec STACK-014, STACK-024
def test_an_item_resolves_once_every_other_seat_has_passed() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))

    passed(situation, S2)

    assert situation.game.seat(S2).life == 37
    assert situation.game.stack == []
    assert situation.game.pending == []


# @spec STACK-014
def test_an_item_waits_while_any_other_seat_has_yet_to_pass() -> None:
    situation = three_seats(lambda b: b.with_hand("Lightning Bolt"))
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))

    passed(situation, S2)

    assert stack_ids(situation) == ["s1"]
    assert situation.game.seat(S2).life == 40


# @spec STACK-015
def test_an_item_resolves_at_once_when_no_other_seat_is_left() -> None:
    builder: Any = a_game().with_battlefield(*S1_LANDS).with_hand("Grizzly Bears")
    situation = builder.and_an_opposing_seat().eliminated().build()

    result = cast(situation, S1, "Grizzly Bears")

    assert events_named(result, "ItemResolved")
    assert situation.game.stack == []
    assert "Grizzly Bears" in situation.names_in(Zone.BATTLEFIELD)


# @spec STACK-016, STACK-018
def test_a_resolving_permanent_spell_enters_before_its_delta_so_the_delta_can_change_it() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))
    bears = card_of(situation, "Grizzly Bears")
    cast(situation, S1, "Grizzly Bears", delta={"counters": {"Grizzly Bears": {"+1/+1": 1}}})

    passed(situation, S2)

    card = situation.game.instance(bears.id)
    assert (card.zone, card.controller, card.counters) == (Zone.BATTLEFIELD, S1, {"+1/+1": 1})


# @spec STACK-018
def test_a_resolving_permanent_enters_on_the_table_turn() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"))
    bears = card_of(situation, "Grizzly Bears")
    cast(situation, S1, "Grizzly Bears")

    passed(situation, S2)

    assert situation.game.instance(bears.id).entered_turn == 5


# @spec STACK-017
def test_a_stated_destination_of_a_hidden_or_owned_zone_is_the_owners() -> None:
    situation = two_seats(second=lambda b: b.with_graveyard("Lightning Bolt"))
    bolt = card_of(situation, "Lightning Bolt", S2)
    cast(situation, S1, "Lightning Bolt", from_zone="graveyard", to="exile", delta=bolt_at(2))

    passed(situation, S2)

    card = situation.game.instance(bolt.id)
    assert (card.zone, card.owner) == (Zone.EXILE, S2)


# @spec STACK-080
def test_a_spell_sent_to_the_battlefield_enters_under_its_controller_on_the_table_turn() -> None:
    situation = two_seats(second=lambda b: b.with_graveyard("Grizzly Bears"))
    bears = card_of(situation, "Grizzly Bears", S2)
    cast(
        situation,
        S1,
        "Grizzly Bears",
        from_zone="graveyard",
        to="battlefield_tapped",
        override="a reanimation spell",
    )

    passed(situation, S2)

    card = situation.game.instance(bears.id)
    assert (card.zone, card.controller, card.tapped, card.entered_turn) == (
        Zone.BATTLEFIELD,
        S1,
        True,
        5,
    )


# @spec STACK-019
def test_a_resolving_instant_goes_to_its_owners_graveyard() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    bolt = card_of(situation, "Lightning Bolt")
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))

    passed(situation, S2)

    assert zone_of(situation, bolt.id) == "graveyard"


# @spec STACK-020
def test_a_resolving_ability_applies_its_delta_and_leaves_the_stack() -> None:
    situation = two_seats()
    recorded(situation, S1, "a drain", {"life": {"2": -2, "1": 2}})

    passed(situation, S2)

    assert (situation.game.seat(S1).life, situation.game.seat(S2).life) == (42, 38)
    assert situation.game.stack == []


# @spec STACK-021, STACK-081
def test_a_resolving_delta_acts_as_its_controller_whichever_seat_passed() -> None:
    situation = two_seats(
        lambda b: b.with_library("Plains", "Swamp"), lambda b: b.with_battlefield("Forest")
    )
    recorded(situation, S1, "an ability", {"draw": 1, "life": 3, "tap": ["Forest"]})

    passed(situation, S2)

    assert situation.names_in(Zone.HAND) == ["Plains"]
    assert situation.game.seat(S1).life == 43
    assert [c.owner for c in situation.game.cards if c.name == "Forest" and c.tapped] == [S1]


# @spec STACK-022
def test_a_resolving_delta_gets_the_bookkeeping_of_a_delta_applied_at_once() -> None:
    situation = two_seats(lambda b: b.with_library("Plains", "Swamp", "Forest"))
    recorded(
        situation,
        S1,
        "a fetch",
        {"fetch": {"hand": ["Swamp"]}, "tokens": {"name": "Treasure", "types": "Artifact"}},
    )

    result = passed(situation, S2)

    assert situation.game.seat(S1).shuffles == 1
    assert [c.owner for c in situation.game.cards if c.name == "Treasure"] == [S1]
    assert events_named(result, "LibraryShuffled")


# @spec STACK-022
def test_a_resolving_delta_that_takes_a_seat_to_zero_life_eliminates_it() -> None:
    situation = two_seats(second=lambda b: b.with_life(3))
    recorded(situation, S1, "a drain", {"damage": {"2": 3}})

    result = passed(situation, S2)

    assert situation.game.seat(S2).eliminated
    assert events_named(result, "SeatEliminated")


# @spec STACK-023
def test_an_item_resolving_marks_every_item_below_it_disturbed() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}),
        lambda b: b.with_ability_on_stack("another trick", delta={"life": 1}).with_window(
            "stack", asking=2, passed=(1,)
        ),
    )

    passed(situation, S2)

    assert stack_ids(situation) == ["s1", "s2"]
    assert all(item.disturbed for item in situation.game.stack)


# @spec STACK-072
def test_a_seat_brought_to_zero_by_one_item_loses_its_items_below_before_they_resolve() -> None:
    builder: Any = a_game().with_battlefield("Forest", tapped=True)
    builder = builder.and_an_opposing_seat().with_life(3).with_battlefield("Island")
    builder = builder.with_ability_on_stack("a lifegain", delta={"life": 10})
    builder = builder.with_ability_on_stack("a drain", delta=bolt_at(2), controller=1)
    situation = builder.with_window("stack", asking=2).build()

    passed(situation, S2)

    assert situation.game.seat(S2).eliminated
    assert situation.game.stack == []
    assert situation.game.seat(S2).life <= 0


# @spec STACK-073
def test_a_commander_spell_sent_to_the_graveyard_on_resolution_goes_to_the_command_zone() -> None:
    situation = two_seats(lambda b: b.with_commander(ATRAXA).with_pool("{G}{W}{U}{B}"))
    atraxa = card_of(situation, ATRAXA)
    cast(situation, S1, ATRAXA, to="graveyard")

    result = passed(situation, S2)

    assert zone_of(situation, atraxa.id) == "command"
    assert any(event.commander_redirected for event in events_named(result, "CardMoved"))


# @spec STACK-074
def test_a_commander_spell_whose_delta_lets_it_stay_goes_where_it_was_sent() -> None:
    situation = two_seats(lambda b: b.with_commander(ATRAXA).with_pool("{G}{W}{U}{B}"))
    atraxa = card_of(situation, ATRAXA)
    cast(situation, S1, ATRAXA, to="graveyard", delta={"commander_stays": True})

    passed(situation, S2)

    assert zone_of(situation, atraxa.id) == "graveyard"


# ------------------------------------------------------------------ confirming or restating


def a_disturbed_bears(**options: Any) -> Situation:
    """S1's Grizzly Bears waits on the stack, disturbed, and S2 is asked about it."""
    return two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears", disturbed=True, **options),
        lambda b: b.with_window("stack", asking=2),
    )


def answer(situation: Situation, seat: SeatNumber = S1, **arguments: Any) -> Any:
    choice = situation.game.pending[0]
    return choose(situation.game, situation.deck, seat, choice_id=choice.choice_id, **arguments)


# @spec STACK-025
def test_a_disturbed_item_reaching_resolution_asks_its_controller_to_confirm_or_restate() -> None:
    situation = a_disturbed_bears(delta={"life": 1})

    passed(situation, S2)

    choice = situation.game.pending[0]
    assert (choice.kind, choice.seat, choice.item) == ("resolve", S1, "s1")
    assert stack_ids(situation) == ["s1"]
    assert situation.game.seat(S1).life == 40


# @spec STACK-026
def test_confirming_a_disturbed_item_resolves_it_as_held() -> None:
    situation = a_disturbed_bears(delta={"life": 1})
    bears = card_of(situation, "Grizzly Bears")
    passed(situation, S2)

    acted(situation, answer(situation))

    assert zone_of(situation, bears.id) == "battlefield"
    assert situation.game.seat(S1).life == 41
    assert situation.game.stack == []


# @spec STACK-027
def test_restating_a_disturbed_item_resolves_it_with_the_restated_delta_and_destination() -> None:
    situation = a_disturbed_bears(delta={"life": 1})
    bears = card_of(situation, "Grizzly Bears")
    passed(situation, S2)

    acted(situation, answer(situation, restate={"delta": {"life": 5}, "to": "exile"}))

    assert zone_of(situation, bears.id) == "exile"
    assert situation.game.seat(S1).life == 45


# @spec STACK-028
def test_a_restate_without_a_destination_keeps_the_held_one() -> None:
    situation = a_disturbed_bears(delta={"life": 1}, to="hand")
    bears = card_of(situation, "Grizzly Bears")
    passed(situation, S2)

    acted(situation, answer(situation, restate={"delta": {}}))

    assert zone_of(situation, bears.id) == "hand"
    assert situation.game.seat(S1).life == 40


# @spec STACK-028
def test_a_restate_without_a_delta_keeps_the_held_one() -> None:
    situation = a_disturbed_bears(delta={"life": 1})
    bears = card_of(situation, "Grizzly Bears")
    passed(situation, S2)

    acted(situation, answer(situation, restate={"to": "graveyard"}))

    assert zone_of(situation, bears.id) == "graveyard"
    assert situation.game.seat(S1).life == 41


# @spec STACK-029
def test_a_spell_restated_to_do_nothing_goes_to_its_owners_graveyard() -> None:
    situation = a_disturbed_bears(delta={"life": 1})
    bears = card_of(situation, "Grizzly Bears")
    passed(situation, S2)

    acted(situation, answer(situation, restate={"delta": {}, "to": "graveyard"}))

    assert zone_of(situation, bears.id) == "graveyard"
    assert situation.game.seat(S1).life == 40


# @spec STACK-029
def test_a_commander_restated_to_do_nothing_goes_to_the_command_zone() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack(ATRAXA, disturbed=True, commander=True),
        lambda b: b.with_window("stack", asking=2),
    )
    commander = str(situation.game.stack[0].card)
    passed(situation, S2)

    acted(situation, answer(situation, restate={"delta": {}, "to": "graveyard"}))

    assert zone_of(situation, commander) == "command"


def a_failing_bolt() -> Situation:
    """S1's Lightning Bolt holds a delta naming a card that is nowhere, and S2 is asked."""
    return two_seats(
        lambda b: b.with_spell_on_stack(
            "Lightning Bolt",
            delta={"damage": {"2": 3}, "move": {"graveyard": ["Shivan Dragon"]}},
        ),
        lambda b: b.with_window("stack", asking=2),
    )


# @spec STACK-067
def test_a_held_delta_that_cannot_be_applied_leaves_the_item_and_asks_its_controller() -> None:
    situation = a_failing_bolt()
    bolt = card_of(situation, "Lightning Bolt")

    passed(situation, S2)

    assert situation.game.seat(S2).life == 40
    assert zone_of(situation, bolt.id) == "stack"
    assert (situation.game.pending[0].kind, situation.game.pending[0].seat) == ("resolve", S1)


# @spec STACK-068
def test_the_resolve_choice_for_a_failing_delta_states_the_error() -> None:
    situation = a_failing_bolt()

    result = passed(situation, S2)

    (asked,) = events_named(result, "ResolveAsked")
    assert asked.error is not None
    assert asked.error.kind.value == "card_not_in_zone"


# @spec STACK-069
def test_an_answer_that_still_cannot_be_applied_is_an_error_and_the_choice_waits() -> None:
    situation = a_failing_bolt()
    passed(situation, S2)

    result = answer(situation)

    assert error_kinds(result) == ["card_not_in_zone"]
    assert situation.game.pending[0].kind == "resolve"
    assert stack_ids(situation) == ["s1"]


# @spec STACK-069
def test_a_restated_answer_that_cannot_be_applied_is_an_error() -> None:
    situation = a_failing_bolt()
    passed(situation, S2)

    result = answer(situation, restate={"delta": {"tap": ["Serra Angel"]}})

    assert error_kinds(result) == ["card_not_in_zone"]


# @spec STACK-075
def test_a_restate_may_hold_keys_that_ask_other_seats() -> None:
    situation = a_failing_bolt()
    passed(situation, S2)

    restate = {"delta": {"ask": [{"seats": [2], "text": "discard a card"}]}}
    acted(situation, answer(situation, restate=restate))

    choice = situation.game.pending[0]
    assert (choice.kind, choice.seat) == ("ask", S2)


# @spec STACK-082
def test_a_restated_delta_puts_nothing_on_the_stack_and_opens_no_window() -> None:
    situation = a_failing_bolt()
    passed(situation, S2)

    acted(situation, answer(situation, restate={"delta": {"damage": {"2": 3}}}))

    assert situation.game.stack == []
    assert situation.game.window is None
    assert situation.game.seat(S2).life == 37


# @spec STACK-076
def test_a_restate_giving_a_destination_for_an_ability_is_an_error() -> None:
    situation = two_seats(
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}, disturbed=True),
        lambda b: b.with_window("stack", asking=2),
    )
    passed(situation, S2)

    result = answer(situation, restate={"to": "graveyard"})

    assert error_kinds(result) == ["ability_has_no_card"]


# ------------------------------------------------------------------ countering


def bolt_and_counterspell() -> Situation:
    """S1's Lightning Bolt at S2 waits; S2 is asked and holds Counterspell."""
    return two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_hand("Counterspell").with_window("stack", asking=2),
    )


# @spec STACK-030, STACK-031
@pytest.mark.parametrize("named", ["s1", "Lightning Bolt"], ids=["by id", "by name"])
def test_a_countered_spell_leaves_the_stack_unapplied_for_its_owners_graveyard(named: str) -> None:
    situation = bolt_and_counterspell()
    bolt = card_of(situation, "Lightning Bolt")
    cast(situation, S2, "Counterspell", delta={"counter": [named]})

    passed(situation, S1)

    assert situation.game.stack == []
    assert situation.game.seat(S2).life == 40
    assert zone_of(situation, bolt.id) == "graveyard"


# @spec STACK-031
def test_a_countered_commander_goes_to_its_owners_command_zone() -> None:
    situation = two_seats(
        lambda b: b.with_commander(ATRAXA).with_pool("{G}{W}{U}{B}"),
        lambda b: b.with_hand("Counterspell"),
    )
    atraxa = card_of(situation, ATRAXA)
    cast(situation, S1, ATRAXA)
    cast(situation, S2, "Counterspell", delta={"counter": ["s1"]})

    passed(situation, S1)

    assert zone_of(situation, atraxa.id) == "command"


# @spec STACK-032, PLAY-123, PLAY-085
def test_a_countering_delta_may_move_the_countered_card_by_name() -> None:
    situation = two_seats(
        lambda b: b.with_hand("Lightning Bolt").with_spell_on_stack(
            "Lightning Bolt", delta=bolt_at(2)
        ),
        lambda b: b.with_window("stack", asking=2),
    )
    held = situation.game.stack[0].card
    recorded(
        situation,
        S2,
        "a counter that exiles",
        {"counter": ["s1"], "move": {"exile": ["Lightning Bolt"]}},
        immediate=True,
    )

    assert zone_of(situation, str(held)) == "exile"
    assert situation.names_in(Zone.HAND) == ["Lightning Bolt"]


# @spec STACK-033
def test_an_item_below_one_that_resolves_stays_on_the_stack() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}),
        lambda b: b.with_window("stack", asking=3, passed=(1,)),
    )

    passed(situation, S3)

    assert stack_ids(situation) == ["s1"]


# @spec PLAY-125
@pytest.mark.parametrize("counter", ["s1", [3], {"s1": True}], ids=["text", "number", "map"])
def test_a_counter_that_is_not_a_list_of_items_is_malformed(counter: object) -> None:
    situation = bolt_and_counterspell()

    result = play(
        situation.game, situation.deck, S2, card="Counterspell", delta={"counter": counter}
    )

    assert error_kinds(result) == ["malformed_argument"]


# @spec PLAY-078
def test_a_counter_naming_nothing_on_the_stack_is_an_error() -> None:
    situation = bolt_and_counterspell()

    result = play(
        situation.game, situation.deck, S2, card="Counterspell", delta={"counter": ["Ponder"]}
    )

    assert error_kinds(result) == ["not_on_stack"]


# @spec PLAY-090
@pytest.mark.parametrize("named", ["id", "name"])
def test_moving_a_spell_on_the_stack_without_countering_it_is_an_error(named: str) -> None:
    situation = bolt_and_counterspell()
    held = str(situation.game.stack[0].card)

    result = effect(
        situation.game,
        situation.deck,
        S2,
        source="a misplaced move",
        delta={"move": {"exile": [held if named == "id" else "Lightning Bolt"]}},
        immediate=True,
    )

    assert error_kinds(result) == ["card_on_stack"]


# @spec PLAY-130
def test_a_move_by_a_name_also_on_the_stack_takes_the_card_in_hand() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_hand("Lightning Bolt").with_window("stack", asking=2),
    )
    held = str(situation.game.stack[0].card)

    recorded(
        situation, S2, "a discard", {"move": {"graveyard": ["Lightning Bolt"]}}, immediate=True
    )

    assert zone_of(situation, held) == "stack"
    assert situation.names_in(Zone.GRAVEYARD, S2) == ["Lightning Bolt"]


# ------------------------------------------------------------------ elimination


# @spec STACK-058, STACK-059
def test_an_eliminated_seats_items_leave_the_stack_and_its_cards_leave_the_game() -> None:
    situation = two_seats(
        second=lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(1)).with_window(
            "stack", asking=1
        )
    )
    held = str(situation.game.stack[0].card)

    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))

    assert situation.game.stack == []
    assert situation.game.find(held) is None


# @spec STACK-059
def test_an_eliminated_seats_spell_of_another_seats_card_goes_to_its_owners_graveyard() -> None:
    builder: Any = a_game().with_battlefield(*S1_LANDS).with_graveyard("Lightning Bolt")
    builder = builder.and_an_opposing_seat().with_battlefield(*tables.OTHER_LANDS)
    builder = builder.and_an_opposing_seat().with_battlefield(*tables.OTHER_LANDS)
    situation = builder.build()
    bolt = card_of(situation, "Lightning Bolt")
    situation.game.active = S2
    cast(situation, S2, "Lightning Bolt", from_zone="graveyard", delta=bolt_at(3))
    assert stack_ids(situation) == ["s1"]

    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))

    assert zone_of(situation, bolt.id) == "graveyard"
    assert situation.game.stack == []


# @spec STACK-060
def test_when_the_seat_being_asked_is_eliminated_the_asking_moves_on() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
    )

    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))

    assert situation.game.window is not None
    assert situation.game.window.asking == S3


# @spec STACK-061
def test_removing_an_eliminated_seats_items_disturbs_none_of_the_rest() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}),
        lambda b: b.with_ability_on_stack("another", delta={"life": 1}).with_window(
            "stack", asking=1
        ),
    )

    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))

    assert stack_ids(situation) == ["s1", "s3"]
    assert not any(item.disturbed for item in situation.game.stack)


# @spec STACK-063
def test_an_item_whose_card_the_eliminated_seat_owns_leaves_the_stack() -> None:
    situation = three_seats(
        second=lambda b: b.with_graveyard("Lightning Bolt"),
        third=lambda b: b,
    )
    bolt = card_of(situation, "Lightning Bolt", S2)
    cast(situation, S1, "Lightning Bolt", from_zone="graveyard", delta=bolt_at(3))
    assert stack_ids(situation) == ["s1"]

    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))

    assert situation.game.stack == []
    assert situation.game.find(bolt.id) is None


# @spec GAME-147
def test_the_tested_seat_ending_the_game_discards_the_window_and_the_stack() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_window("stack", asking=2),
    )

    acted(situation, end_game(situation.game, situation.deck, S1, result="win"))

    assert situation.game.stack == []
    assert situation.game.window is None
