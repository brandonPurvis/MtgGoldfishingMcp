"""Combat in a contested game: each attacker attacks a seat, attacked seats declare blockers
through pending choices, and the service deals combat damage to seats and keeps commander
damage per commander per seat."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.stack.passing import pass_
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted, check_kinds, error_kinds, events_named
from tests.support.builders import Situation, a_game

ATRAXA = "Atraxa, Praetors' Voice"


def a_table(
    seats: int = 2,
    *,
    attackers: tuple[str, ...] = ("Grizzly Bears", "Shivan Dragon"),
    blockers: tuple[str, ...] = ("Llanowar Elves",),
    tapped_blockers: bool = False,
    step: Step = Step.MAIN1,
) -> Situation:
    """Seat 1's turn: it controls `attackers`, every other seat controls `blockers`."""
    builder: Any = a_game().in_step(step).with_battlefield(*attackers)
    for _ in range(seats - 1):
        builder = builder.and_an_opposing_seat()
        if blockers:
            builder = builder.with_battlefield(*blockers, tapped=tapped_blockers)
    return builder.build()


def attacking(situation: Situation, seat: SeatNumber = S1, **arguments: object) -> Any:
    return attack(situation.game, situation.deck, seat, **arguments)  # type: ignore[arg-type]


def advanced(situation: Situation, to: str, seat: SeatNumber = S1) -> Applied:
    return acted(situation, advance(situation.game, situation.deck, seat, to=to))


def blocking(situation: Situation, seat: SeatNumber, blocks: object, **more: object) -> Any:
    choice = situation.game.pending[0].choice_id
    return choose(
        situation.game,
        situation.deck,
        seat,
        choice_id=choice,
        blocks=blocks,  # type: ignore[call-arg]
        **more,  # type: ignore[arg-type]
    )


def recorded(situation: Situation, delta: object, seat: SeatNumber = S1, **more: object) -> Any:
    result = effect(
        situation.game,
        situation.deck,
        seat,
        source="a test effect",
        delta=delta,
        **{"immediate": True, **more},  # type: ignore[arg-type]
    )
    return acted(situation, result)


def card_of(situation: Situation, name: str, controller: SeatNumber) -> Any:
    return next(c for c in situation.game.cards if c.name == name and c.controller == controller)


def target_of(situation: Situation, name: str) -> int:
    attack_ = situation.game.declared_attack
    assert attack_ is not None
    return int(attack_.targets[card_of(situation, name, S1).id])


# ------------------------------------------------------------------ who may attack


# @spec CMBT-028
def test_a_seat_that_is_not_the_active_seat_may_not_attack() -> None:
    error = acting.may_call(a_table().game, S2, "attack")
    assert error is not None
    assert error.kind.value == "not_your_call"


# ------------------------------------------------------------------ targets


# @spec CMBT-030
def test_one_seat_number_as_targets_sends_every_attacker_at_that_seat() -> None:
    situation = a_table(3)
    acted(situation, attacking(situation, attackers=["Grizzly Bears", "Shivan Dragon"], targets=3))
    assert (target_of(situation, "Grizzly Bears"), target_of(situation, "Shivan Dragon")) == (3, 3)


# @spec CMBT-031
def test_targets_as_a_map_sends_each_attacker_at_its_own_seat() -> None:
    situation = a_table(3)
    targets = {"Grizzly Bears": 2, "Shivan Dragon": 3}
    result = acted(
        situation,
        attacking(situation, attackers=["Grizzly Bears", "Shivan Dragon"], targets=targets),
    )
    assert (target_of(situation, "Grizzly Bears"), target_of(situation, "Shivan Dragon")) == (2, 3)
    assert dict(result.summary.targets) == {"Grizzly Bears": S2, "Shivan Dragon": S3}


# @spec CMBT-032
def test_with_one_opponent_left_an_attacker_without_a_target_attacks_it() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    situation = builder.and_an_opposing_seat().eliminated().build()
    acted(situation, attacking(situation, attackers=["Grizzly Bears"]))
    assert target_of(situation, "Grizzly Bears") == 2


