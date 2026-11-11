"""Turn snapshots of a contested game: one for every seat's turn, numbered by table turn,
describing the active seat, with every seat's life and the unanswered reminders of the turn."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import Reminder
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.records.export import snapshot_to_data
from mtg_goldfishing.domain.records.snapshots import take_snapshot
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted
from tests.support.builders import Situation, a_game

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
ATRAXA = "Atraxa, Praetors' Voice"
KENRITH = "Kenrith, the Returned King"


def seat_2_s_turn(step: Step = Step.END, *, third_out: bool = True) -> Situation:
    """Seat 2's own turn 3 (table turn 8, round 3) of three seats; seat 3 is out unless told."""
    builder: Any = (
        a_game()
        .in_step(step, turn=8)
        .in_round(3)
        .in_turn_of(2)
        .with_turns_taken(3)
        .with_commander(ATRAXA)
        .with_library("Forest")
    )
    builder = (
        builder.and_an_opposing_seat()
        .with_turns_taken(3)
        .with_life(33)
        .with_commander(KENRITH)
        .with_commander_damage(KENRITH, 1, 6)
        .with_hand("Island")
        .with_battlefield("Forest", tapped=True)
        .with_graveyard("Grizzly Bears")
        .with_library("Forest")
    )
    builder = (
        builder.and_an_opposing_seat().with_turns_taken(2).with_life(12).with_library("Plains")
    )
    if third_out:
        builder = builder.eliminated()
    return builder.build()


def into_cleanup(situation: Situation) -> Any:
    result = acted(situation, advance(situation.game, situation.deck, S2, to="cleanup"))
    (snapshot,) = result.snapshots
    return snapshot


# @spec REC-045, REC-049
@NOT_BUILT
def test_entering_cleanup_of_another_seat_s_turn_writes_a_snapshot_of_that_seat() -> None:
    situation = seat_2_s_turn()
    exported = snapshot_to_data(into_cleanup(situation))
    assert exported["turn"] == 3
    assert [card["name"] for card in exported["hand"]] == ["Island"]
    assert exported["battlefield"] == [{"name": "Forest", "tapped": True, "counters": {}}]
    assert exported["graveyard"] == ["Grizzly Bears"]
    assert (exported["lands"], exported["life"]) == (1, 33)


# @spec REC-046
@NOT_BUILT
def test_a_contested_snapshot_records_the_seat_the_table_turn_the_round_and_every_life() -> None:
    situation = seat_2_s_turn()
    exported = snapshot_to_data(into_cleanup(situation))
    assert (exported["seat"], exported["table_turn"], exported["round"]) == (2, 8, 3)
    assert exported["lives"] == {"1": 40, "2": 33, "3": 12}
    assert exported["eliminated"] == [3]


# @spec REC-047, REC-079
@NOT_BUILT
def test_a_contested_snapshot_s_commander_damage_has_an_entry_for_every_other_seat() -> None:
    situation = seat_2_s_turn()
    exported = snapshot_to_data(into_cleanup(situation))
    assert exported["commander_damage"] == {KENRITH: {"1": 6, "3": 0}}
    assert "damage_dealt" not in exported


# @spec REC-048
def test_a_contested_game_writes_at_most_one_snapshot_per_table_turn() -> None:
    situation = seat_2_s_turn()
    into_cleanup(situation)
    assert take_snapshot(situation.game, situation.deck) is None


# @spec REC-048
@NOT_BUILT
def test_two_seats_own_turns_of_the_same_number_each_get_their_snapshot() -> None:
    builder: Any = a_game().in_step(Step.END, turn=1).in_round(1).with_turns_taken(1)
    builder = builder.with_library("Forest", "Forest").and_an_opposing_seat().with_turns_taken(0)
    situation = builder.with_library("Forest", "Forest").build()
    first = acted(situation, advance(situation.game, situation.deck, S1, to="cleanup"))
    acted(situation, advance(situation.game, situation.deck, S1))
    second = acted(situation, advance(situation.game, situation.deck, S2, to="cleanup"))
    (one,), (two,) = first.snapshots, second.snapshots
    assert [(s.turn, s.contested.table_turn) for s in (one, two)] == [(1, 1), (1, 2)]


# @spec REC-069
@NOT_BUILT
def test_a_contested_snapshot_lists_every_seat_s_unanswered_reminders_of_its_table_turn() -> None:
    situation = seat_2_s_turn(third_out=False)
    reminder: Any = Reminder
    situation.game.seat(S2).reminders.append(
        reminder("c90", "Phyrexian Arena", Step.UPKEEP, turn=8)
    )
    situation.game.seat(S3).reminders.append(reminder("c91", "Rhystic Study", Step.UPKEEP, turn=8))
    situation.game.seat(S1).reminders.append(reminder("c92", "Sylvan Library", Step.DRAW, turn=7))
    exported = snapshot_to_data(into_cleanup(situation))
    assert exported["unanswered_reminders"] == [
        {"card": "Phyrexian Arena", "step": "upkeep", "seat": 2},
        {"card": "Rhystic Study", "step": "upkeep", "seat": 3},
    ]


# @spec REC-050
@NOT_BUILT
def test_the_tested_seat_ending_the_game_in_another_seat_s_turn_snapshots_that_seat() -> None:
    situation = seat_2_s_turn(Step.MAIN1)
    result = acted(situation, end_game(situation.game, situation.deck, S1, result="win"))
    (snapshot,) = result.snapshots
    assert (snapshot.contested.seat, snapshot.turn, snapshot.life) == (S2, 3, 33)


# @spec REC-064, REC-071
@NOT_BUILT
def test_a_turn_ended_by_its_active_seat_s_elimination_snapshots_that_seat_as_it_left() -> None:
    situation = seat_2_s_turn(Step.MAIN1, third_out=False)
    result = acted(
        situation,
        effect(situation.game, situation.deck, S2, source="x", delta={"life": -33}),
    )
    (snapshot,) = result.snapshots
    exported = snapshot_to_data(snapshot)
    assert (exported["seat"], exported["table_turn"], exported["life"]) == (2, 8, 0)
    assert (exported["hand"], exported["battlefield"], exported["graveyard"]) == ([], [], [])
    assert exported["lands"] == 0
    assert situation.game.active == S3


# @spec REC-064
@NOT_BUILT
def test_a_conceding_active_seat_s_turn_gets_its_snapshot_when_the_turn_ends() -> None:
    situation = seat_2_s_turn(Step.MAIN1, third_out=False)
    result = acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))
    (snapshot,) = result.snapshots
    assert (snapshot.contested.seat, snapshot.life) == (S2, 33)
