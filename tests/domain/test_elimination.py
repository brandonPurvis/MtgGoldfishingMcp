"""Elimination in a contested game: at 0 life, at 21 combat damage from one commander, and by
conceding; what becomes of the cards and choices of an eliminated seat, its turn, the
notices, and the tested seat's end of the game."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import GameStatus, Zone
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaPool, ManaString
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted, events_named
from tests.support.builders import Situation, a_game

ATRAXA = "Atraxa, Praetors' Voice"
DISCARD = "discard a card"


def a_table(seats: int = 3, *, active: int = 1) -> Situation:
    """Seat `active`'s turn in its first main step; every seat holds an Island and has a
    Forest on its battlefield and in its library."""
    builder: Any = a_game().in_turn_of(active)
    for number in range(1, seats + 1):
        if number > 1:
            builder = builder.and_an_opposing_seat()
        builder = builder.with_hand("Island").with_battlefield("Forest").with_library("Forest")
    return builder.build()


def recorded(situation: Situation, delta: object, seat: SeatNumber = S1) -> Any:
    result = effect(
        situation.game, situation.deck, seat, source="a test effect", delta=delta, immediate=True
    )
    return acted(situation, result)


def conceded(situation: Situation, seat: SeatNumber, notes: str = "beaten") -> Any:
    return acted(
        situation, end_game(situation.game, situation.deck, seat, result="loss", notes=notes)
    )


def eliminated(situation: Situation) -> list[SeatNumber]:
    return [seat.number for seat in situation.game.seats if seat.eliminated]


def causes(result: Any) -> list[tuple[SeatNumber, str]]:
    return [(e.seat, e.cause.value) for e in events_named(result, "SeatEliminated")]


# ------------------------------------------------------------------ when a seat is eliminated


# @spec GAME-129, GAME-128, GAME-138
def test_a_seat_at_0_life_once_a_delta_is_applied_is_eliminated() -> None:
    situation = a_table()
    result = recorded(situation, {"damage": {"2": 40}})
    assert eliminated(situation) == [S2]
    assert causes(result) == [(S2, "life")]


# @spec GAME-160
def test_a_seat_at_0_life_partway_through_a_delta_and_above_it_at_the_end_stays_in() -> None:
    situation = a_table()
    recorded(situation, {"life": {"2": -40}, "damage": {"2": -3}})
    assert situation.game.seat(S2).life == 3
    assert eliminated(situation) == []


# @spec GAME-130
def test_a_seat_dealt_21_combat_damage_by_one_commander_is_eliminated() -> None:
    builder: Any = a_game().with_commander(ATRAXA, zone=Zone.BATTLEFIELD)
    situation = builder.with_commander_damage(ATRAXA, 2, 18).and_an_opposing_seat().build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=[ATRAXA]))
    result = acted(situation, advance(situation.game, situation.deck, S1, to="combat_damage"))
    assert situation.game.seat(S2).life == 36
    assert causes(result) == [(S2, "commander_damage")]


# @spec GAME-169
def test_a_seat_out_by_life_and_commander_damage_at_once_is_out_for_life() -> None:
    builder: Any = a_game().with_commander(ATRAXA, zone=Zone.BATTLEFIELD)
    builder = builder.with_commander_damage(ATRAXA, 2, 18).and_an_opposing_seat().with_life(3)
    situation = builder.build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=[ATRAXA]))
    result = acted(situation, advance(situation.game, situation.deck, S1, to="combat_damage"))
    assert causes(result) == [(S2, "life")]


# @spec GAME-128
def test_elimination_is_checked_once_an_ask_answer_s_delta_is_applied() -> None:
    situation = a_table()
    recorded(situation, {"ask": [{"seats": [2], "text": "deal 40 damage to a player"}]})
    choice = situation.game.pending[0].choice_id
    result = acted(
        situation,
        choose(  # type: ignore[call-arg]
            situation.game, situation.deck, S2, choice_id=choice, delta={"damage": {"3": 40}}
        ),
    )
    assert causes(result) == [(S3, "life")]


# @spec GAME-139
def test_seats_out_at_one_check_are_eliminated_in_turn_order_from_the_active_seat() -> None:
    situation = a_table(active=2)
    result = recorded(situation, {"damage": {"1": 40, "3": 40}}, S2)
    assert causes(result) == [(S3, "life"), (S1, "life")]


# @spec GAME-141
def test_drawing_from_a_library_with_too_few_cards_eliminates_no_one() -> None:
    situation = a_table(2)
    recorded(situation, {"draw": 3})
    assert eliminated(situation) == []


# ------------------------------------------------------------------ conceding


# @spec GAME-131
def test_an_opposing_seat_s_end_game_concedes_and_the_game_goes_on() -> None:
    situation = a_table()
    result = conceded(situation, S2, "outclassed")
    assert eliminated(situation) == [S2]
    assert (situation.game.status, situation.game.result) == (GameStatus.ACTIVE, None)
    (gone,) = events_named(result, "SeatEliminated")
    assert (gone.seat, gone.cause.value, gone.notes) == (S2, "concede", "outclassed")


# @spec GAME-161
def test_a_seat_concedes_while_the_game_waits_on_its_own_pending_choice() -> None:
    situation = a_table()
    recorded(situation, {"ask": [{"seats": [2], "text": DISCARD}]})
    assert acting.may_call(situation.game, S2, "end_game") is None
    conceded(situation, S2)
    assert eliminated(situation) == [S2]


# @spec GAME-161
def test_a_seat_that_is_not_the_seat_to_act_may_concede() -> None:
    assert acting.may_call(a_table().game, S3, "end_game") is None


# @spec GAME-158
def test_an_opposing_seat_may_concede_during_mulligans_whether_or_not_it_has_kept() -> None:
    builder: Any = a_game().in_mulligan().with_library("Forest").having_kept(False)
    builder = builder.and_an_opposing_seat().having_kept(False)
    situation = builder.and_an_opposing_seat().having_kept(True).build()
    conceded(situation, S2)
    conceded(situation, S3)
    assert eliminated(situation) == [S2, S3]
    assert situation.game.status is GameStatus.MULLIGAN


# @spec GAME-159
def test_a_concession_that_leaves_every_seat_kept_starts_the_game() -> None:
    builder: Any = a_game().in_mulligan().with_library("Forest", "Forest").having_kept(True)
    situation = builder.and_an_opposing_seat().with_library("Island").having_kept(False).build()
    conceded(situation, S2)
    game = situation.game
    assert (game.status, game.active, game.step) == (GameStatus.ACTIVE, S1, Step.MAIN1)


# @spec GAME-102
def test_the_last_keep_still_starts_a_game_after_a_concession() -> None:
    builder: Any = a_game().in_mulligan().with_library("Forest", "Forest").having_kept(False)
    situation = builder.and_an_opposing_seat().eliminated().having_kept(False).build()
    acted(situation, mulligan(situation.game, situation.deck, S1, keep=True))
    assert situation.game.status is GameStatus.ACTIVE


# ------------------------------------------------------------------ what leaves with the seat


# @spec GAME-132
def test_every_card_an_eliminated_seat_owns_leaves_the_game_from_every_zone() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    builder = builder.with_hand("Island").with_library("Swamp").with_graveyard("Lightning Bolt")
    situation = (
        builder.with_battlefield("Llanowar Elves").controlled_by("Llanowar Elves", 1).build()
    )
    recorded(situation, {"damage": {"2": 40}})
    assert [c for c in situation.game.cards if c.owner == S2] == []
    assert situation.game.seat(S2).library == []
    assert situation.names_in(Zone.BATTLEFIELD, S1) == ["Grizzly Bears"]


# @spec GAME-133, PLAY-094
def test_a_permanent_the_eliminated_seat_controlled_returns_to_its_owner() -> None:
    builder: Any = a_game().with_battlefield("Sol Ring").controlled_by("Sol Ring", 2)
    situation = builder.and_an_opposing_seat().build()
    recorded(situation, {"damage": {"2": 40}})
    ring = next(c for c in situation.game.cards if c.name == "Sol Ring")
    assert (ring.zone, ring.controller) == (Zone.BATTLEFIELD, S1)


# @spec GAME-135
def test_the_pending_choices_addressed_to_an_eliminated_seat_are_discarded() -> None:
    situation = a_table()
    recorded(situation, {"ask": [{"seats": [2, 3], "text": DISCARD}]})
    conceded(situation, S2)
    assert [(c.kind, c.seat) for c in situation.game.pending] == [("ask", S3)]


# @spec GAME-162
def test_an_ask_the_eliminated_seat_s_effect_made_still_waits_for_its_answer() -> None:
    situation = a_table(active=2)
    recorded(situation, {"ask": [{"seats": [3], "text": DISCARD}]}, S2)
    conceded(situation, S2)
    assert [(c.kind, c.seat, c.asked_by) for c in situation.game.pending] == [("ask", S3, S2)]


# @spec GAME-163
def test_a_look_at_the_eliminated_seat_s_hand_is_discarded() -> None:
    situation = a_table()
    recorded(situation, {"look_at_hand": 2})
    conceded(situation, S2)
    assert situation.game.pending == []
    assert situation.game.status is GameStatus.ACTIVE


# ------------------------------------------------------------------ the eliminated seat's turn


# @spec GAME-136, TURN-038
def test_when_the_active_seat_is_eliminated_the_next_seat_still_in_begins_its_turn() -> None:
    situation = a_table(active=2)
    situation.game.seat(S1).mana_pool = ManaPool().add(ManaString.parse("{G}"))
    conceded(situation, S2)
    game = situation.game
    assert (game.active, game.step) == (S3, Step.MAIN1)
    assert str(game.seat(S1).mana_pool) == "{}"


# @spec TURN-036
def test_an_eliminated_active_seat_s_attack_and_the_blocks_it_asked_for_are_discarded() -> None:
    builder: Any = a_game().with_battlefield("Llanowar Elves").in_turn_of(2)
    builder = builder.and_an_opposing_seat().with_battlefield("Grizzly Bears")
    situation = builder.and_an_opposing_seat().build()
    declared = attack(situation.game, situation.deck, S2, attackers=["Grizzly Bears"], targets=1)  # type: ignore[call-arg]
    acted(situation, declared)
    acted(situation, advance(situation.game, situation.deck, S2, to="declare_blockers"))
    assert [c.kind for c in situation.game.pending] == ["blocks"]
    conceded(situation, S2)
    assert situation.game.pending == []
    assert situation.game.declared_attack is None
    assert situation.game.active == S3


# @spec TURN-037
def test_the_next_turn_waits_for_the_choices_an_eliminated_active_seat_left() -> None:
    situation = a_table(active=2)
    recorded(situation, {"ask": [{"seats": [3], "text": DISCARD}]}, S2)
    conceded(situation, S2)
    assert situation.game.active == S2
    choice = situation.game.pending[0].choice_id
    acted(situation, choose(situation.game, situation.deck, S3, choice_id=choice, delta={}))  # type: ignore[call-arg]
    assert (situation.game.active, situation.game.step) == (S3, Step.MAIN1)


# @spec GAME-136, TURN-031
def test_an_eliminated_seat_takes_no_more_turns() -> None:
    builder: Any = a_game().in_step(Step.CLEANUP).with_library("Forest")
    builder = builder.and_an_opposing_seat().eliminated().and_an_opposing_seat()
    situation = builder.with_library("Forest").build()
    acted(situation, advance(situation.game, situation.deck, S1))
    assert situation.game.active == S3


# @spec GAME-164, TURN-062
def test_with_every_seat_eliminated_no_turn_begins_and_no_seat_is_to_act() -> None:
    situation = a_table(2)
    recorded(situation, {"life": {"1": -40, "2": -40}})
    game = situation.game
    assert eliminated(situation) == [S1, S2]
    assert (game.active, acting.seats_to_act(game), game.status) == (None, None, GameStatus.ACTIVE)


# @spec GAME-167, GAME-149
def test_with_every_seat_eliminated_only_reads_and_the_tested_seat_s_end_game_are_taken() -> None:
    situation = a_table(2)
    recorded(situation, {"life": {"1": -40, "2": -40}})
    assert acting.may_call(situation.game, S1, "advance") is not None
    assert acting.may_call(situation.game, S2, "end_game") is not None
    assert acting.may_call(situation.game, S1, "get_state") is None
    assert acting.may_call(situation.game, S1, "end_game") is None
    acted(situation, end_game(situation.game, situation.deck, S1, result="loss"))
    assert situation.game.status is GameStatus.ENDED


# ------------------------------------------------------------------ notices


# @spec GAME-142
def test_the_tested_seat_s_elimination_raises_its_notice() -> None:
    situation = a_table()
    recorded(situation, {"life": -40})
    assert [notice.value for notice in situation.game.notices] == ["tested_seat_eliminated"]


# @spec GAME-143
def test_the_elimination_of_every_opposing_seat_raises_its_notice() -> None:
    situation = a_table()
    recorded(situation, {"damage": {"2": 40}})
    assert situation.game.notices == []
    conceded(situation, S3)
    assert [notice.value for notice in situation.game.notices] == ["opponents_eliminated"]


# @spec GAME-146
def test_a_contested_game_raises_no_goldfish_life_notice() -> None:
    situation = a_table()
    recorded(situation, {"life": {"2": -45}})
    assert "life" not in [notice.value for notice in situation.game.notices]


# ------------------------------------------------------------------ the tested seat ends the game


# @spec GAME-148, GAME-045
def test_the_tested_seat_ends_the_game_while_it_waits_on_another_seat_s_choice() -> None:
    situation = a_table()
    recorded(situation, {"ask": [{"seats": [2], "text": DISCARD}]})
    assert acting.may_call(situation.game, S1, "end_game") is None
    acted(situation, end_game(situation.game, situation.deck, S1, result="win"))
    assert (situation.game.status, situation.game.pending) == (GameStatus.ENDED, [])


# @spec GAME-148
def test_the_tested_seat_ends_the_game_during_mulligans() -> None:
    builder: Any = a_game().in_mulligan().having_kept(True)
    situation = builder.and_an_opposing_seat().having_kept(False).build()
    assert acting.may_call(situation.game, S1, "end_game") is None
    acted(situation, end_game(situation.game, situation.deck, S1, result="stalled"))
    assert situation.game.status is GameStatus.ENDED


# @spec GAME-149
def test_an_eliminated_tested_seat_may_still_end_the_game() -> None:
    situation = a_table()
    recorded(situation, {"life": -40})
    assert situation.game.seat(S1).eliminated
    assert acting.may_call(situation.game, S1, "end_game") is None
    acted(situation, end_game(situation.game, situation.deck, S1, result="loss"))
    assert situation.game.status is GameStatus.ENDED
