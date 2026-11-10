"""Paying in a contested game: a seat pays with the permanents it controls, whoever owns them,
and never with another seat's."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.play.playing import play
from tests.support.acting import S1, S2, acted, errors_of
from tests.support.builders import Situation, a_game


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