# @spec CMBT-059
def test_an_attacker_without_a_target_while_several_opponents_remain_is_an_error() -> None:
    situation = a_table(3)
    result = attacking(
        situation, attackers=["Grizzly Bears", "Shivan Dragon"], targets={"Grizzly Bears": 2}
    )
    assert error_kinds(result) == ["no_target"]


# @spec CMBT-076
def test_attacking_with_no_opponent_left_is_an_error() -> None:
    situation = (
        a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat().eliminated().build()
    )
    assert error_kinds(attacking(situation, attackers=["Grizzly Bears"])) == ["no_opponent_left"]


# @spec CMBT-058
@pytest.mark.parametrize(
    ("target", "kind"), [(1, "target_is_you"), (5, "no_such_seat"), (3, "seat_out")]
)
def test_a_target_that_is_the_attacker_itself_absent_or_eliminated_is_an_error(
    target: int, kind: str
) -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    situation = builder.and_an_opposing_seat().eliminated().build()
    result = attacking(situation, attackers=["Grizzly Bears"], targets=target)
    assert error_kinds(result) == [kind]


# @spec CMBT-057
def test_a_target_for_something_that_is_not_an_attacker_is_an_error() -> None:
    situation = a_table()
    result = attacking(situation, attackers=["Grizzly Bears"], targets={"Shivan Dragon": 2})
    assert error_kinds(result) == ["not_an_attacker"]


# @spec CMBT-054
def test_blocked_is_not_given_in_a_contested_game() -> None:
    result = attacking(a_table(), attackers=["Grizzly Bears"], blocked=["Grizzly Bears"])
    assert error_kinds(result) == ["goldfish_only"]


# @spec CMBT-055
def test_commander_target_is_not_given_in_a_contested_game() -> None:
    result = attacking(a_table(), attackers=["Grizzly Bears"], commander_target=1)
    assert error_kinds(result) == ["goldfish_only"]


# @spec CMBT-056
def test_targets_are_not_given_in_a_goldfish_game() -> None:
    situation = a_game().with_battlefield("Grizzly Bears").build()
    assert error_kinds(attacking(situation, attackers=["Grizzly Bears"], targets=2)) == [
        "contested_only"
    ]


# @spec CMBT-068
def test_attacking_with_another_seat_s_creature_is_an_error() -> None:
    situation = a_table(attackers=("Grizzly Bears",), blockers=("Shivan Dragon",))
    assert error_kinds(attacking(situation, attackers=["Shivan Dragon"])) == ["not_your_attacker"]


# @spec CMBT-053
def test_an_attacker_in_another_seat_s_hand_is_reported_as_in_a_hidden_zone() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    situation = builder.with_hand("Shivan Dragon").build()
    dragon = next(c.id for c in situation.game.cards if c.name == "Shivan Dragon")
    (error,) = attacking(situation, attackers=[dragon]).errors
    assert (error.kind.value, error.number) == ("hidden_zone", 2)


# @spec CMBT-053
def test_an_attacker_in_the_attacking_seat_s_graveyard_is_said_to_be_there() -> None:
    builder: Any = a_game().with_graveyard("Grizzly Bears").and_an_opposing_seat()
    situation = builder.build()
    (error,) = attacking(situation, attackers=["Grizzly Bears"]).errors
    assert (error.kind.value, error.found_in) == ("attacker_not_on_battlefield", "graveyard")


# @spec CMBT-060
def test_a_contested_attacker_with_no_numeric_power_needs_a_damage_entry() -> None:
    situation = a_table(attackers=("Tarmogoyf",))
    assert check_kinds(attacking(situation, attackers=["Tarmogoyf"])) == ["power_not_a_number"]


# ------------------------------------------------------------------ one declaration per combat


