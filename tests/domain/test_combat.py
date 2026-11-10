"""Declaring attacks and dealing combat damage."""

from __future__ import annotations

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.events import (
    AttackDeclared,
    AttackerDamage,
    CheckKind,
    ChecksOverridden,
    CombatDamageDealt,
    ErrorKind,
    ReminderIssued,
)
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.reading.model import CardReading, FaceReading
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import GameBuilder, Situation, a_game
from tests.support.library import card


def declared(situation: Situation, **arguments: object) -> Applied:
    result = attack(situation.game, situation.deck, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def refused(situation: Situation, **arguments: object) -> Refusal:
    result = attack(situation.game, situation.deck, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Refusal), result
    return result


def to_damage(situation: Situation) -> Applied:
    result = advance(situation.game, situation.deck, to="combat_damage")
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def bears(step: Step = Step.MAIN1) -> GameBuilder:
    return a_game().in_step(step).with_battlefield("Grizzly Bears")


# ------------------------------------------------------------------ when attack may be called


# @spec CMBT-001
def test_attacking_from_the_first_main_step_moves_to_declare_attackers() -> None:
    situation = bears().build()
    result = declared(situation, attackers=["Grizzly Bears"])
    assert result.game.step is Step.DECLARE_ATTACKERS
    assert result.game.declared_attack is not None


# @spec CMBT-002
def test_a_beginning_of_combat_reminder_is_listed_and_the_attack_still_declared() -> None:
    trigger = CardReading((FaceReading(step_triggers=(Step.BEGIN_COMBAT,)),))
    situation = (
        bears().with_card(card("Shivan Dragon"), trigger).with_battlefield("Shivan Dragon").build()
    )
    result = declared(situation, attackers=["Grizzly Bears"])
    assert ReminderIssued(Step.BEGIN_COMBAT, (("Shivan Dragon", 1),)) in result.events
    assert result.game.declared_attack is not None


# @spec CMBT-003
def test_attacking_in_declare_attackers_declares() -> None:
    situation = bears(Step.DECLARE_ATTACKERS).build()
    declared(situation, attackers=["Grizzly Bears"])
    assert situation.game.declared_attack is not None


# @spec CMBT-004
def test_a_second_attack_replaces_the_first_without_refusing_its_tapped_attackers() -> None:
    situation = bears(Step.DECLARE_ATTACKERS).with_battlefield("Goblin Guide").build()
    declared(situation, attackers=["Grizzly Bears"])
    situation.game.step = Step.DECLARE_BLOCKERS
    result = declared(situation, attackers=["Grizzly Bears", "Goblin Guide"])
    assert result.game.declared_attack is not None
    assert result.game.declared_attack.attackers == ["c1", "c2"]


# @spec CMBT-005
def test_attacking_before_the_first_main_step_fails_a_rule_check() -> None:
    situation = bears(Step.UPKEEP).build()
    result = refused(situation, attackers=["Grizzly Bears"])
    assert [c.kind for c in result.checks] == [CheckKind.ATTACK_TOO_EARLY]


# @spec CMBT-006
def test_attacking_early_with_an_override_proceeds_as_from_the_first_main_step() -> None:
    situation = bears(Step.UPKEEP).with_library("Forest").build()
    result = declared(situation, attackers=["Grizzly Bears"], override="Relentless Assault")
    assert result.game.step is Step.DECLARE_ATTACKERS


# @spec CMBT-007
def test_attacking_after_combat_damage_fails_a_rule_check() -> None:
    situation = bears(Step.MAIN2).build()
    result = refused(situation, attackers=["Grizzly Bears"])
    assert [c.kind for c in result.checks] == [CheckKind.COMBAT_OVER]


# @spec CMBT-008
def test_an_overridden_attack_after_combat_is_an_additional_combat() -> None:
    situation = bears(Step.MAIN2).build()
    result = declared(situation, attackers=["Grizzly Bears"], override="Relentless Assault")
    assert (result.game.turn, result.game.step) == (3, Step.DECLARE_ATTACKERS)


# @spec CMBT-009
def test_an_empty_attack_clears_an_earlier_declaration() -> None:
    situation = bears(Step.DECLARE_ATTACKERS).build()
    declared(situation, attackers=["Grizzly Bears"])
    result = declared(situation, attackers=[])
    assert result.game.declared_attack is None


# @spec CMBT-010
def test_a_refused_attack_changes_nothing_including_the_step() -> None:
    situation = bears(Step.UPKEEP).build()
    before = situation.game.copy()
    refused(situation, attackers=["Grizzly Bears"])
    assert situation.game == before


# ------------------------------------------------------------------ declaring


# @spec CMBT-011
def test_declaring_taps_attackers_without_vigilance() -> None:
    situation = bears().build()
    result = declared(situation, attackers=["Grizzly Bears"])
    assert result.game.instance("c1").tapped


# @spec CMBT-012
def test_declaring_leaves_attackers_with_vigilance_untapped() -> None:
    situation = a_game().with_battlefield("Serra Angel", "Grizzly Bears").build()
    result = declared(
        situation, attackers=["Serra Angel", "Grizzly Bears"], vigilance=["Grizzly Bears"]
    )
    assert not result.game.instance("c1").tapped
    assert not result.game.instance("c2").tapped


# @spec CMBT-013
def test_vigilance_and_haste_given_in_a_call_apply_to_that_declaration_only() -> None:
    situation = a_game().with_battlefield("Grizzly Bears", entered_turn=3).build()
    declared(situation, attackers=["Grizzly Bears"], haste=["Grizzly Bears"])
    situation.game.step = Step.DECLARE_BLOCKERS
    result = refused(situation, attackers=["Grizzly Bears"])
    assert CheckKind.SUMMONING_SICK_ATTACKER in [c.kind for c in result.checks]


# ------------------------------------------------------------------ refusals


# @spec CMBT-014
def test_an_attacker_not_on_the_battlefield_is_an_error() -> None:
    situation = a_game().with_hand("Grizzly Bears").build()
    result = refused(situation, attackers=["Grizzly Bears"])
    assert result.errors[0].kind is ErrorKind.ATTACKER_NOT_ON_BATTLEFIELD


# @spec CMBT-015
def test_naming_something_that_is_not_attacking_in_blocked_is_an_error() -> None:
    situation = bears().with_battlefield("Goblin Guide").build()
    result = refused(situation, attackers=["Grizzly Bears"], blocked=["Goblin Guide"])
    assert result.errors[0].kind is ErrorKind.NOT_AN_ATTACKER


# @spec CMBT-016
def test_a_commander_target_outside_zero_to_two_is_an_error() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=_battlefield()).build()
    result = refused(situation, attackers=["Atraxa, Praetors' Voice"], commander_target=3)
    assert result.errors[0].kind is ErrorKind.BAD_COMMANDER_TARGET


