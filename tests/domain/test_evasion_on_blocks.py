"""Evasion on blocks in a contested game: a `blocks` answer is checked against each attacker's
flying, horsemanship and "can't be blocked", read from card data or stated by the attacking
seat in `evasion`, and the `blocks` choice shows the evasion it will check."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.results import Applied, Refusal
from tests.support.acting import S1, S2, check_kinds, error_kinds, events_named
from tests.support.combat import (
    a_duel,
    advanced,
    at_blocks,
    attacked,
    attacking,
    blocked,
    blocking,
    card_of,
    immediately,
)

EVASION = "evasion_forbids_block"


def held(check: Any) -> tuple[str, str, str, bool, bool, tuple[str, ...]]:
    """What a failed evasion check names: blocker, attacker, evasion and where it is held from."""
    evasion = check.evasion
    return (
        check.subject,
        check.attacker,
        evasion.evasion.value,
        evasion.read,
        evasion.listed,
        evasion.assumptions,
    )


# ------------------------------------------------------------------ the checks


# @spec CMBT-083
def test_a_blocker_without_flying_or_reach_blocking_a_flyer_fails_a_rule_check() -> None:
    situation = at_blocks(a_duel(attackers=("Wind Drake",)), attackers=["Wind Drake"])
    result = blocking(situation, S2, {"Llanowar Elves": "Wind Drake"})
    assert check_kinds(result) == [EVASION]


# @spec CMBT-084
def test_a_blocker_without_horsemanship_blocking_a_horseman_fails_a_rule_check() -> None:
    situation = at_blocks(a_duel(attackers=("Shu Cavalry",)), attackers=["Shu Cavalry"])
    assert check_kinds(blocking(situation, S2, {"Llanowar Elves": "Shu Cavalry"})) == [EVASION]


# @spec CMBT-084
def test_a_blocker_with_horsemanship_may_block_a_horseman() -> None:
    situation = at_blocks(
        a_duel(attackers=("Shu Cavalry",), blockers=("Wu Light Cavalry",)),
        attackers=["Shu Cavalry"],
    )
    result = blocking(situation, S2, {"Wu Light Cavalry": "Shu Cavalry"})
    assert isinstance(result, Applied)


# @spec CMBT-085
@pytest.mark.parametrize("blocker", ["Llanowar Elves", "Wind Drake", "Wu Light Cavalry"])
def test_any_blocker_blocking_an_attacker_that_can_t_be_blocked_fails_a_rule_check(
    blocker: str,
) -> None:
    situation = at_blocks(
        a_duel(attackers=("Phantom Warrior",), blockers=(blocker,)), attackers=["Phantom Warrior"]
    )
    assert check_kinds(blocking(situation, S2, {blocker: "Phantom Warrior"})) == [EVASION]


# @spec CMBT-086
@pytest.mark.parametrize(
    ("blocker", "also"),
    [("Wind Drake", ()), ("Giant Spider", ()), ("Wind Drake", ("Treetop Snare",))],
    ids=["flying", "reach", "flying and reach"],
)
def test_a_blocker_with_flying_or_reach_or_both_may_block_a_flyer(
    blocker: str, also: tuple[str, ...]
) -> None:
    situation = at_blocks(
        a_duel(attackers=("Wind Drake",), blockers=(blocker,), blocking_seat_also=also),
        attackers=["Wind Drake"],
    )
    assert isinstance(blocking(situation, S2, {blocker: "Wind Drake"}), Applied)


# ------------------------------------------------------------------ where evasion comes from


# @spec CMBT-087
def test_flying_granted_by_a_permanent_the_attacking_seat_controls_is_checked() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",), attacking_seat_also=("Levitation",)),
        attackers=["Grizzly Bears"],
    )
    assert check_kinds(blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"})) == [EVASION]


# @spec CMBT-087
def test_flying_granted_by_a_permanent_another_seat_controls_does_not_reach_the_attacker() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",), blocking_seat_also=("Levitation",)),
        attackers=["Grizzly Bears"],
    )
    assert isinstance(blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"}), Applied)


# @spec CMBT-087
def test_a_grant_that_excludes_its_own_card_gives_that_attacker_no_flying() -> None:
    situation = at_blocks(a_duel(attackers=("Flock Leader",)), attackers=["Flock Leader"])
    assert isinstance(blocking(situation, S2, {"Llanowar Elves": "Flock Leader"}), Applied)


# @spec CMBT-087
def test_a_grant_limited_to_a_subtype_reaches_an_attacker_of_that_subtype() -> None:
    situation = at_blocks(
        a_duel(attackers=("Spirit Wisp",), attacking_seat_also=("Spirit Banner",)),
        attackers=["Spirit Wisp"],
    )
    assert check_kinds(blocking(situation, S2, {"Llanowar Elves": "Spirit Wisp"})) == [EVASION]


# @spec CMBT-087
def test_a_grant_limited_to_a_subtype_does_not_reach_an_attacker_of_another_type() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",), attacking_seat_also=("Spirit Banner",)),
        attackers=["Grizzly Bears"],
    )
    assert isinstance(blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"}), Applied)


# @spec CMBT-080, CMBT-087
def test_evasion_listed_on_the_attack_is_held_for_the_attacker_and_checked() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",)),
        attackers=["Grizzly Bears"],
        evasion={"Grizzly Bears": "flying"},
    )
    assert check_kinds(blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"})) == [EVASION]


# @spec CMBT-080
def test_evasion_listed_on_one_declaration_is_not_held_for_the_next_combat() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",)),
        attackers=["Grizzly Bears"],
        evasion={"Grizzly Bears": ["flying", "unblockable"]},
    )
    blocked(situation, S2, {})
    advanced(situation, "main2")
    attacked(situation, attackers=["Grizzly Bears"], override="an extra combat card")
    advanced(situation, "declare_blockers")
    assert isinstance(blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"}), Applied)


# @spec CMBT-088
def test_reach_granted_by_a_permanent_the_answering_seat_controls_lets_a_blocker_block() -> None:
    situation = at_blocks(
        a_duel(attackers=("Wind Drake",), blocking_seat_also=("Treetop Snare",)),
        attackers=["Wind Drake"],
    )
    assert isinstance(blocking(situation, S2, {"Llanowar Elves": "Wind Drake"}), Applied)


# @spec CMBT-088
def test_reach_granted_by_a_permanent_another_seat_controls_does_not_reach_the_blocker() -> None:
    situation = at_blocks(
        a_duel(attackers=("Wind Drake",), attacking_seat_also=("Treetop Snare",)),
        attackers=["Wind Drake"],
    )
    assert check_kinds(blocking(situation, S2, {"Llanowar Elves": "Wind Drake"})) == [EVASION]


# @spec CMBT-089
def test_evasion_is_read_from_the_attackers_as_they_stand_when_blocks_are_given() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",), attacking_seat_hand=("Levitation",)),
        attackers=["Grizzly Bears"],
    )
    immediately(situation, {"move": {"battlefield": ["Levitation"]}})
    assert check_kinds(blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"})) == [EVASION]


# ------------------------------------------------------------------ the refusal and override


# @spec CMBT-090
def test_the_refusal_names_the_blocker_the_attacker_and_flying_read_from_its_card() -> None:
    situation = at_blocks(a_duel(attackers=("Wind Drake",)), attackers=["Wind Drake"])
    result = blocking(situation, S2, {"Llanowar Elves": "Wind Drake"})
    assert isinstance(result, Refusal)
    assert [held(check) for check in result.checks] == [
        ("Llanowar Elves", "Wind Drake", "flying", True, False, ())
    ]


# @spec CMBT-090
def test_the_refusal_gives_the_assumption_of_a_reading_under_a_condition() -> None:
    situation = at_blocks(a_duel(attackers=("Island Skimmer",)), attackers=["Island Skimmer"])
    result = blocking(situation, S2, {"Llanowar Elves": "Island Skimmer"})
    assert isinstance(result, Refusal)
    assert [held(check)[5] for check in result.checks] == [("assumes its condition is met",)]


# @spec CMBT-090
@pytest.mark.parametrize(
    ("attacker", "read"), [("Grizzly Bears", False), ("Wind Drake", True)], ids=["listed", "both"]
)
def test_the_refusal_says_whether_flying_was_listed_in_evasion_or_also_read(
    attacker: str, read: bool
) -> None:
    situation = at_blocks(
        a_duel(attackers=(attacker,)), attackers=[attacker], evasion={attacker: "flying"}
    )
    result = blocking(situation, S2, {"Llanowar Elves": attacker})
    assert isinstance(result, Refusal)
    assert [held(check)[2:5] for check in result.checks] == [("flying", read, True)]


# @spec CMBT-090
def test_an_attacker_with_two_evasions_fails_one_check_for_each() -> None:
    situation = at_blocks(a_duel(attackers=("Sky Rider",)), attackers=["Sky Rider"])
    result = blocking(situation, S2, {"Llanowar Elves": "Sky Rider"})
    assert isinstance(result, Refusal)
    assert [held(check)[2] for check in result.checks] == ["flying", "horsemanship"]


# @spec CMBT-091
def test_an_override_records_the_blocks_and_names_the_overridden_evasion_checks() -> None:
    situation = at_blocks(a_duel(attackers=("Wind Drake",)), attackers=["Wind Drake"])
    result = blocked(
        situation, S2, {"Llanowar Elves": "Wind Drake"}, override="it gained reach this turn"
    )
    attack_ = situation.game.declared_attack
    assert attack_ is not None
    assert attack_.blocked == [card_of(situation, "Wind Drake", S1).id]
    (overridden,) = events_named(result, "ChecksOverridden")
    assert [check.kind.value for check in overridden.checks] == [EVASION]


# @spec CMBT-092
def test_blocks_recorded_stand_when_the_attacker_gains_evasion_afterwards() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",), attacking_seat_hand=("Levitation",)),
        attackers=["Grizzly Bears"],
    )
    blocked(situation, S2, {"Llanowar Elves": "Grizzly Bears"})
    immediately(situation, {"move": {"battlefield": ["Levitation"]}})
    attack_ = situation.game.declared_attack
    assert attack_ is not None
    assert attack_.blocked == [card_of(situation, "Grizzly Bears", S1).id]


# ------------------------------------------------------------------ what the choice shows


# @spec CMBT-081
def test_a_blocks_choice_shows_each_attacker_with_the_evasion_held_for_it() -> None:
    situation = attacked(
        a_duel(attackers=("Grizzly Bears", "Wind Drake")),
        attackers=["Grizzly Bears", "Wind Drake"],
        evasion={"Grizzly Bears": "unblockable"},
    )
    result = advanced(situation, "declare_blockers")
    (requested,) = events_named(result, "BlocksRequested")
    shown = [[e.value for e in each] for each in requested.evasion]
    assert (requested.attacker_ids, shown) == (
        (card_of(situation, "Grizzly Bears", S1).id, card_of(situation, "Wind Drake", S1).id),
        [["unblockable"], ["flying"]],
    )


# @spec CMBT-081
def test_the_listing_of_a_blocks_choice_shows_evasion_as_held_when_it_is_listed() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",), attacking_seat_hand=("Levitation",)),
        attackers=["Grizzly Bears"],
    )
    immediately(situation, {"move": {"battlefield": ["Levitation"]}})
    listing: Any = list_state(situation.game, situation.deck, S2)
    (choice,) = listing.choices
    assert [[e.value for e in each] for each in choice.evasion] == [["flying"]]


# ------------------------------------------------------------------ the evasion argument


# @spec CMBT-093
def test_evasion_for_something_that_is_not_an_attacker_is_an_error() -> None:
    situation = a_duel(attackers=("Grizzly Bears", "Wind Drake"))
    result = attacking(situation, attackers=["Grizzly Bears"], evasion={"Wind Drake": "flying"})
    assert error_kinds(result) == ["not_an_attacker"]


# @spec CMBT-094
@pytest.mark.parametrize(
    "value",
    ["trample", [], ["flying", "flying"], ["flying", "menace"], 3],
    ids=["not an evasion", "an empty list", "a repeated value", "one not an evasion", "a number"],
)
def test_an_evasion_entry_that_is_not_an_evasion_or_a_list_of_distinct_ones_is_an_error(
    value: object,
) -> None:
    situation = a_duel(attackers=("Grizzly Bears",))
    result = attacking(situation, attackers=["Grizzly Bears"], evasion={"Grizzly Bears": value})
    assert error_kinds(result) == ["malformed_argument"]


# @spec CMBT-095
def test_evasion_is_not_given_in_a_goldfish_game() -> None:
    situation = a_duel(attackers=("Grizzly Bears",), seats=1)
    result = attacking(situation, attackers=["Grizzly Bears"], evasion={"Grizzly Bears": "flying"})
    assert error_kinds(result) == ["contested_only"]
