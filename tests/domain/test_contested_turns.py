"""Turns in a contested game: the turn passes from seat to seat, rounds are counted, and each
seat's own turn count is kept."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.events import NoticeKind, StepsEntered
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import Situation, a_game

S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)


def advanced(situation: Situation, seat: SeatNumber, **arguments: object) -> Applied:
    result = advance(situation.game, situation.deck, seat, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def two_seats_in_the_first_seat_s(
    step: Step, *, table_turn: int = 3, round_number: int = 2
) -> Situation:
    """Seat 1's turn in `step`: seat 1 has begun 2 turns, seat 2 one."""
    builder: Any = (
        a_game()
        .in_step(step, turn=table_turn)
        .in_round(round_number)
        .with_turns_taken(2)
        .with_battlefield("Forest", tapped=True)
        .with_library("Island", "Island")
    )
    return (
        builder.and_an_opposing_seat()
        .with_turns_taken(1)
        .with_battlefield("Forest", "Llanowar Elves", tapped=True)
        .with_library("Swamp", "Plains")
        .build()
    )


def two_seats_in_the_second_seat_s(step: Step) -> Situation:
    """Seat 2's turn of round 2 in `step`: each seat has begun 2 turns."""
    builder: Any = (
        a_game()
        .in_step(step, turn=4)
        .in_round(2)
        .in_turn_of(2)
        .with_turns_taken(2)
        .with_library("Island", "Island")
    )
    return builder.and_an_opposing_seat().with_turns_taken(2).with_library("Swamp").build()


# ------------------------------------------------------------------ passing the turn


# @spec TURN-031
def test_leaving_cleanup_makes_the_next_seat_in_turn_order_the_active_seat() -> None:
    situation = two_seats_in_the_first_seat_s(Step.CLEANUP)
    advanced(situation, S1)
    game = situation.game
    assert (game.active, game.turn) == (S2, 4)
    assert [seat.turns for seat in game.seats] == [2, 2]


# @spec TURN-031
def test_the_turn_passes_over_an_eliminated_seat() -> None:
    builder: Any = a_game().in_step(Step.CLEANUP).with_library("Island")
    builder = builder.and_an_opposing_seat().eliminated().with_library("Swamp")
    situation = builder.and_an_opposing_seat().with_library("Plains").build()
    advanced(situation, S1)
    assert situation.game.active == S3
    assert situation.game.seat(S2).turns == 0


# @spec TURN-033
def test_the_turn_passing_to_a_later_seat_stays_in_the_round() -> None:
    situation = two_seats_in_the_first_seat_s(Step.CLEANUP)
    advanced(situation, S1)
    assert situation.game.round == 2


# @spec TURN-033
def test_the_turn_passing_back_to_an_earlier_seat_begins_a_new_round() -> None:
    situation = two_seats_in_the_second_seat_s(Step.CLEANUP)
    advanced(situation, S2)
    assert (situation.game.active, situation.game.round) == (S1, 3)


# @spec TURN-033
def test_the_turn_passing_to_the_only_seat_left_begins_a_new_round() -> None:
    builder: Any = a_game().in_step(Step.CLEANUP).in_round(2).with_library("Island")
    builder = builder.and_an_opposing_seat().eliminated().with_library("Swamp")
    situation = builder.and_an_opposing_seat().eliminated().with_library("Plains").build()
    advanced(situation, S1)
    assert (situation.game.active, situation.game.round) == (S1, 3)


# @spec TURN-039
def test_an_advance_to_a_step_of_a_later_turn_ends_with_its_own_seat_s_turn() -> None:
    situation = two_seats_in_the_first_seat_s(Step.MAIN2)
    advanced(situation, S1, to="main2")
    game = situation.game
    assert (game.active, game.step) == (S2, Step.MAIN1)


# @spec TURN-040
def test_the_next_seat_s_turn_goes_on_to_its_first_main_step_within_the_call() -> None:
    situation = two_seats_in_the_first_seat_s(Step.END)
    result = advanced(situation, S1, to="main1")
    assert situation.game.step is Step.MAIN1
    assert isinstance(result.summary, StepsEntered)
    assert [entered.step for entered in result.summary.steps] == [
        Step.CLEANUP,
        Step.UNTAP,
        Step.UPKEEP,
        Step.DRAW,
        Step.MAIN1,
    ]


# @spec TURN-040
def test_the_next_seat_draws_for_its_turn_within_the_call() -> None:
    situation = two_seats_in_the_first_seat_s(Step.CLEANUP)
    advanced(situation, S1)
    assert [card.name for card in situation.game.hand_of(S2)] == ["Swamp"]


