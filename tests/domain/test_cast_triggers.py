"""Cast triggers: the casting seat's own triggers on casting a spell, stated with the `play` that
casts it. What an entry is and what refuses the call, in either kind of game; in a goldfish game
the triggers applied within the call before the spell; in a contested game the triggers put on
the stack above the spell, the window opened once, the disturbed exception and countering."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game.model import StackItemKind, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.steps import Step
from tests.support import tables
from tests.support.acting import (
    S1,
    S2,
    S3,
    a_trigger,
    acted,
    asking,
    cast,
    error_kinds,
    events_named,
    passed,
    playing,
    recorded,
    stack_ids,
)
from tests.support.builders import Situation, a_game
from tests.support.tables import S1_LANDS, bolt_at, three_seats, two_seats

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M2: not implemented yet")

STORM = "Thousand-Year Storm"
PYROMANCER = "Young Pyromancer"


def a_goldfish_table(*library: str) -> Situation:
    """A goldfish game in the first main step: a Lightning Bolt and a Forest in hand, a
    Mountain and two Forests on the battlefield, and `library` (top first)."""
    return (
        a_game()
        .with_hand("Lightning Bolt", "Forest")
        .with_battlefield("Mountain", "Forest", "Forest")
        .with_library(*(library or ("Island", "Swamp")))
        .build()
    )


def a_duel(**options: Any) -> Situation:
    """Seat 1 holds a Lightning Bolt and a Grizzly Bears; seat 2 has untapped lands, so it is
    asked when a window opens."""
    return two_seats(lambda b: b.with_hand("Lightning Bolt", "Grizzly Bears"), **options)


def a_duel_nobody_answers() -> Situation:
    """Seat 1 holds a Lightning Bolt and has its lands; seat 2 has no permanent, so it is
    passed automatically."""
    return two_seats(
        lambda b: b.with_battlefield(*S1_LANDS).with_hand("Lightning Bolt", "Grizzly Bears"),
        lambda b: b.with_hand("Island"),
        lands=False,
    )


def card_of(situation: Situation, name: str, owner: SeatNumber = S1) -> Any:
    return tables.card_of(situation, name, owner)


def top(situation: Situation) -> Any:
    return situation.game.stack[-1]


# ------------------------------------------------------------------ what a cast trigger is


# @spec PLAY-131
@NOT_BUILT
@pytest.mark.parametrize(
    "entry",
    [
        "draw a card",
        {"delta": {"draw": 1}},
        {"source": "   ", "delta": {"draw": 1}},
        {"source": 3, "delta": {"draw": 1}},
        {"source": STORM},
        {"source": STORM, "delta": None},
        {"source": STORM, "delta": ["draw"]},
        {"source": STORM, "delta": {}, "choices": "copy it"},
        {"source": STORM, "delta": {}, "pay": {"cost": "{1}"}},
    ],
    ids=[
        "not an object",
        "no source",
        "a source of whitespace",
        "a source that is not text",
        "no delta",
        "a null delta",
        "a delta that is not an object",
        "choices that are not an object",
        "another field",
    ],
)
def test_a_malformed_cast_trigger_is_an_error(entry: object) -> None:
    situation = a_goldfish_table()
    result = playing(situation, S1, "Lightning Bolt", cast_triggers=[entry])
    assert error_kinds(result) == ["malformed_argument"]


# @spec PLAY-131
@NOT_BUILT
def test_a_malformed_cast_trigger_is_an_error_in_a_contested_game() -> None:
    situation = a_duel()
    result = playing(situation, S1, "Lightning Bolt", cast_triggers=[{"source": STORM}])
    assert error_kinds(result) == ["malformed_argument"]


# @spec PLAY-131
@NOT_BUILT
def test_a_cast_trigger_with_an_empty_delta_is_accepted() -> None:
    situation = a_goldfish_table()
    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger(STORM, {})])
    assert "Lightning Bolt" in situation.names_in(Zone.GRAVEYARD)


# @spec PLAY-132
@NOT_BUILT
@pytest.mark.parametrize("contested", [False, True], ids=["goldfish", "contested"])
def test_a_land_takes_no_cast_triggers(contested: bool) -> None:
    situation = two_seats(lambda b: b.with_hand("Forest")) if contested else a_goldfish_table()
    result = playing(situation, S1, "Forest", cast_triggers=[a_trigger(STORM, {"draw": 1})])
    assert error_kinds(result) == ["land_not_cast"]


# @spec PLAY-134
@NOT_BUILT
@pytest.mark.parametrize("contested", [False, True], ids=["goldfish", "contested"])
@pytest.mark.parametrize("card", ["Lightning Bolt", "Forest"])
def test_an_empty_cast_triggers_changes_nothing(contested: bool, card: str) -> None:
    if contested:
        situation = two_seats(lambda b: b.with_hand("Lightning Bolt", "Forest"))
    else:
        situation = a_goldfish_table()
    delta = bolt_at(2) if contested else {"damage": 3}
    arguments: dict[str, Any] = {} if card == "Forest" else {"delta": delta}
    without = playing(situation, S1, card, **arguments)
    with_empty = playing(situation, S1, card, cast_triggers=[], **arguments)
    assert (with_empty.game, with_empty.events) == (without.game, without.events)


# @spec PLAY-142
@NOT_BUILT
def test_a_cast_trigger_s_x_and_extra_cost_pay_nothing() -> None:
    situation = a_goldfish_table()
    choices = {"x": 5, "extra_cost": "{3}"}
    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger(STORM, {}, choices=choices)])
    tapped = [c.name for c in situation.game.battlefield_of(S1) if c.tapped]
    assert tapped == ["Mountain"]


# @spec PLAY-142
@NOT_BUILT
def test_a_cast_trigger_s_definition_creates_no_card() -> None:
    situation = a_goldfish_table()
    choices = {"definition": {"name": "Made Up Copy", "type_line": "Instant"}}
    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger(STORM, {}, choices=choices)])
    assert all(c.name != "Made Up Copy" for c in situation.game.cards)


# @spec PLAY-142
@NOT_BUILT
@pytest.mark.parametrize(
    "choices",
    [{"x": "lots"}, {"extra_cost": "{Q}"}, {"definition": "a copy"}, {"modes": 3}],
    ids=["x", "extra_cost", "definition", "modes"],
)
def test_a_cast_trigger_s_choices_never_refuse_the_call(choices: dict[str, object]) -> None:
    situation = a_goldfish_table()
    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger(STORM, {}, choices=choices)])
    assert "Lightning Bolt" in situation.names_in(Zone.GRAVEYARD)


# ------------------------------------------------------------------ goldfish games


# @spec PLAY-135
@NOT_BUILT
def test_a_goldfish_cast_trigger_is_applied_before_the_spell_s_delta() -> None:
    situation = a_goldfish_table("Island", "Swamp")
    cast(
        situation,
        S1,
        "Lightning Bolt",
        delta={"discard": ["Island"]},
        cast_triggers=[a_trigger(STORM, {"draw": 1})],
    )
    assert "Island" in situation.names_in(Zone.GRAVEYARD)


# @spec PLAY-135
@NOT_BUILT
def test_goldfish_cast_triggers_are_applied_in_the_order_listed() -> None:
    situation = a_goldfish_table("Island", "Swamp")
    cast(
        situation,
        S1,
        "Lightning Bolt",
        cast_triggers=[
            a_trigger(STORM, {"draw": 1}),
            a_trigger(PYROMANCER, {"discard": ["Island"]}),
        ],
    )
    assert "Island" in situation.names_in(Zone.GRAVEYARD)


# @spec PLAY-135
@NOT_BUILT
def test_a_goldfish_spell_s_cost_is_paid_before_its_cast_triggers() -> None:
    situation = a_goldfish_table()
    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger(STORM, {"untap": ["Mountain"]})])
    assert not card_of(situation, "Mountain").tapped


# @spec PLAY-135
@NOT_BUILT
def test_a_goldfish_spell_reaches_its_destination_after_its_cast_triggers() -> None:
    situation = a_game().with_hand("Grizzly Bears").with_battlefield("Forest", "Forest").build()
    cast(situation, S1, "Grizzly Bears", cast_triggers=[a_trigger(STORM, {"draw": 1})])
    assert situation.names_in(Zone.BATTLEFIELD).count("Grizzly Bears") == 1


# @spec PLAY-136
@NOT_BUILT
def test_a_goldfish_cast_trigger_does_not_find_its_spell_s_card() -> None:
    situation = a_goldfish_table()
    trigger = a_trigger(STORM, {"move": {"exile": ["Lightning Bolt"]}})
    result = playing(situation, S1, "Lightning Bolt", cast_triggers=[trigger])
    assert error_kinds(result) == ["card_not_in_zone"]


# @spec PLAY-136
@NOT_BUILT
def test_a_goldfish_cast_trigger_naming_the_spell_s_card_finds_another_card_of_that_name() -> None:
    situation = (
        a_game()
        .with_hand("Lightning Bolt")
        .with_graveyard("Lightning Bolt")
        .with_battlefield("Mountain")
        .build()
    )
    in_graveyard = situation.ids_in(Zone.GRAVEYARD)
    trigger = a_trigger(STORM, {"move": {"exile": ["Lightning Bolt"]}})
    cast(situation, S1, "Lightning Bolt", cast_triggers=[trigger])
    assert situation.ids_in(Zone.EXILE) == in_graveyard


# @spec PLAY-136
@NOT_BUILT
def test_a_goldfish_cast_trigger_does_not_find_a_permanent_spell_on_the_battlefield() -> None:
    situation = a_game().with_hand("Grizzly Bears").with_battlefield("Forest", "Forest").build()
    trigger = a_trigger(STORM, {"counters": {"Grizzly Bears": {"+1/+1": 1}}})
    result = playing(situation, S1, "Grizzly Bears", cast_triggers=[trigger])
    assert error_kinds(result) == ["card_not_in_zone"]


# @spec PLAY-133
@NOT_BUILT
@pytest.mark.parametrize(
    ("delta", "kind"),
    [
        ({"bogus": 1}, "unknown_delta_key"),
        ({"tap": ["Shivan Dragon"]}, "card_not_in_zone"),
        ({"life": {"2": 1}}, "contested_only"),
    ],
    ids=["an unknown key", "a card not there", "a contested-only key"],
)
def test_an_error_in_a_goldfish_cast_trigger_refuses_the_whole_call(
    delta: dict[str, object], kind: str
) -> None:
    situation = a_goldfish_table()
    result = playing(
        situation,
        S1,
        "Lightning Bolt",
        delta={"damage": 3},
        cast_triggers=[a_trigger(STORM, delta)],
    )
    assert error_kinds(result) == [kind]


# @spec PLAY-137
@NOT_BUILT
@pytest.mark.parametrize(
    "delta",
    [{"look": {"n": 1, "rest": "library_top"}}, {"search": {}}],
    ids=["look", "search"],
)
def test_a_goldfish_cast_trigger_may_not_reveal_cards(delta: dict[str, object]) -> None:
    situation = a_goldfish_table()
    result = playing(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger(STORM, delta)])
    assert error_kinds(result) == ["cast_trigger_reveals"]


# ------------------------------------------------------------------ contested games: the stack


# @spec STACK-086
@NOT_BUILT
def test_a_cast_trigger_goes_on_the_stack_above_its_spell_as_an_ability_of_the_caster() -> None:
    situation = a_duel()
    trigger = a_trigger("Guttersnipe", {"damage": {"2": 2}}, choices={"notes": "two"})

    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=[trigger])

    item = top(situation)
    assert (item.kind, item.controller, item.source, item.card, item.cast_with) == (
        StackItemKind.ABILITY,
        S1,
        "Guttersnipe",
        None,
        "s1",
    )
    assert (item.delta, item.choices) == ({"damage": {"2": 2}}, {"notes": "two"})


# @spec STACK-086
@NOT_BUILT
def test_a_cast_trigger_on_the_stack_has_not_applied_its_delta() -> None:
    situation = a_duel()

    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger("Guttersnipe", bolt_at(2, 2))])

    assert situation.game.seat(S2).life == 40


# @spec STACK-087
@NOT_BUILT
def test_cast_triggers_go_on_the_stack_so_that_the_first_listed_is_on_top() -> None:
    situation = a_duel()
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"life": 2})]

    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=triggers)

    assert stack_ids(situation) == ["s1", "s2", "s3"]
    assert [item.source for item in situation.game.stack] == ["Lightning Bolt", "second", "first"]


# @spec STACK-034
@NOT_BUILT
def test_one_window_opens_for_the_top_item_once_a_spell_and_its_cast_triggers_are_on() -> None:
    situation = a_duel()
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"life": 2})]

    cast(situation, S1, "Lightning Bolt", cast_triggers=triggers)

    window = situation.game.window
    assert window is not None
    assert (window.kind.value, window.asking, window.passed) == ("stack", S2, ())


# @spec STACK-034
@NOT_BUILT
def test_the_first_seat_passed_automatically_after_a_cast_is_passed_on_the_top_item() -> None:
    situation = three_seats(
        lambda b: b.with_battlefield(*S1_LANDS).with_hand("Lightning Bolt"),
        lambda b: b.with_hand("Island"),
        lambda b: b.with_battlefield("Island"),
        lands=False,
    )
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"life": 2})]

    result = cast(situation, S1, "Lightning Bolt", cast_triggers=triggers)

    assert [(p.seat, p.item) for p in events_named(result, "AutomaticPass")] == [(S2, "s3")]
    assert asking(situation) == S3


# @spec STACK-088
@NOT_BUILT
def test_a_cast_trigger_may_counter_its_own_spell() -> None:
    situation = a_duel()
    trigger = a_trigger("a misfire", {"counter": ["Lightning Bolt"]})

    cast(situation, S1, "Lightning Bolt", cast_triggers=[trigger])

    assert top(situation).delta["counter"] == ["s1"]


# @spec STACK-088
@NOT_BUILT
def test_a_cast_trigger_may_counter_an_item_below_its_spell() -> None:
    situation = two_seats(
        lambda b: b.with_hand("Lightning Bolt"),
        lambda b: b.with_ability_on_stack("a drain", delta=bolt_at(1)).with_window(
            "stack", asking=1
        ),
    )
    trigger = a_trigger("a redirect", {"counter": ["s1"]})

    cast(situation, S1, "Lightning Bolt", cast_triggers=[trigger])

    assert top(situation).delta["counter"] == ["s1"]


# @spec STACK-088, PLAY-133
@NOT_BUILT
def test_a_cast_trigger_may_not_counter_another_cast_trigger_of_the_same_call() -> None:
    situation = a_duel()
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"counter": ["s3"]})]

    result = playing(situation, S1, "Lightning Bolt", cast_triggers=triggers)

    assert error_kinds(result) == ["not_on_stack"]


# @spec PLAY-133
@NOT_BUILT
@pytest.mark.parametrize(
    ("delta", "kind"),
    [
        ({"bogus": 1}, "unknown_delta_key"),
        ({"life": {"5": 1}}, "no_such_seat"),
        ({"counter": ["Counterspell"]}, "not_on_stack"),
        ({"damage": 3}, "damage_needs_seats"),
    ],
    ids=["an unknown key", "a seat not in the game", "a counter naming nothing", "pooled damage"],
)
def test_an_error_in_a_contested_cast_trigger_refuses_the_whole_call(
    delta: dict[str, object], kind: str
) -> None:
    situation = a_duel()
    result = playing(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger("x", delta)])
    assert error_kinds(result) == [kind]


# @spec PLAY-133, STACK-066
@NOT_BUILT
def test_a_contested_cast_trigger_naming_a_card_not_in_play_is_accepted_when_cast() -> None:
    situation = a_duel()

    cast(
        situation, S1, "Lightning Bolt", cast_triggers=[a_trigger("x", {"tap": ["Shivan Dragon"]})]
    )

    assert top(situation).delta == {"tap": ["Shivan Dragon"]}


# @spec PLAY-143
@NOT_BUILT
def test_expect_is_compared_once_the_cast_triggers_are_on_the_stack_before_any_resolves() -> None:
    situation = a_duel_nobody_answers()

    result = cast(
        situation,
        S1,
        "Lightning Bolt",
        delta=bolt_at(2),
        cast_triggers=[a_trigger("a lifelink copy", {"life": 2})],
        expect={"life": 42},
    )

    assert [(e.key, e.actual) for e in events_named(result, "ExpectationMismatched")] == [
        ("life", "40")
    ]


# ------------------------------------------------------------------ contested games: resolving


# @spec STACK-089, STACK-023
@NOT_BUILT
def test_a_resolving_cast_trigger_leaves_its_spell_and_sibling_triggers_undisturbed() -> None:
    situation = a_duel()
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"life": 2})]
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=triggers)

    passed(situation, S2)

    assert stack_ids(situation) == ["s1", "s2"]
    assert not any(item.disturbed for item in situation.game.stack)


# @spec STACK-089
@NOT_BUILT
def test_a_cast_trigger_resolving_as_restated_leaves_its_spell_and_siblings_undisturbed() -> None:
    situation = a_duel()
    triggers = [a_trigger("first", {"tap": ["Shivan Dragon"]}), a_trigger("second", {"life": 2})]
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=triggers)
    passed(situation, S2)
    choice = situation.game.pending[0].choice_id

    acted(
        situation,
        choose(situation.game, situation.deck, S1, choice_id=choice, restate={"delta": {}}),
    )

    assert stack_ids(situation) == ["s1", "s2"]
    assert not any(item.disturbed for item in situation.game.stack)


# @spec STACK-023, STACK-089
@NOT_BUILT
def test_another_seat_s_response_resolving_above_cast_triggers_disturbs_them_and_the_spell() -> (
    None
):
    situation = a_duel()
    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger("first", {"life": 1})])
    recorded(situation, S2, "a trick", {"life": {"2": 1}})

    passed(situation, S1)

    assert stack_ids(situation) == ["s1", "s2"]
    assert all(item.disturbed for item in situation.game.stack)


# @spec STACK-090
@NOT_BUILT
def test_cast_triggers_nobody_answers_resolve_within_the_play_first_listed_first() -> None:
    situation = a_duel_nobody_answers()
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"life": 2})]

    result = cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=triggers)

    assert [e.item for e in events_named(result, "ItemResolved")] == ["s3", "s2", "s1"]


# @spec STACK-090
@NOT_BUILT
def test_cast_triggers_nobody_answers_leave_the_stack_empty_with_every_delta_applied() -> None:
    situation = a_duel_nobody_answers()
    triggers = [a_trigger("first", {"life": 1}), a_trigger("second", {"life": 2})]

    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=triggers)

    assert (situation.game.stack, situation.game.seat(S1).life) == ([], 43)


# @spec STACK-090, STACK-070
@NOT_BUILT
def test_a_pending_choice_a_cast_trigger_creates_stops_the_resolving_within_the_play() -> None:
    situation = a_duel_nobody_answers()
    trigger = a_trigger("a punisher", {"ask": [{"seats": [2], "text": "discard a card"}]})

    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), cast_triggers=[trigger])

    assert stack_ids(situation) == ["s1"]


# @spec STACK-091
@NOT_BUILT
def test_a_countered_spell_leaves_its_cast_triggers_on_the_stack() -> None:
    situation = two_seats(
        lambda b: b.with_hand("Grizzly Bears"), lambda b: b.with_hand("Counterspell")
    )
    cast(situation, S1, "Grizzly Bears", cast_triggers=[a_trigger("first", {"life": 1})])
    cast(situation, S2, "Counterspell", delta={"counter": ["Grizzly Bears"]})

    passed(situation, S1)

    assert [(item.id, item.source) for item in situation.game.stack] == [("s2", "first")]


# ------------------------------------------------------------------ reminders


# @spec REC-086
@NOT_BUILT
@pytest.mark.parametrize("contested", [False, True], ids=["goldfish", "contested"])
def test_a_cast_trigger_answers_no_reminder(contested: bool) -> None:
    def reminded(builder: Any) -> Any:
        return (
            builder.with_battlefield("Phyrexian Arena", "Mountain")
            .with_hand("Lightning Bolt")
            .with_reminder("Phyrexian Arena", Step.UPKEEP)
        )

    situation = two_seats(reminded, lands=False) if contested else reminded(a_game()).build()

    cast(situation, S1, "Lightning Bolt", cast_triggers=[a_trigger("Phyrexian Arena", {})])

    assert [r.answered for r in situation.game.seat(S1).reminders] == [False]
