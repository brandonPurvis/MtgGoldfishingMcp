"""Reminders for seats other than the active seat: which step triggers remind whom, the game
waiting on a reminded seat, and how a reminded seat answers or declines."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted, events_named, passed, recorded, stack_ids
from tests.support.builders import a_game
from tests.support.tables import a_table, bolt_at

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M4: not built")


def at_untap(*describers: Any) -> Any:
    """Seat 1's untap step; the next step entered is its upkeep."""
    return a_table(*describers, step=Step.UNTAP)


def advanced(situation: Any, seat: Any = S1, **arguments: Any) -> Any:
    return acted(situation, advance(situation.game, situation.deck, seat, **arguments))


def reminded(result: Any) -> list[tuple[Any, tuple[tuple[str, int], ...]]]:
    """Each reminder line of a call: the seat reminded and the cards it was reminded of."""
    return [(event.seat, event.cards) for event in events_named(result, "ReminderIssued")]


def asked(situation: Any) -> tuple[tuple[Any, ...], str]:
    found: Any = acting.seats_to_act(situation.game)
    return found.seats, found.kind.value


def none() -> Any:
    return lambda b: b


def vise_and_vortex() -> Any:
    """At S1's untap: S2 has Black Vise (each opponent's upkeep) and Sulfuric Vortex (each
    upkeep)."""
    return at_untap(
        none(),
        lambda b: b.with_battlefield("Black Vise", "Sulfuric Vortex").with_hand("Lightning Bolt"),
    )


def in_upkeep_reminded(situation: Any) -> Any:
    advanced(situation)
    return situation


# ------------------------------------------------------------------ who is reminded


# @spec TURN-047
def test_a_goldfish_seat_is_not_reminded_of_a_trigger_on_opponents_turns_only() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Black Vise").build()

    result = advanced(situation)

    assert reminded(result) == []


# @spec TURN-047
def test_the_active_seat_is_not_reminded_of_a_trigger_on_opponents_turns_only() -> None:
    situation = at_untap(lambda b: b.with_battlefield("Black Vise"), none())

    result = advanced(situation)

    assert reminded(result) == []


# @spec TURN-048
@NOT_BUILT
def test_another_seat_is_reminded_of_its_triggers_on_each_turn_and_on_opponents_turns() -> None:
    situation = vise_and_vortex()

    result = advanced(situation)

    assert reminded(result) == [(S2, (("Black Vise", 1), ("Sulfuric Vortex", 1)))]


# @spec TURN-049
def test_another_seat_is_not_reminded_of_a_trigger_on_its_own_turn_only() -> None:
    situation = at_untap(none(), lambda b: b.with_battlefield("Mystic Remora"))

    result = advanced(situation)

    assert reminded(result) == []


# @spec TURN-050
@NOT_BUILT
def test_a_reminder_goes_to_the_seat_that_controls_the_permanent() -> None:
    situation = at_untap(
        none(), none(), lambda b: b.with_battlefield("Black Vise").controlled_by("Black Vise", 2)
    )

    result = advanced(situation)

    assert reminded(result) == [(S2, (("Black Vise", 1),))]


# @spec TURN-055
@NOT_BUILT
def test_permanents_of_one_name_under_different_controllers_are_reminded_to_each() -> None:
    situation = at_untap(
        none(),
        lambda b: b.with_battlefield("Black Vise"),
        lambda b: b.with_battlefield("Black Vise"),
    )

    result = advanced(situation)

    assert reminded(result) == [(S2, (("Black Vise", 1),)), (S3, (("Black Vise", 1),))]


# ------------------------------------------------------------------ waiting on a reminded seat


# @spec TURN-051
@NOT_BUILT
def test_an_advance_stops_where_another_seat_is_reminded_and_that_seat_acts() -> None:
    situation = vise_and_vortex()

    advanced(situation, to="main1")

    assert situation.game.step is Step.UPKEEP
    assert asked(situation) == ((S2,), "trigger")


