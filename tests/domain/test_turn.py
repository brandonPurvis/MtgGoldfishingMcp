"""Advancing through the steps of a turn."""

from __future__ import annotations

import pytest

from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    CardsDrawn,
    CheckKind,
    ChecksOverridden,
    EnteredStep,
    Error,
    ErrorKind,
    FailedCheck,
    ReminderIssued,
    StepsEntered,
    StopReason,
)
from mtg_goldfishing.domain.game.model import Attack, Zone
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.mana import ManaPool
from mtg_goldfishing.domain.steps import STEPS, Step
from mtg_goldfishing.domain.turn import Walk, advance, return_to_declare_attackers
from tests.support.builders import Situation, a_game


def advanced(situation: Situation, **arguments: object) -> Applied:
    result = advance(situation.game, situation.deck, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Applied), result
    return result


def refused(situation: Situation, **arguments: object) -> Refusal:
    result = advance(situation.game, situation.deck, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Refusal), result
    return result


def a_big_hand(cards: int) -> tuple[str, ...]:
    return ("Ponder",) * cards


# @spec TURN-001
def test_the_steps_follow_in_order_and_untap_follows_cleanup() -> None:
    situation = a_game().in_step(Step.UNTAP, turn=2).with_library(*("Forest",) * 3).build()
    seen = []
    for _ in range(len(STEPS)):
        result = advanced(situation)
        situation.game = result.game
        seen.append(result.game.step)
    assert seen == [*STEPS[1:], Step.UNTAP]


# @spec TURN-002
def test_entering_untap_starts_the_next_turn_with_everything_untapped() -> None:
    situation = (
        a_game()
        .in_step(Step.CLEANUP, turn=4)
        .with_battlefield("Forest", "Grizzly Bears", tapped=True)
        .with_land_drops_used(1)
        .build()
    )
    situation.game.turn_stats.mana_spent = 5
    game = advanced(situation).game
    assert (game.turn, game.step, game.land_drops_used) == (5, Step.UNTAP, 0)
    assert not any(card.tapped for card in game.battlefield)
    assert game.turn_stats.mana_spent == 0


# @spec TURN-003
def test_entering_draw_draws_a_card() -> None:
    situation = a_game().in_step(Step.UPKEEP).with_library("Island", "Forest").build()
    result = advanced(situation)
    assert CardsDrawn(("Island",)) in result.events
    assert [c.name for c in result.game.hand] == ["Island"]


# @spec TURN-003
def test_turn_one_does_not_draw_when_the_first_turn_draw_is_off() -> None:
    situation = (
        a_game()
        .in_step(Step.UPKEEP, turn=1)
        .without_first_turn_draw()
        .with_library("Island")
        .build()
    )
    assert advanced(situation).game.hand == []


# @spec TURN-004
def test_entering_cleanup_writes_the_turn_snapshot() -> None:
    situation = a_game().in_step(Step.END, turn=4).build()
    result = advanced(situation)
    assert [s.turn for s in result.snapshots] == [4]


# @spec TURN-005
def test_leaving_a_step_empties_the_mana_pool() -> None:
    situation = a_game().in_step(Step.MAIN1).with_pool("{G}{G}").build()
    assert advanced(situation).game.mana_pool == ManaPool()


# @spec TURN-006
def test_advance_without_a_target_moves_to_the_next_step() -> None:
    situation = a_game().in_step(Step.MAIN1).build()
    assert advanced(situation).game.step is Step.BEGIN_COMBAT


# @spec TURN-007
def test_advance_to_a_step_moves_through_every_step_up_to_it() -> None:
    situation = a_game().in_step(Step.MAIN2, turn=3).with_library("Forest").build()
    result = advanced(situation, to="main1")
    assert result.summary == StepsEntered(
        (
            EnteredStep(3, Step.END),
            EnteredStep(3, Step.CLEANUP),
            EnteredStep(4, Step.UNTAP),
            EnteredStep(4, Step.UPKEEP),
            EnteredStep(4, Step.DRAW),
            EnteredStep(4, Step.MAIN1),
        )
    )


# @spec TURN-008
def test_advance_to_the_current_step_goes_to_that_step_next_turn() -> None:
    situation = a_game().in_step(Step.MAIN1, turn=3).with_library("Forest").build()
    game = advanced(situation, to="main1").game
    assert (game.turn, game.step) == (4, Step.MAIN1)


# @spec TURN-009
def test_an_advance_reports_steps_draws_and_reminders() -> None:
    situation = (
        a_game()
        .in_step(Step.UNTAP, turn=3)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest")
        .build()
    )
    result = advanced(situation, to="upkeep")
    assert isinstance(result.summary, StepsEntered)
    assert ReminderIssued(Step.UPKEEP, (("Phyrexian Arena", 1),)) in result.events


# @spec TURN-010
def test_advancing_to_an_unknown_step_is_an_error() -> None:
    situation = a_game().build()
    assert refused(situation, to="second_breakfast") == Refusal.error(
        Error(ErrorKind.UNKNOWN_STEP, subject="second_breakfast")
    )


# @spec TURN-011, TURN-012
def test_an_advance_stops_in_a_step_with_a_reminder_and_says_what_to_send() -> None:
    situation = (
        a_game()
        .in_step(Step.END, turn=6)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest")
        .build()
    )
    result = advanced(situation, to="main1")
    assert result.game.step is Step.UPKEEP
    assert result.events[-1] == AdvanceStopped(StopReason.REMINDER, Step.UPKEEP, Step.MAIN1)