# @spec CMBT-017
def test_attacking_with_a_non_creature_fails_a_rule_check() -> None:
    situation = a_game().with_battlefield("Sol Ring").build()
    result = refused(situation, attackers=["Sol Ring"])
    assert [c.kind for c in result.checks] == [CheckKind.NOT_A_CREATURE]


# @spec CMBT-018
def test_attacking_with_a_tapped_creature_fails_a_rule_check() -> None:
    situation = a_game().with_battlefield("Grizzly Bears", tapped=True).build()
    result = refused(situation, attackers=["Grizzly Bears"])
    assert [c.kind for c in result.checks] == [CheckKind.ATTACKER_TAPPED]


# @spec CMBT-019
def test_attacking_with_a_creature_that_entered_this_turn_without_haste_fails_a_check() -> None:
    situation = a_game().with_battlefield("Grizzly Bears", entered_turn=3).build()
    result = refused(situation, attackers=["Grizzly Bears"])
    assert [c.kind for c in result.checks] == [CheckKind.SUMMONING_SICK_ATTACKER]


# @spec CMBT-019
def test_a_creature_with_haste_may_attack_the_turn_it_entered() -> None:
    situation = a_game().with_battlefield("Goblin Guide", entered_turn=3).build()
    declared(situation, attackers=["Goblin Guide"])


