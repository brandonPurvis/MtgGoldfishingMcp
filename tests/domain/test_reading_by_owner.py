"""A card instance is read from its owner's deck, whichever seat controls it: a permanent taken
from another seat keeps the mana, keywords and type its owner's deck reads for it.

Each table gives the seats different decks, so a permanent read from the controlling seat's
deck, which does not hold it, would lose everything the service reads of it.
"""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import play
from mtg_goldfishing.domain.stack.passing import pass_
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, acted, check_kinds
from tests.support.builders import Situation, a_deck, a_game

CROSSROADS = "Concordant Crossroads"


def card_of(situation: Situation, name: str, owner: Any) -> Any:
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


def taken_by_seat_1(situation_builder: Any, *names: str) -> Situation:
    """The opposing seat's permanents `names`, now controlled by seat 1."""
    builder = situation_builder
    for name in names:
        builder = builder.controlled_by(name, 1)
    situation: Situation = builder.build()
    return situation


# @spec PAY-054, GAME-171
def test_a_permanent_taken_from_another_seat_makes_the_mana_its_owners_deck_reads() -> None:
    builder: Any = a_game().with_hand("Grizzly Bears").with_battlefield("Forest")
    builder = builder.and_an_opposing_seat().with_battlefield("Llanowar Elves")
    situation = taken_by_seat_1(builder, "Llanowar Elves")
    decks = Decks({S1: a_deck("Grizzly Bears", "Forest"), S2: a_deck("Llanowar Elves")})

    acted(situation, play(situation.game, decks.of(S1), S1, card="Grizzly Bears", decks=decks))

    assert card_of(situation, "Llanowar Elves", S2).tapped


# @spec PAY-054
def test_a_counted_amount_reads_each_counted_permanent_from_its_owners_deck() -> None:
    builder: Any = a_game().with_hand("Grizzly Bears").with_battlefield("Gaea's Cradle")
    builder = builder.with_battlefield("Grizzly Bears")
    builder = builder.and_an_opposing_seat().with_battlefield("Tarmogoyf")
    situation = taken_by_seat_1(builder, "Tarmogoyf")
    decks = Decks({S1: a_deck("Grizzly Bears", "Gaea's Cradle"), S2: a_deck("Tarmogoyf")})

    acted(situation, play(situation.game, decks.of(S1), S1, card="Grizzly Bears", decks=decks))

    assert card_of(situation, "Gaea's Cradle", S1).tapped


# @spec PAY-054
def test_haste_granted_by_a_taken_permanent_lets_a_new_creature_pay() -> None:
    builder: Any = a_game().with_hand("Grizzly Bears").with_battlefield("Forest")
    builder = builder.with_battlefield("Llanowar Elves", entered_turn=3)
    builder = builder.and_an_opposing_seat().with_battlefield(CROSSROADS)
    situation = taken_by_seat_1(builder, CROSSROADS)
    mine = a_deck("Grizzly Bears", "Forest", "Llanowar Elves")
    decks = Decks({S1: mine, S2: a_deck(CROSSROADS)})

    acted(situation, play(situation.game, mine, S1, card="Grizzly Bears", decks=decks))

    assert card_of(situation, "Llanowar Elves", S1).tapped


# @spec CMBT-079
def test_haste_granted_by_a_taken_permanent_lets_a_new_creature_attack() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears", entered_turn=3)
    builder = builder.and_an_opposing_seat().with_battlefield(CROSSROADS)
    situation = taken_by_seat_1(builder, CROSSROADS)
    mine = a_deck("Grizzly Bears")
    decks = Decks({S1: mine, S2: a_deck(CROSSROADS)})

    result = attack(situation.game, mine, S1, attackers=["Grizzly Bears"], targets=2, decks=decks)

    acted(situation, result)