# @spec TURN-013
def test_triggers_in_the_step_being_left_never_stop_an_advance() -> None:
    situation = (
        a_game()
        .in_step(Step.UPKEEP, turn=6)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest")
        .build()
    )
    assert advanced(situation, to="main1").game.step is Step.MAIN1


# @spec TURN-014
def test_several_permanents_with_the_same_name_are_reminded_once_with_a_count() -> None:
    situation = (
        a_game().in_step(Step.UNTAP).with_battlefield("Rhystic Study", "Rhystic Study").build()
    )
    result = advanced(situation)
    assert ReminderIssued(Step.UPKEEP, (("Rhystic Study", 2),)) in result.events


# @spec TURN-015, TURN-016
def test_a_reminder_is_never_enforced_and_the_target_is_not_remembered() -> None:
    situation = (
        a_game()
        .in_step(Step.UNTAP, turn=6)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest")
        .build()
    )
    first = advanced(situation, to="main1")
    situation.game = first.game
    second = advanced(situation)
    assert second.game.step is Step.DRAW


# @spec TURN-017
def test_too_many_cards_before_cleanup_stops_in_the_end_step() -> None:
    situation = a_game().in_step(Step.MAIN2).with_hand(*a_big_hand(9)).build()
    result = advanced(situation, to="main1")
    assert result.game.step is Step.END
    assert result.events[-1] == AdvanceStopped(StopReason.DISCARD, Step.END, Step.MAIN1, 2)


# @spec TURN-018
def test_discarding_exactly_the_excess_discards_on_entering_cleanup() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(8), "Forest").build()
    result = advanced(situation, discard=["Forest", "Ponder"])
    assert result.game.step is Step.CLEANUP
    assert sorted(c.name for c in result.game.in_zone(Zone.GRAVEYARD)) == ["Forest", "Ponder"]


# @spec TURN-019
def test_an_override_without_discard_enters_cleanup_keeping_every_card() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    result = advanced(situation, override="Reliquary Tower")
    assert len(result.game.hand) == 9


# @spec TURN-020
def test_an_override_with_discard_discards_exactly_the_cards_named() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    result = advanced(situation, discard=["Ponder"], override="madness")
    assert len(result.game.hand) == 8


# @spec TURN-019, REC-006
def test_an_override_that_lets_an_advance_keep_too_many_cards_records_the_overridden_check() -> (
    None
):
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    result = advanced(situation, override="Reliquary Tower")
    overridden = ChecksOverridden(
        (FailedCheck(CheckKind.HAND_TOO_BIG, number=2),), "Reliquary Tower"
    )
    assert overridden in result.events


# @spec TURN-020, REC-006
def test_an_override_that_lets_a_wrong_discard_count_through_records_the_overridden_check() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    result = advanced(situation, discard=["Ponder"], override="madness")
    overridden = ChecksOverridden(
        (FailedCheck(CheckKind.DISCARD_COUNT, number=1, expected=2),), "madness"
    )
    assert overridden in result.events


# @spec TURN-021
def test_an_advance_starting_in_end_with_too_many_cards_fails_a_rule_check() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    result = refused(situation)
    assert [(c.kind, c.number) for c in result.checks] == [(CheckKind.HAND_TOO_BIG, 2)]


# @spec TURN-022
def test_discarding_the_wrong_number_without_override_fails_a_rule_check() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    result = refused(situation, discard=["Ponder"])
    assert [(c.kind, c.number, c.expected) for c in result.checks] == [
        (CheckKind.DISCARD_COUNT, 1, 2)
    ]


# @spec TURN-023
def test_discarding_a_card_not_in_hand_is_an_error() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(8)).build()
    result = refused(situation, discard=["Forest"])
    assert result.errors[0].kind is ErrorKind.DISCARD_NOT_IN_HAND


# @spec TURN-024
@pytest.mark.parametrize("start", [Step.MAIN1, Step.UNTAP])
def test_discard_on_an_advance_that_does_not_enter_cleanup_is_an_error(start: Step) -> None:
    situation = (
        a_game().in_step(start).with_battlefield("Phyrexian Arena").with_hand("Ponder").build()
    )
    result = refused(situation, to="main2" if start is Step.MAIN1 else "end", discard=["Ponder"])
    assert result == Refusal.error(Error(ErrorKind.DISCARD_WITHOUT_CLEANUP))


# @spec TURN-024
def test_a_refused_advance_never_moves_the_game() -> None:
    situation = a_game().in_step(Step.END).with_hand(*a_big_hand(9)).build()
    before = situation.game.copy()
    refused(situation)
    assert situation.game == before


# @spec TURN-025
def test_the_turn_limit_never_stops_an_advance() -> None:
    situation = a_game().in_step(Step.CLEANUP, turn=5).with_turn_limit(3).with_library("Forest")
    game = advanced(situation.build(), to="main1").game
    assert game.turn == 6


# @spec TURN-026
def test_an_additional_combat_returns_to_declare_attackers_in_the_same_turn() -> None:
    situation = a_game().in_step(Step.MAIN2, turn=4).with_pool("{R}").build()
    situation.game.declared_attack = Attack(attackers=[])
    return_to_declare_attackers(situation.game, situation.deck, Walk())
    assert (situation.game.turn, situation.game.step) == (4, Step.DECLARE_ATTACKERS)
    assert situation.game.mana_pool == ManaPool()
