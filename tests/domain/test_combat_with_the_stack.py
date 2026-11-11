"""Combat in a contested game with the stack: the window after attackers are declared, an
attack that stops for another seat's reminder, an empty declaration, and the result of
combat between creatures stated with an immediate effect."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.steps import Step
from tests.support.acting import S1, S2, acted, events_named, passed, recorded
from tests.support.tables import two_seats


def attacked(situation: Any, attackers: list[str], **arguments: Any) -> Any:
    result = attack(situation.game, situation.deck, S1, attackers=attackers, **arguments)
    return acted(situation, result)


# @spec CMBT-073
def test_an_attack_stops_undeclared_where_another_seat_is_reminded_on_the_way() -> None:
    situation = two_seats(
        lambda b: b.with_battlefield("Grizzly Bears"),
        lambda b: b.with_battlefield("Banner of Each Combat"),
    )

    attacked(situation, ["Grizzly Bears"])

    assert situation.game.step is Step.BEGIN_COMBAT
    assert situation.game.declared_attack is None
    assert not any(c.tapped for c in situation.game.cards if c.name == "Grizzly Bears")
    found: Any = acting.seats_to_act(situation.game)
    assert (found.seats, found.kind.value) == ((S2,), "trigger")


# @spec CMBT-078
def test_an_attack_that_stops_undeclared_says_so() -> None:
    situation = two_seats(
        lambda b: b.with_battlefield("Grizzly Bears"),
        lambda b: b.with_battlefield("Banner of Each Combat"),
    )

    result = attacked(situation, ["Grizzly Bears"])

    assert type(result.summary).__name__ == "AttackNotDeclared"
    assert events_named(result, "AttackDeclared") == []


# @spec CMBT-073
def test_once_the_reminded_seat_has_passed_the_attack_may_be_sent_again() -> None:
    situation = two_seats(
        lambda b: b.with_battlefield("Grizzly Bears"),
        lambda b: b.with_battlefield("Banner of Each Combat"),
    )
    attacked(situation, ["Grizzly Bears"])
    passed(situation, S2)

    attacked(situation, ["Grizzly Bears"])

    assert situation.game.declared_attack is not None
    assert situation.game.step is Step.DECLARE_ATTACKERS


# @spec CMBT-070
def test_an_empty_attack_opens_no_window_and_leaves_the_combats_declaration_to_come() -> None:
    situation = two_seats(lambda b: b.with_battlefield("Grizzly Bears"))

    attacked(situation, [])
    assert situation.game.window is None
    attacked(situation, ["Grizzly Bears"])

    assert situation.game.declared_attack is not None
    assert situation.game.window is not None


# @spec CMBT-051
def test_the_result_of_combat_is_an_immediate_effect_applied_at_once_to_any_seat() -> None:
    situation = two_seats(
        lambda b: b.with_battlefield("Grizzly Bears"),
        lambda b: b.with_battlefield("Llanowar Elves"),
        step=Step.COMBAT_DAMAGE,
    )

    recorded(
        situation,
        S1,
        "the result of combat",
        {"move": {"graveyard": ["Llanowar Elves", "Grizzly Bears"]}, "life": {"1": 2, "2": -5}},
        immediate=True,
    )

    assert situation.game.stack == []
    assert situation.game.window is None
    assert situation.names_in(Zone.GRAVEYARD, S2) == ["Llanowar Elves"]
    assert (situation.game.seat(S1).life, situation.game.seat(S2).life) == (42, 35)