# @spec CMBT-020
def test_an_attacker_whose_power_is_not_a_number_needs_a_damage_entry() -> None:
    situation = a_game().with_battlefield("Tarmogoyf").build()
    result = refused(situation, attackers=["Tarmogoyf"])
    assert [c.kind for c in result.checks] == [CheckKind.POWER_NOT_A_NUMBER]
    declared(situation, attackers=["Tarmogoyf"], damage={"Tarmogoyf": 4})


# @spec CMBT-021
def test_an_overridden_attack_is_declared_and_names_the_overridden_checks() -> None:
    situation = a_game().with_battlefield("Grizzly Bears", tapped=True).build()
    result = declared(situation, attackers=["Grizzly Bears"], override="untapped by an effect")
    overridden = [e for e in result.events if isinstance(e, ChecksOverridden)]
    assert [c.kind for c in overridden[0].checks] == [CheckKind.ATTACKER_TAPPED]


# ------------------------------------------------------------------ combat damage


# @spec CMBT-022, CMBT-023
def test_unblocked_attackers_deal_power_adjusted_by_counters() -> None:
    situation = (
        a_game()
        .with_battlefield("Grizzly Bears", counters={"+1/+1": 2})
        .with_battlefield("Goblin Guide", counters={"-1/-1": 1})
        .build()
    )
    declared(situation, attackers=["Grizzly Bears", "Goblin Guide"])
    to_damage(situation)
    assert situation.game.damage_dealt == 5


# @spec CMBT-022
def test_a_damage_entry_replaces_the_default_damage() -> None:
    situation = bears().build()
    declared(situation, attackers=["Grizzly Bears"], damage={"Grizzly Bears": 7})
    to_damage(situation)
    assert situation.game.damage_dealt == 7


# @spec CMBT-024
def test_a_commander_also_deals_commander_damage_to_its_target() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=_battlefield()).build()
    declared(situation, attackers=["Atraxa, Praetors' Voice"], commander_target=2)
    to_damage(situation)
    assert situation.game.commander_damage["c1"] == [0, 0, 4]


# @spec CMBT-024
def test_a_commander_attacks_opponent_zero_by_default() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=_battlefield()).build()
    declared(situation, attackers=["Atraxa, Praetors' Voice"])
    to_damage(situation)
    assert situation.game.commander_damage["c1"] == [4, 0, 0]


# @spec CMBT-025
def test_blocked_attackers_deal_no_damage_to_opponents() -> None:
    situation = bears().with_battlefield("Goblin Guide").build()
    declared(situation, attackers=["Grizzly Bears", "Goblin Guide"], blocked=["Goblin Guide"])
    to_damage(situation)
    assert situation.game.damage_dealt == 2


# @spec CMBT-026
def test_combat_damage_clears_the_attack_and_reports_each_attacker() -> None:
    situation = bears().build()
    declared(situation, attackers=["Grizzly Bears"])
    result = to_damage(situation)
    assert result.game.declared_attack is None
    assert CombatDamageDealt((AttackerDamage("Grizzly Bears", 2),), 2, ()) in result.events


# @spec CMBT-027
def test_entering_combat_damage_without_an_attack_changes_no_total() -> None:
    situation = bears().build()
    to_damage(situation)
    assert situation.game.damage_dealt == 0


def test_the_declaration_reports_attackers_blocked_and_targets() -> None:
    situation = bears().build()
    result = declared(situation, attackers=["Grizzly Bears"])
    assert result.summary == AttackDeclared(("Grizzly Bears",), (), (), ("Grizzly Bears",))


def _battlefield():  # type: ignore[no-untyped-def]
    from mtg_goldfishing.domain.game.model import Zone  # noqa: PLC0415

    return Zone.BATTLEFIELD
