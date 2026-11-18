"""Station cards as creatures: a station card with enough charge counters is a creature, and
every rule that speaks of a creature (attacking, blocking, summoning sickness, mana sources,
counts of creatures) treats it as one."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.events import AttackerDamage, CheckKind, CombatDamageDealt, Error
from mtg_goldfishing.domain.game.cards_in_play import is_creature
from mtg_goldfishing.domain.game.listing import StationListing, list_state
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.payment.sources import count
from mtg_goldfishing.domain.reading.model import PermanentsCount
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, check_kinds, events_named, recorded
from tests.support.builders import TESTED, GameBuilder, Situation, a_game
from tests.support.combat import advanced, attacked, blocking, card_of

LABSHIP = "Synthesizer Labship"
RAIDER = "K'Vort-Class Raider"


def stationed(name: str = LABSHIP, charge: int = 9, **options: Any) -> GameBuilder:
    """The tested seat's first main step, with a station card carrying `charge` counters."""
    return a_game().with_battlefield(name, counters={"charge": charge}, **options)


def judged_creature(situation: Situation, name: str = LABSHIP) -> bool:
    return is_creature(situation.deck, situation.named(name))


def declare(situation: Situation, **arguments: object) -> Applied | Refusal:
    operate: Any = attack
    result: Applied | Refusal = operate(situation.game, situation.deck, TESTED, **arguments)
    if isinstance(result, Applied):
        situation.game = result.game
    return result


# ------------------------------------------------------------------ which permanents are creatures


# @spec GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_with_the_charge_counters_its_reading_names_is_a_creature() -> None:
    assert judged_creature(stationed(charge=9).build())


# @spec GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_with_more_charge_counters_than_it_needs_is_a_creature() -> None:
    assert judged_creature(stationed(charge=12).build())


# @spec GAME-198
def test_a_station_card_with_fewer_charge_counters_than_it_needs_is_not_a_creature() -> None:
    assert not judged_creature(stationed(charge=8).build())


# @spec GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_the_charge_counter_kind_is_matched_ignoring_case() -> None:
    situation = a_game().with_battlefield(LABSHIP, counters={"Charge": 9}).build()
    assert judged_creature(situation)


# @spec GAME-198
def test_counters_of_another_kind_do_not_make_a_station_card_a_creature() -> None:
    situation = a_game().with_battlefield(LABSHIP, counters={"+1/+1": 9}).build()
    assert not judged_creature(situation)


# @spec GAME-198
def test_a_station_card_stops_being_a_creature_when_its_charge_counters_fall_short() -> None:
    situation = stationed(charge=9).build()
    recorded(situation, TESTED, "a test effect", {"counters": {LABSHIP: {"charge": -1}}})
    assert not judged_creature(situation)


# @spec GAME-198
def test_a_station_card_returned_to_hand_and_put_back_is_not_a_creature() -> None:
    situation = stationed(charge=9).build()
    recorded(situation, TESTED, "a bounce", {"move": {"hand": [LABSHIP]}})
    recorded(situation, TESTED, "a recast", {"move": {"battlefield": [LABSHIP]}})
    assert not judged_creature(situation)


# @spec GAME-198
def test_a_station_card_that_never_becomes_a_creature_is_not_one_at_any_count() -> None:
    assert not judged_creature(stationed("Deep Space 9", charge=40).build(), "Deep Space 9")


# ------------------------------------------------------------------ attacking


# @spec CMBT-017, GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_with_enough_charge_counters_attacks_without_an_override() -> None:
    situation = stationed(charge=9).build()
    assert isinstance(declare(situation, attackers=[LABSHIP]), Applied)


# @spec CMBT-017
def test_a_station_card_short_of_its_charge_counters_fails_the_creature_check() -> None:
    situation = stationed(charge=3).build()
    result = declare(situation, attackers=[LABSHIP])
    assert isinstance(result, Refusal)
    assert [c.kind for c in result.checks] == [CheckKind.NOT_A_CREATURE]


# @spec GAME-199
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_deals_its_printed_power_in_combat() -> None:
    situation = stationed(charge=9).build()
    declare(situation, attackers=[LABSHIP])
    result = advance(situation.game, situation.deck, TESTED, to="combat_damage")
    assert isinstance(result, Applied), result
    dealt = next(e for e in result.events if isinstance(e, CombatDamageDealt))
    assert dealt.hits == (AttackerDamage(LABSHIP, 4),)


