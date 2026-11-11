"""A contested game whose seats reach one another is stored and read back whole: choices
addressed to seats, a look at a hand waiting for answers, attack targets and blocks, and the
events a seat's most recent change reported."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, acted
from tests.support.builders import Situation, a_game


def three_seats() -> Situation:
    builder: Any = a_game().with_battlefield("Grizzly Bears").with_hand("Island")
    builder = builder.and_an_opposing_seat().with_hand("Island").with_battlefield("Llanowar Elves")
    return builder.and_an_opposing_seat().with_hand("Lightning Bolt").build()


def round_trip(game: Game) -> Game:
    read: Game = decode(encode(game, Game), Game)
    return read


# @spec STOR-015
def test_choices_addressed_to_seats_and_a_waiting_look_at_a_hand_are_stored_whole() -> None:
    situation = three_seats()
    delta = {"ask": [{"seats": "opponents", "text": "discard a card"}], "look_at_hand": 3}
    result = acted(
        situation,
        effect(situation.game, situation.deck, S1, source="Mind Rot", delta=delta, immediate=True),
    )
    accept_change(result, S1, "effect", {"delta": delta})
    assert situation.game.hand_looks
    assert round_trip(situation.game) == situation.game


# @spec STOR-015
def test_attack_targets_and_blocks_choices_are_stored_whole() -> None:
    situation = three_seats()
    acted(
        situation,
        attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"], targets=2),  # type: ignore[call-arg]
    )
    result = acted(situation, advance(situation.game, situation.deck, S1, to="declare_blockers"))
    accept_change(result, S1, "advance", {"to": "declare_blockers"})
    assert situation.game.pending[0].attackers
    assert round_trip(situation.game) == situation.game