# @spec CMBT-069
def test_a_second_attack_in_one_combat_is_an_error() -> None:
    situation = a_table()
    acted(situation, attacking(situation, attackers=["Grizzly Bears"]))
    assert error_kinds(attacking(situation, attackers=["Shivan Dragon"])) == ["attack_declared"]


# @spec CMBT-070
def test_after_an_empty_attack_a_later_attack_is_the_combat_s_first() -> None:
    situation = a_table()
    acted(situation, attacking(situation, attackers=[]))
    acted(situation, attacking(situation, attackers=["Grizzly Bears"]))
    assert target_of(situation, "Grizzly Bears") == 2


# @spec CMBT-071
def test_an_additional_combat_takes_its_own_declaration() -> None:
    situation = a_table(blockers=())
    acted(situation, attacking(situation, attackers=["Grizzly Bears"]))
    advanced(situation, "main2")
    acted(
        situation,
        attacking(situation, attackers=["Shivan Dragon"], override="an extra combat card"),
    )
    assert target_of(situation, "Shivan Dragon") == 2


# @spec CMBT-072
def test_attacking_in_declare_blockers_is_an_error() -> None:
    situation = a_table(step=Step.DECLARE_BLOCKERS)
    assert error_kinds(attacking(situation, attackers=["Grizzly Bears"])) == [
        "attack_after_blockers"
    ]


# ------------------------------------------------------------------ blocks


def attacked(situation: Situation, **arguments: object) -> Situation:
    """The attack is declared, and every seat its window asks passes."""
    acted(situation, attacking(situation, **arguments))
    while situation.game.window is not None and situation.game.window.asking is not None:
        acted(situation, pass_(situation.game, situation.deck, situation.game.window.asking))
    return situation


# @spec CMBT-037, CMBT-047
def test_entering_declare_blockers_asks_each_attacked_seat_with_an_untapped_creature() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears", "Shivan Dragon")
    builder = builder.and_an_opposing_seat().with_battlefield("Llanowar Elves", tapped=True)
    builder = builder.and_an_opposing_seat().with_battlefield("Llanowar Elves")
    situation = attacked(
        builder.build(),
        attackers=["Grizzly Bears", "Shivan Dragon"],
        targets={"Grizzly Bears": 2, "Shivan Dragon": 3},
    )
    result = advanced(situation, "declare_blockers")
    assert [(c.kind, c.seat) for c in situation.game.pending] == [("blocks", S3)]
    assert [e.seat for e in events_named(result, "NoBlocksDeclared")] == [S2]


# @spec CMBT-037
def test_blocks_choices_are_created_in_turn_order_from_the_seat_after_the_active_seat() -> None:
    situation = attacked(
        a_table(3),
        attackers=["Grizzly Bears", "Shivan Dragon"],
        targets={"Grizzly Bears": 3, "Shivan Dragon": 2},
    )
    advanced(situation, "declare_blockers")
    assert [c.seat for c in situation.game.pending] == [S2, S3]


# @spec CMBT-049
def test_a_blocks_choice_shows_only_the_attackers_attacking_that_seat() -> None:
    situation = attacked(
        a_table(3),
        attackers=["Grizzly Bears", "Shivan Dragon"],
        targets={"Grizzly Bears": 3, "Shivan Dragon": 2},
    )
    advanced(situation, "declare_blockers")
    dragon = card_of(situation, "Shivan Dragon", S1).id
    bears = card_of(situation, "Grizzly Bears", S1).id
    assert [c.attackers for c in situation.game.pending] == [[dragon], [bears]]


# @spec CMBT-038
def test_an_advance_stops_in_declare_blockers_when_blocks_are_asked_for() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears"])
    advanced(situation, "combat_damage")
    assert situation.game.step is Step.DECLARE_BLOCKERS