# @spec CMBT-019, GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_that_entered_this_turn_is_summoning_sick_as_a_creature() -> None:
    situation = stationed(charge=9, entered_turn=3).build()
    result = declare(situation, attackers=[LABSHIP])
    assert isinstance(result, Refusal)
    assert [c.kind for c in result.checks] == [CheckKind.SUMMONING_SICK_ATTACKER]


# @spec CMBT-019, READ-068
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_with_haste_after_its_station_symbol_attacks_the_turn_it_entered() -> None:
    situation = stationed(RAIDER, charge=4, entered_turn=3).build()
    assert isinstance(declare(situation, attackers=[RAIDER]), Applied)


# ------------------------------------------------------------------ blocking


def defended_by(*permanents: str, charge: int = 9) -> Situation:
    """Seat 1 attacks seat 2 with Grizzly Bears; seat 2 controls `permanents`, each station
    card among them carrying `charge` counters."""
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    builder = builder.with_battlefield(*permanents, counters={"charge": charge})
    return attacked(builder.build(), attackers=["Grizzly Bears"])


# @spec CMBT-037, CMBT-047, GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_seat_whose_only_creature_is_a_station_card_is_asked_for_blocks() -> None:
    situation = defended_by(LABSHIP)
    advanced(situation, "declare_blockers")
    assert [(c.kind, c.seat) for c in situation.game.pending] == [("blocks", S2)]


# @spec CMBT-047
def test_a_seat_whose_station_card_is_short_of_its_charge_counters_is_not_asked() -> None:
    situation = defended_by(LABSHIP, charge=2)
    result = advanced(situation, "declare_blockers")
    assert situation.game.pending == []
    assert [e.seat for e in events_named(result, "NoBlocksDeclared")] == [S2]


# @spec CMBT-046, GAME-198
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_with_enough_charge_counters_blocks_without_an_override() -> None:
    situation = defended_by(LABSHIP)
    advanced(situation, "declare_blockers")
    result = blocking(situation, S2, {LABSHIP: "Grizzly Bears"})
    assert isinstance(result, Applied), check_kinds(result)
    assert result.game.declared_attack is not None
    assert result.game.declared_attack.blocked == [card_of(situation, "Grizzly Bears", S1).id]


# ------------------------------------------------------------------ mana


# @spec PAY-055
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_count_of_creatures_counts_a_station_card_with_enough_charge_counters() -> None:
    situation = stationed(charge=9).with_battlefield("Gaea's Cradle", "Grizzly Bears").build()
    cradle = situation.named("Gaea's Cradle")
    assert count(situation.game, situation.deck, cradle, PermanentsCount("creature")) == 2


# @spec PAY-055
def test_a_count_of_creatures_leaves_out_a_station_card_short_of_its_charge_counters() -> None:
    situation = stationed(charge=1).with_battlefield("Gaea's Cradle", "Grizzly Bears").build()
    cradle = situation.named("Gaea's Cradle")
    assert count(situation.game, situation.deck, cradle, PermanentsCount("creature")) == 1


# ------------------------------------------------------------------ state on request


def listed_station(situation: Situation) -> StationListing | None:
    listing = list_state(situation.game, situation.deck, TESTED, "summary")
    assert not isinstance(listing, Error)
    return next(p.station for p in listing.battlefield if p.name == LABSHIP)


# @spec GAME-200
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_the_listing_shows_a_station_card_that_is_a_creature_with_its_power_and_toughness() -> None:
    assert listed_station(stationed(charge=9).build()) == StationListing(
        creature_at=9, creature=True, power="4", toughness="4"
    )


# @spec GAME-200
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_the_listing_shows_a_station_card_short_of_its_charge_counters_as_no_creature() -> None:
    assert listed_station(stationed(charge=2).build()) == StationListing(
        creature_at=9, creature=False
    )


# @spec GAME-200
def test_the_listing_shows_no_station_for_a_permanent_without_a_station_reading() -> None:
    situation = a_game().with_battlefield("Grizzly Bears").build()
    listing = list_state(situation.game, situation.deck, TESTED, "summary")
    assert not isinstance(listing, Error)
    assert [p.station for p in listing.battlefield] == [None]


# @spec GAME-198
def test_a_token_is_never_a_creature_by_charge_counters() -> None:
    situation = a_game().build()
    recorded(
        situation,
        TESTED,
        "a token maker",
        {"tokens": [{"name": "Ship Copy", "types": "Artifact — Spacecraft", "pt": "4/4"}]},
    )
    token = situation.named("Ship Copy")
    token.counters["charge"] = 20
    assert not is_creature(situation.deck, token)