# @spec CMBT-079
def test_a_taken_attacker_keeps_the_vigilance_its_owners_deck_reads() -> None:
    builder: Any = a_game().and_an_opposing_seat().with_battlefield("Serra Angel")
    situation = taken_by_seat_1(builder, "Serra Angel")
    mine = a_deck("Grizzly Bears")
    decks = Decks({S1: mine, S2: a_deck("Serra Angel")})

    acted(
        situation,
        attack(situation.game, mine, S1, attackers=["Serra Angel"], targets=2, decks=decks),
    )

    assert not card_of(situation, "Serra Angel", S2).tapped


# @spec GAME-171
def test_a_taken_permanent_is_listed_with_the_mana_its_owners_deck_reads() -> None:
    builder: Any = a_game().and_an_opposing_seat().with_battlefield("Llanowar Elves")
    situation = taken_by_seat_1(builder, "Llanowar Elves")
    decks = Decks({S1: a_deck("Grizzly Bears"), S2: a_deck("Llanowar Elves")})

    listing: Any = list_state(situation.game, decks.of(S1), S1, decks=decks)

    assert [bool(permanent.mana) for permanent in listing.battlefield] == [True]


# @spec GAME-171
def test_haste_granted_by_a_taken_permanent_is_listed() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears", entered_turn=3)
    builder = builder.and_an_opposing_seat().with_battlefield(CROSSROADS)
    situation = taken_by_seat_1(builder, CROSSROADS)
    decks = Decks({S1: a_deck("Grizzly Bears"), S2: a_deck(CROSSROADS)})

    listing: Any = list_state(situation.game, decks.of(S1), S1, decks=decks)

    bears = next(p for p in listing.battlefield if p.name == "Grizzly Bears")
    assert bears.haste


# @spec GAME-171, CMBT-089
@pytest.mark.xfail(strict=True, reason="M1: not implemented yet")
def test_a_taken_attacker_keeps_the_flying_its_owners_deck_reads_when_blocks_are_judged() -> None:
    builder: Any = a_game().and_an_opposing_seat().with_battlefield("Wind Drake", "Llanowar Elves")
    situation = taken_by_seat_1(builder, "Wind Drake")
    mine = a_deck("Grizzly Bears")
    decks = Decks({S1: mine, S2: a_deck("Wind Drake", "Llanowar Elves")})
    acted(
        situation,
        attack(situation.game, mine, S1, attackers=["Wind Drake"], targets=2, decks=decks),
    )
    acted(situation, pass_(situation.game, mine, S2, decks=decks))
    acted(situation, advance(situation.game, mine, S1, to="declare_blockers", decks=decks))
    choice = situation.game.pending[0].choice_id

    result = choose(
        situation.game,
        decks.of(S2),
        S2,
        choice_id=choice,
        blocks={"Llanowar Elves": "Wind Drake"},
        decks=decks,
    )

    assert check_kinds(result) == ["evasion_forbids_block"]


# @spec REC-081
def test_a_snapshot_counts_a_land_taken_from_another_seat_among_the_lands() -> None:
    builder: Any = a_game().in_step(Step.END).with_hand("Grizzly Bears")
    builder = builder.and_an_opposing_seat().with_battlefield("Command Tower")
    situation = taken_by_seat_1(builder, "Command Tower")
    decks = Decks({S1: a_deck("Grizzly Bears"), S2: a_deck("Command Tower")})

    result = acted(situation, advance(situation.game, decks.of(S1), S1, to="cleanup", decks=decks))

    assert [snapshot.lands for snapshot in result.snapshots] == [1]


# @spec REC-081
def test_a_snapshot_judges_payable_with_the_mana_of_a_permanent_taken_from_another_seat() -> None:
    builder: Any = a_game().in_step(Step.END).with_hand("Llanowar Elves")
    builder = builder.and_an_opposing_seat().with_battlefield("Forest")
    situation = taken_by_seat_1(builder, "Forest")
    decks = Decks({S1: a_deck("Llanowar Elves"), S2: a_deck("Forest")})

    result = acted(situation, advance(situation.game, decks.of(S1), S1, to="cleanup", decks=decks))

    assert [card.payable for card in result.snapshots[0].hand] == [True]