# @spec TURN-052, TURN-063
@NOT_BUILT
def test_the_game_waits_until_each_reminder_of_the_seat_is_answered() -> None:
    situation = in_upkeep_reminded(vise_and_vortex())

    recorded(situation, S2, "Black Vise", bolt_at(1, 2))
    still = asked(situation)
    recorded(situation, S2, "Sulfuric Vortex", bolt_at(1, 2))

    assert still == ((S2,), "trigger")
    assert asked(situation) != ((S2,), "trigger")


# @spec TURN-063
@NOT_BUILT
def test_an_effect_naming_a_reminded_permanent_goes_on_the_stack_and_answers_it() -> None:
    situation = in_upkeep_reminded(vise_and_vortex())

    recorded(situation, S2, "black vise", bolt_at(1, 2))

    assert stack_ids(situation) == ["s1"]
    answered = {r.name: r.answered for r in situation.game.seat(S2).reminders}
    assert answered == {"Black Vise": True, "Sulfuric Vortex": False}


# @spec TURN-064, STACK-051
@NOT_BUILT
def test_a_pass_declines_every_reminder_of_the_step_still_unanswered() -> None:
    situation = in_upkeep_reminded(vise_and_vortex())

    passed(situation, S2)

    assert asked(situation) == ((S1,), "turn")


# @spec TURN-065, STACK-079
@NOT_BUILT
@pytest.mark.parametrize("call", ["play", "immediate effect", "unnamed effect"])
def test_other_calls_from_a_reminded_seat_are_applied_and_its_reminders_wait(call: str) -> None:
    situation = in_upkeep_reminded(vise_and_vortex())
    if call == "play":
        result: Any = play(
            situation.game, situation.deck, S2, card="Lightning Bolt", delta=bolt_at(1)
        )
    else:
        result = effect(
            situation.game,
            situation.deck,
            S2,
            source="Island" if call == "immediate effect" else "a curse",
            delta={"mana": "{U}"} if call == "immediate effect" else {"life": 1},
            immediate=call == "immediate effect",
        )

    acted(situation, result)

    assert asked(situation) == ((S2,), "trigger")


# @spec TURN-066
@NOT_BUILT
def test_while_another_seat_is_reminded_nothing_on_the_stack_resolves() -> None:
    situation = at_untap(
        lambda b: b.with_battlefield("Forest", tapped=True),
        lambda b: b.with_battlefield("Black Vise"),
        lambda b: b.with_battlefield("Sulfuric Vortex"),
    )
    advanced(situation)

    recorded(situation, S2, "Black Vise", bolt_at(1, 2))

    assert stack_ids(situation) == ["s1"]
    assert situation.game.window is None or situation.game.window.asking is None
    assert asked(situation) == ((S3,), "trigger")


# @spec TURN-053
@NOT_BUILT
def test_reminded_seats_are_waited_on_one_at_a_time_in_turn_order() -> None:
    situation = at_untap(
        none(),
        lambda b: b.with_battlefield("Black Vise"),
        lambda b: b.with_battlefield("Sulfuric Vortex"),
    )
    advanced(situation)
    first = asked(situation)

    passed(situation, S2)

    assert (first, asked(situation)) == (((S2,), "trigger"), ((S3,), "trigger"))


# @spec TURN-054
@NOT_BUILT
def test_once_every_reminded_seat_has_answered_the_active_seat_continues() -> None:
    situation = in_upkeep_reminded(vise_and_vortex())

    passed(situation, S2)

    assert situation.game.stack == []
    assert asked(situation) == ((S1,), "turn")
    assert acting.may_call(situation.game, S1, "advance") is None


# @spec TURN-067
@NOT_BUILT
def test_a_reminder_for_the_active_seat_does_not_make_the_game_wait() -> None:
    situation = at_untap(lambda b: b.with_battlefield("Mystic Remora"), none())

    result = advanced(situation, to="main1")

    assert reminded(result) == [(S1, (("Mystic Remora", 1),))]
    assert situation.game.step is Step.UPKEEP
    assert asked(situation) == ((S1,), "turn")
    assert acting.may_call(situation.game, S1, "advance") is None