# @spec CMBT-039, CMBT-048
def test_an_attacker_named_in_a_blocks_answer_is_blocked_and_the_active_seat_acts_again() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears", "Shivan Dragon"])
    advanced(situation, "declare_blockers")
    result = acted(situation, blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"}))
    attack_ = situation.game.declared_attack
    assert attack_ is not None
    assert attack_.blocked == [card_of(situation, "Shivan Dragon", S1).id]
    assert [(b.blocker, b.attacker) for b in result.summary.blocks] == [
        ("Llanowar Elves", "Shivan Dragon")
    ]
    waiting = acting.seats_to_act(situation.game)
    assert waiting is not None
    assert (waiting.seats, waiting.kind.value) == ((S1,), "turn")


# @spec CMBT-040
def test_several_blockers_may_block_one_attacker() -> None:
    situation = attacked(
        a_table(blockers=("Llanowar Elves", "Grizzly Bears")), attackers=["Shivan Dragon"]
    )
    advanced(situation, "declare_blockers")
    blocks = {"Llanowar Elves": "Shivan Dragon", "Grizzly Bears": "Shivan Dragon"}
    acted(situation, blocking(situation, S2, blocks))
    assert situation.game.declared_attack.blocked == [card_of(situation, "Shivan Dragon", S1).id]


# @spec CMBT-041
def test_an_empty_blocks_answer_declares_no_blocks() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears"])
    advanced(situation, "declare_blockers")
    acted(situation, blocking(situation, S2, {}))
    assert situation.game.declared_attack.blocked == []
    assert situation.game.pending == []


# @spec CMBT-042
def test_a_blocker_the_answering_seat_does_not_control_is_an_error() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears"])
    advanced(situation, "declare_blockers")
    result = blocking(situation, S2, {"Shivan Dragon": "Grizzly Bears"})
    assert error_kinds(result) == ["not_your_blocker"]


# @spec CMBT-043
def test_blocking_an_attacker_that_is_not_attacking_the_answering_seat_is_an_error() -> None:
    situation = attacked(
        a_table(3),
        attackers=["Grizzly Bears", "Shivan Dragon"],
        targets={"Grizzly Bears": 2, "Shivan Dragon": 3},
    )
    advanced(situation, "declare_blockers")
    result = blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"})
    assert error_kinds(result) == ["not_attacking_you"]


# @spec CMBT-044
def test_naming_one_blocker_twice_is_an_error() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears", "Shivan Dragon"])
    advanced(situation, "declare_blockers")
    elves = card_of(situation, "Llanowar Elves", S2).id
    result = blocking(situation, S2, {elves: "Grizzly Bears", "Llanowar Elves": "Shivan Dragon"})
    assert error_kinds(result)
    assert len(situation.game.pending) == 1


# @spec CMBT-045
def test_a_tapped_blocker_fails_a_rule_check_that_override_passes() -> None:
    situation = attacked(
        a_table(blockers=("Llanowar Elves", "Grizzly Bears")), attackers=["Shivan Dragon"]
    )
    card_of(situation, "Grizzly Bears", S2).tapped = True
    advanced(situation, "declare_blockers")
    blocks = {"Grizzly Bears": "Shivan Dragon"}
    assert check_kinds(blocking(situation, S2, blocks)) == ["blocker_tapped"]
    acted(situation, blocking(situation, S2, blocks, override="it untapped in response"))
    assert situation.game.declared_attack.blocked == [card_of(situation, "Shivan Dragon", S1).id]


# @spec CMBT-046
def test_a_blocker_that_is_not_a_creature_fails_a_rule_check() -> None:
    situation = attacked(
        a_table(blockers=("Llanowar Elves", "Sol Ring")), attackers=["Grizzly Bears"]
    )
    advanced(situation, "declare_blockers")
    result = blocking(situation, S2, {"Sol Ring": "Grizzly Bears"})
    assert check_kinds(result) == ["blocker_not_a_creature"]


# ------------------------------------------------------------------ attackers that change


# @spec CMBT-034
def test_an_attacker_that_left_the_battlefield_is_removed_before_blocks() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears", "Shivan Dragon"])
    recorded(situation, {"move": {"graveyard": ["Grizzly Bears"]}})
    advanced(situation, "declare_blockers")
    dragon = card_of(situation, "Shivan Dragon", S1).id
    assert situation.game.declared_attack.attackers == [dragon]
    assert situation.game.pending[0].attackers == [dragon]


# @spec CMBT-035
def test_an_attacker_whose_controller_changed_is_removed_before_blocks() -> None:
    situation = attacked(a_table(), attackers=["Grizzly Bears", "Shivan Dragon"])
    recorded(situation, {"control": {"2": ["Grizzly Bears"]}})
    advanced(situation, "declare_blockers")
    dragon = card_of(situation, "Shivan Dragon", S1).id
    assert situation.game.declared_attack.attackers == [dragon]


# @spec CMBT-036
def test_an_attacker_whose_target_seat_was_eliminated_is_removed_before_blocks() -> None:
    situation = attacked(
        a_table(3),
        attackers=["Grizzly Bears", "Shivan Dragon"],
        targets={"Grizzly Bears": 2, "Shivan Dragon": 3},
    )
    recorded(situation, {"damage": {"3": 40}})
    advanced(situation, "declare_blockers")
    bears = card_of(situation, "Grizzly Bears", S1).id
    assert situation.game.declared_attack.attackers == [bears]
    assert [c.seat for c in situation.game.pending] == [S2]


# @spec CMBT-074
def test_an_attacker_whose_controller_changed_after_blocks_deals_no_damage() -> None:
    situation = attacked(a_table(blockers=()), attackers=["Grizzly Bears", "Shivan Dragon"])
    advanced(situation, "declare_blockers")
    recorded(situation, {"control": {"2": ["Shivan Dragon"]}})
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 38


# @spec CMBT-075
def test_an_attacker_whose_target_was_eliminated_after_blocks_deals_no_damage() -> None:
    situation = attacked(
        a_table(3, blockers=()),
        attackers=["Grizzly Bears", "Shivan Dragon"],
        targets={"Grizzly Bears": 2, "Shivan Dragon": 3},
    )
    advanced(situation, "declare_blockers")
    recorded(situation, {"damage": {"3": 40}})
    result = advanced(situation, "combat_damage")
    (dealt,) = events_named(result, "CombatDamageToSeats")
    assert [(hit.attacker, hit.seat) for hit in dealt.hits] == [("Grizzly Bears", S2)]
    assert situation.game.seat(S3).life == 0


# ------------------------------------------------------------------ combat damage


# @spec CMBT-061, CMBT-067
def test_an_unblocked_attacker_s_damage_comes_off_the_life_of_the_seat_it_attacks() -> None:
    situation = attacked(a_table(3, blockers=()), attackers=["Grizzly Bears"], targets=3)
    advanced(situation, "combat_damage")
    assert [seat.life for seat in situation.game.seats] == [40, 40, 38]
    assert situation.game.imaginary is None


# @spec CMBT-062
def test_an_attacking_commander_s_damage_counts_against_the_seat_it_attacks() -> None:
    builder: Any = a_game().with_commander(ATRAXA, zone=Zone.BATTLEFIELD)
    situation = builder.and_an_opposing_seat().and_an_opposing_seat().build()
    attacked(situation, attackers=[ATRAXA], targets=3, damage={ATRAXA: 6})
    advanced(situation, "combat_damage")
    atraxa = card_of(situation, ATRAXA, S1)
    assert situation.game.seat(S1).commander_damage == {atraxa.id: {"3": 6}}


# @spec CMBT-063
def test_a_blocked_attacker_deals_exactly_its_trample_damage_whatever_its_damage_entry() -> None:
    situation = attacked(a_table(), attackers=["Shivan Dragon"], damage={"Shivan Dragon": 6})
    advanced(situation, "declare_blockers")
    acted(situation, blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"}))
    acted(situation, attacking(situation, trample={"Shivan Dragon": 2}))
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 38


# @spec CMBT-064
def test_a_blocked_attacker_with_a_damage_entry_and_no_trample_damage_deals_nothing() -> None:
    situation = attacked(a_table(), attackers=["Shivan Dragon"], damage={"Shivan Dragon": 3})
    advanced(situation, "declare_blockers")
    acted(situation, blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"}))
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 40


# @spec CMBT-064, CMBT-050
def test_a_blocked_attacker_without_trample_damage_deals_nothing_and_nothing_dies() -> None:
    situation = attacked(a_table(), attackers=["Shivan Dragon"])
    advanced(situation, "declare_blockers")
    acted(situation, blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"}))
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 40
    assert card_of(situation, "Llanowar Elves", S2).zone is Zone.BATTLEFIELD
    assert card_of(situation, "Shivan Dragon", S1).zone is Zone.BATTLEFIELD


# @spec CMBT-077
def test_a_blocked_attacker_with_trample_damage_no_longer_on_the_battlefield_deals_nothing() -> (
    None
):
    situation = attacked(a_table(), attackers=["Shivan Dragon"], damage={"Shivan Dragon": 3})
    advanced(situation, "declare_blockers")
    acted(situation, blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"}))
    acted(situation, attacking(situation, trample={"Shivan Dragon": 3}))
    recorded(situation, {"move": {"graveyard": ["Shivan Dragon"]}}, immediate=True)
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 40


# @spec CMBT-051
def test_the_attacking_seat_states_the_result_of_combat_with_an_immediate_effect() -> None:
    situation = attacked(a_table(), attackers=["Shivan Dragon"])
    advanced(situation, "declare_blockers")
    acted(situation, blocking(situation, S2, {"Llanowar Elves": "Shivan Dragon"}))
    advanced(situation, "combat_damage")
    recorded(situation, {"move": {"graveyard": ["Llanowar Elves"]}, "life": 1}, immediate=True)
    assert situation.names_in(Zone.GRAVEYARD, S2) == ["Llanowar Elves"]
    assert situation.game.seat(S1).life == 41


# @spec CMBT-052
def test_combat_damage_is_dealt_in_full_whatever_an_earlier_effect_stated() -> None:
    situation = attacked(a_table(blockers=()), attackers=["Grizzly Bears"])
    advanced(situation, "declare_blockers")
    recorded(situation, {"damage": {"2": 2}}, immediate=True)
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 36


# @spec CMBT-065
def test_a_seat_brought_to_0_life_by_combat_damage_is_eliminated_within_the_call() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat().with_life(2)
    situation = attacked(
        builder.and_an_opposing_seat().build(), attackers=["Grizzly Bears"], targets=2
    )
    result = advanced(situation, "combat_damage")
    assert situation.game.seat(S2).eliminated
    assert [e.seat for e in events_named(result, "SeatEliminated")] == [S2]


# @spec CMBT-066
def test_the_combat_damage_outcome_gives_each_hit_and_each_damaged_seat_s_totals() -> None:
    builder: Any = (
        a_game().with_battlefield("Grizzly Bears").with_commander(ATRAXA, zone=Zone.BATTLEFIELD)
    )
    situation = builder.and_an_opposing_seat().and_an_opposing_seat().build()
    attacked(
        situation,
        attackers=["Grizzly Bears", ATRAXA],
        targets={"Grizzly Bears": 2, ATRAXA: 3},
    )
    result = advanced(situation, "combat_damage")
    (dealt,) = events_named(result, "CombatDamageToSeats")
    assert [(h.attacker, h.damage, h.seat) for h in dealt.hits] == [
        ("Grizzly Bears", 2, S2),
        (ATRAXA, 4, S3),
    ]
    assert [(s.seat, s.life, s.commander_damage) for s in dealt.seats] == [
        (S2, 38, ()),
        (S3, 36, ((ATRAXA, 4),)),
    ]
