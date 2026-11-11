"""Paying in a contested game: a seat pays with the permanents it controls, whoever owns them,
and never with another seat's."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.play.playing import play
from tests.support.acting import S1, S2, acted, check_kinds, errors_of
from tests.support.builders import Situation, a_deck, a_game


def card_of(situation: Situation, name: str, owner: Any) -> Any:
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


# @spec PAY-045, PAY-046
def test_a_seat_pays_with_a_permanent_it_controls_but_does_not_own() -> None:
    builder: Any = a_game().with_hand("Llanowar Elves").with_battlefield("Forest")
    builder = builder.controlled_by("Forest", 2).and_an_opposing_seat()
    situation = builder.with_battlefield("Forest").controlled_by("Forest", 1).build()
    acted(situation, play(situation.game, situation.deck, S1, card="Llanowar Elves"))
    assert card_of(situation, "Forest", S2).tapped
    assert not card_of(situation, "Forest", S1).tapped


# @spec PAY-047
def test_pay_with_naming_another_seat_s_permanent_is_an_error() -> None:
    builder: Any = a_game().with_hand("Llanowar Elves").and_an_opposing_seat()
    situation = builder.with_battlefield("Forest").build()
    forest = card_of(situation, "Forest", S2).id
    result = play(situation.game, situation.deck, S1, card="Llanowar Elves", pay={"with": [forest]})
    assert errors_of(result)
    assert not card_of(situation, "Forest", S2).tapped


def _duel() -> Any:
    """Seat 1 with Grizzly Bears in hand, a Forest and Llanowar Elves that entered this turn."""
    builder: Any = a_game().with_hand("Grizzly Bears").with_battlefield("Forest")
    return builder.with_battlefield("Llanowar Elves", entered_turn=3).and_an_opposing_seat()


# @spec PAY-049
def test_haste_granted_by_another_seat_s_permanent_does_not_make_a_new_creature_a_source() -> None:
    situation = _duel().with_battlefield("Concordant Crossroads").build()
    result = play(situation.game, situation.deck, S1, card="Grizzly Bears")
    assert check_kinds(result) == ["cost_not_payable"]


# @spec PAY-049
def test_haste_granted_by_a_permanent_the_seat_controls_but_does_not_own_counts() -> None:
    builder = _duel().with_battlefield("Concordant Crossroads")
    situation = builder.controlled_by("Concordant Crossroads", 1).build()
    acted(situation, play(situation.game, situation.deck, S1, card="Grizzly Bears"))
    assert card_of(situation, "Llanowar Elves", S1).tapped


def _commander_deck(commander: str, *names: str) -> Any:
    return a_deck(*names, commanders=(commander,))


# @spec PAY-050
def test_commander_identity_mana_comes_from_the_controlling_seat_s_commanders() -> None:
    builder: Any = a_game().with_hand("Ponder").and_an_opposing_seat()
    situation = builder.with_battlefield("Command Tower").controlled_by("Command Tower", 1).build()
    mine = _commander_deck("Thrasios, Triton Hero", "Ponder", "Command Tower")
    theirs = _commander_deck("Tymna the Weaver", "Command Tower")
    decks = Decks({S1: mine, S2: theirs})
    acted(situation, play(situation.game, mine, S1, card="Ponder", decks=decks))
    assert card_of(situation, "Command Tower", S2).tapped


# @spec PAY-051
def test_a_counted_amount_counts_the_controlling_seat_s_permanents() -> None:
    builder: Any = a_game().with_hand("Cultivate").with_battlefield("Grizzly Bears")
    builder = builder.and_an_opposing_seat().with_battlefield("Gaea's Cradle")
    builder = builder.with_battlefield("Llanowar Elves", "Birds of Paradise", "Tarmogoyf")
    situation = builder.controlled_by("Gaea's Cradle", 1).build()
    result = play(situation.game, situation.deck, S1, card="Cultivate")
    assert check_kinds(result) == ["cost_not_payable"]