# @spec TURN-040
def test_the_next_seat_s_turn_stops_where_its_reminder_stops_it() -> None:
    builder: Any = a_game().in_step(Step.CLEANUP).with_library("Island")
    situation = (
        builder.and_an_opposing_seat()
        .with_battlefield("Phyrexian Arena")
        .with_library("Swamp")
        .build()
    )
    advanced(situation, S1, to="main1")
    game = situation.game
    assert (game.active, game.step) == (S2, Step.UPKEEP)
    assert game.hand_of(S2) == []


# @spec TURN-041
def test_the_seat_whose_turn_begins_is_then_the_seat_to_act() -> None:
    situation = two_seats_in_the_first_seat_s(Step.CLEANUP)
    advanced(situation, S1)
    asked: Any = acting.seats_to_act(situation.game)
    assert (asked.seats, asked.kind.value) == ((S2,), "turn")


# @spec TURN-042
def test_the_outcome_shows_the_turn_passing_to_the_new_active_seat() -> None:
    situation = two_seats_in_the_first_seat_s(Step.CLEANUP)
    result = advanced(situation, S1)
    summary: Any = result.summary
    untap = next(entered for entered in summary.steps if entered.step is Step.UNTAP)
    assert (untap.seat, untap.turn) == (S2, 2)


# @spec TURN-042
def test_the_card_the_new_active_seat_drew_is_named_only_to_that_seat() -> None:
    situation = two_seats_in_the_first_seat_s(Step.CLEANUP)
    result = advanced(situation, S1)
    events = (result.summary, *result.events)
    assert "'Swamp'" in repr(as_seen_by(events, S2))
    assert "'Swamp'" not in repr(as_seen_by(events, S1))


# ------------------------------------------------------------------ what a turn's start touches


# @spec TURN-027
def test_a_seat_s_untap_leaves_the_other_seats_permanents_land_drops_and_statistics() -> None:
    builder: Any = (
        a_game()
        .in_step(Step.CLEANUP, turn=3)
        .in_round(2)
        .with_battlefield("Forest", tapped=True)
        .with_land_drops_used(1)
        .with_library("Island")
    )
    situation = (
        builder.and_an_opposing_seat()
        .with_battlefield("Swamp", tapped=True)
        .with_land_drops_used(1)
        .with_library("Plains")
        .build()
    )
    situation.game.seat(S1).turn_stats.mana_spent = 3
    advanced(situation, S1)
    game = situation.game
    assert situation.named("Forest").tapped is True
    assert situation.named("Swamp").tapped is False
    assert (game.seat(S1).land_drops_used, game.seat(S1).turn_stats.mana_spent) == (1, 3)
    assert game.seat(S2).land_drops_used == 0


# @spec TURN-028
def test_a_seat_draws_on_its_first_turn_after_the_table_s_first_when_the_first_draw_is_off() -> (
    None
):
    builder: Any = (
        a_game().without_first_turn_draw().in_step(Step.CLEANUP, turn=1).with_library("Island")
    )
    situation = builder.and_an_opposing_seat().with_turns_taken(0).with_library("Swamp").build()
    advanced(situation, S1)
    assert [card.name for card in situation.game.hand_of(S2)] == ["Swamp"]


# @spec TURN-060
def test_only_the_active_seat_s_hand_is_held_to_seven_at_cleanup() -> None:
    builder: Any = a_game().in_step(Step.END).with_hand("Forest").with_library("Island")
    situation = (
        builder.and_an_opposing_seat().with_hand(*("Swamp",) * 9).with_library("Plains").build()
    )
    advanced(situation, S1, to="main1")
    game = situation.game
    assert (game.active, game.step) == (S2, Step.MAIN1)
    assert len(game.hand_of(S2)) == 10


# ------------------------------------------------------------------ the turn limit counts rounds


def with_a_turn_limit_of_two() -> Situation:
    builder: Any = (
        a_game()
        .with_turn_limit(2)
        .in_step(Step.CLEANUP, turn=1)
        .in_round(1)
        .with_turns_taken(1)
        .with_library("Island", "Island")
    )
    return builder.and_an_opposing_seat().with_turns_taken(0).with_library("Swamp", "Swamp").build()


# @spec GAME-144
def test_the_turn_limit_is_not_reached_by_the_second_turn_of_the_first_round() -> None:
    situation = with_a_turn_limit_of_two()
    advanced(situation, S1)
    assert (situation.game.turn, situation.game.round) == (2, 1)
    assert NoticeKind.TURN_LIMIT not in situation.game.notices


# @spec GAME-144
def test_the_turn_limit_is_reached_on_entering_the_first_turn_of_its_round() -> None:
    situation = with_a_turn_limit_of_two()
    advanced(situation, S1)
    advanced(situation, S2, to="cleanup")
    advanced(situation, S2)
    assert (situation.game.turn, situation.game.round) == (3, 2)
    assert situation.game.notices == [NoticeKind.TURN_LIMIT]
