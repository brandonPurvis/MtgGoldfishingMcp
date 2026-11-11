"""Trample damage in a contested game: once blocks are known, the attacking seat states with an
`attack` giving `trample` the combat damage each blocked attacker deals the seat it attacks; a
blocked attacker with none deals that seat nothing. And what `attack` needs: attackers or
trample damage, in either kind of game."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seeing import as_seen_by, public_form
from mtg_goldfishing.domain.steps import Step
from tests.support.acting import S1, S2, S3, acted, error_kinds, events_named
from tests.support.builders import Situation, a_game
from tests.support.combat import (
    a_duel,
    advanced,
    at_blocks,
    attacked,
    attacking,
    blocked,
    card_of,
    immediately,
    stating_trample,
)

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M1: not implemented yet")
ATRAXA = "Atraxa, Praetors' Voice"


def blocks_answered(
    attackers: tuple[str, ...] = ("Shivan Dragon",),
    blockers: tuple[str, ...] = ("Llanowar Elves",),
    blocks: dict[str, str] | None = None,
    seats: int = 2,
) -> Situation:
    """Seat 1 attacks with `attackers`; seat 2 answers its blocks choice with `blocks` (each
    blocker on the first attacker, unless given); the game is in declare blockers."""
    situation = at_blocks(
        a_duel(attackers=attackers, blockers=blockers, seats=seats),
        attackers=list(attackers),
        targets=2,
    )
    answer = blocks if blocks is not None else dict.fromkeys(blockers, attackers[0])
    blocked(situation, S2, answer)
    while situation.game.pending:
        blocked(situation, situation.game.pending[0].seat, {})
    return situation


def trample_of(situation: Situation, name: str) -> Any:
    attack_: Any = situation.game.declared_attack
    return attack_.trample.get(card_of(situation, name, S1).id)


# ------------------------------------------------------------------ stating trample damage


# @spec CMBT-098, CMBT-069, CMBT-072
@NOT_BUILT
def test_once_blocks_are_answered_the_active_seat_states_trample_damage_with_attack() -> None:
    situation = blocks_answered()
    acted(situation, stating_trample(situation, {"Shivan Dragon": 3}))
    assert trample_of(situation, "Shivan Dragon") == 3


# @spec CMBT-099
@NOT_BUILT
def test_a_later_statement_replaces_only_the_attackers_it_names() -> None:
    situation = blocks_answered(
        attackers=("Shivan Dragon", "Grizzly Bears"),
        blockers=("Llanowar Elves", "Birds of Paradise"),
        blocks={"Llanowar Elves": "Shivan Dragon", "Birds of Paradise": "Grizzly Bears"},
    )
    acted(situation, stating_trample(situation, {"Shivan Dragon": 3, "Grizzly Bears": 1}))
    acted(situation, stating_trample(situation, {"Shivan Dragon": 4}))
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 35


# @spec CMBT-099
@NOT_BUILT
def test_an_entry_of_zero_takes_an_earlier_statement_back() -> None:
    situation = blocks_answered()
    acted(situation, stating_trample(situation, {"Shivan Dragon": 3}))
    acted(situation, stating_trample(situation, {"Shivan Dragon": 0}))
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 40


# @spec CMBT-100
@NOT_BUILT
def test_a_trample_statement_taps_nothing_opens_no_window_and_moves_to_no_step() -> None:
    situation = blocks_answered()
    tapped_before = {card.id for card in situation.game.cards if card.tapped}
    acted(situation, stating_trample(situation, {"Shivan Dragon": 3}))
    asked = acting.seats_to_act(situation.game)
    assert asked is not None
    assert (
        {card.id for card in situation.game.cards if card.tapped},
        situation.game.window,
        situation.game.step,
        asked.seats,
        asked.kind.value,
    ) == (tapped_before, None, Step.DECLARE_BLOCKERS, (S1,), "turn")


# @spec CMBT-101
@NOT_BUILT
def test_the_outcome_lists_each_named_attacker_with_its_trample_damage_and_its_seat() -> None:
    situation = blocks_answered(seats=3)
    result = acted(situation, stating_trample(situation, {"Shivan Dragon": 3}))
    assert [(e.attacker, e.damage, e.seat) for e in result.summary.entries] == [
        ("Shivan Dragon", 3, S2)
    ]


# @spec CMBT-101
@NOT_BUILT
def test_the_trample_statement_is_shown_alike_to_every_seat() -> None:
    situation = blocks_answered(seats=3)
    result: Applied = acted(situation, stating_trample(situation, {"Shivan Dragon": 3}))
    reported = (result.summary, *result.events)
    assert as_seen_by(reported, S2) == as_seen_by(reported, S3) == public_form(reported)


# @spec CMBT-102
@NOT_BUILT
def test_trample_damage_beyond_the_attacker_s_power_is_accepted_without_a_rule_check() -> None:
    situation = blocks_answered(attackers=("Grizzly Bears",))
    result = acted(situation, stating_trample(situation, {"Grizzly Bears": 7}))
    assert events_named(result, "ChecksOverridden") == []
    assert trample_of(situation, "Grizzly Bears") == 7


# @spec CMBT-082
@NOT_BUILT
def test_an_attacker_whose_blockers_all_left_stays_blocked_and_deals_its_trample_damage() -> None:
    situation = blocks_answered()
    immediately(situation, {"move": {"graveyard": ["Llanowar Elves"]}})
    acted(situation, stating_trample(situation, {"Shivan Dragon": 5}))
    advanced(situation, "combat_damage")
    assert situation.game.seat(S2).life == 35


# ------------------------------------------------------------------ combat damage


# @spec CMBT-097
@NOT_BUILT
def test_a_blocked_commander_s_trample_damage_counts_as_commander_damage() -> None:
    builder: Any = a_game().with_commander(ATRAXA, zone=Zone.BATTLEFIELD)
    situation: Situation = builder.and_an_opposing_seat().with_battlefield("Llanowar Elves").build()
    at_blocks(situation, attackers=[ATRAXA])
    blocked(situation, S2, {"Llanowar Elves": ATRAXA})
    acted(situation, stating_trample(situation, {ATRAXA: 3}))
    advanced(situation, "combat_damage")
    atraxa = card_of(situation, ATRAXA, S1)
    assert situation.game.seat(S1).commander_damage == {atraxa.id: {"2": 3}}


# ------------------------------------------------------------------ errors


# @spec CMBT-103
@NOT_BUILT
def test_trample_is_not_given_in_a_goldfish_game() -> None:
    situation = a_game().in_step(Step.DECLARE_BLOCKERS).with_battlefield("Grizzly Bears").build()
    acted(situation, attacking(situation, attackers=["Grizzly Bears"], blocked=["Grizzly Bears"]))
    result = stating_trample(situation, {"Grizzly Bears": 1})
    assert error_kinds(result) == ["contested_only"]


# @spec CMBT-104
@NOT_BUILT
@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("attackers", ["Shivan Dragon"]),
        ("attackers", []),
        ("targets", 2),
        ("damage", {"Shivan Dragon": 3}),
        ("vigilance", ["Shivan Dragon"]),
        ("haste", ["Shivan Dragon"]),
        ("evasion", {"Shivan Dragon": "flying"}),
    ],
    ids=["attackers", "an empty attackers list", "targets", "damage", "vigilance", "haste", "ev"],
)
def test_trample_given_with_a_declaration_s_arguments_is_an_error(
    argument: str, value: object
) -> None:
    situation = blocks_answered()
    result = stating_trample(situation, {"Shivan Dragon": 3}, **{argument: value})
    assert error_kinds(result) == ["trample_alone"]


# @spec CMBT-105
@NOT_BUILT
def test_trample_before_blockers_are_declared_is_an_error() -> None:
    situation = attacked(a_duel(attackers=("Shivan Dragon",)), attackers=["Shivan Dragon"])
    assert situation.game.step is Step.DECLARE_ATTACKERS
    result = stating_trample(situation, {"Shivan Dragon": 3})
    assert error_kinds(result) == ["trample_not_now"]


# @spec CMBT-105
@NOT_BUILT
def test_trample_with_no_attack_declared_is_an_error() -> None:
    situation = a_duel(attackers=("Shivan Dragon",))
    acted(situation, attacking(situation, attackers=[]))
    advanced(situation, "declare_blockers")
    result = stating_trample(situation, {"Shivan Dragon": 3})
    assert error_kinds(result) == ["trample_not_now"]


# @spec CMBT-106
@NOT_BUILT
def test_trample_for_something_that_is_not_among_the_attackers_is_an_error() -> None:
    situation = blocks_answered()
    result = stating_trample(situation, {"Llanowar Elves": 3})
    assert error_kinds(result) == ["not_an_attacker"]


# @spec CMBT-107
@NOT_BUILT
def test_trample_for_an_attacker_that_is_not_blocked_is_an_error() -> None:
    situation = blocks_answered(blocks={})
    result = stating_trample(situation, {"Shivan Dragon": 3})
    assert error_kinds(result) == ["not_blocked"]


# @spec CMBT-108
@NOT_BUILT
@pytest.mark.parametrize(
    "amount", [-1, 1.5, "3", True], ids=["negative", "a fraction", "text", "a flag"]
)
def test_a_trample_amount_that_is_not_a_whole_number_of_zero_or_more_is_an_error(
    amount: object,
) -> None:
    situation = blocks_answered()
    result = stating_trample(situation, {"Shivan Dragon": amount})
    assert error_kinds(result) == ["malformed_argument"]


# @spec CMBT-096
@NOT_BUILT
@pytest.mark.parametrize("seats", [1, 2], ids=["goldfish", "contested"])
def test_an_attack_with_neither_attackers_nor_trample_is_an_error(seats: int) -> None:
    situation = a_duel(attackers=("Grizzly Bears",), seats=seats)
    assert error_kinds(attacking(situation)) == ["attackers_needed"]
