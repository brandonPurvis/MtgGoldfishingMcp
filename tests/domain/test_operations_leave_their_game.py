"""A domain operation that applies a call leaves the game it was given as it was.

Its changes are made on a copy: after an applied result, the game given equals the game it
was before the call, and it still does once the caller counts the change on the result's
game, so nothing the operation or its caller changes is reachable from the game given. A game
a repository returned can then be shared by every reader without a copy. Parts nobody changes
may be shared.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.results import Applied, Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.stack.passing import pass_
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, acted
from tests.support.builders import TESTED, Situation, a_game
from tests.support.tables import bolt_at, two_seats

Operate = Callable[[Situation], Result]


@dataclass(frozen=True)
class Case:
    """A situation, and an operation the situation's game accepts."""

    arrange: Callable[[], Situation]
    operate: Operate
    seat: SeatNumber = TESTED


def _goldfish_look() -> Situation:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    acted(
        situation,
        effect(
            situation.game,
            situation.deck,
            TESTED,
            source="a look",
            delta={"look": {"n": 3, "from": "top", "rest": "graveyard"}},
        ),
    )
    return situation


def _choosing_the_look(situation: Situation) -> Result:
    waiting = situation.game.waiting_choice
    assert waiting is not None
    return choose(
        situation.game,
        situation.deck,
        TESTED,
        choice_id=waiting.choice_id,
        selections={"hand": ["Forest"]},
    )


def _a_bolt_on_the_stack() -> Situation:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    acted(
        situation,
        play(situation.game, situation.deck, S1, card="Lightning Bolt", delta=bolt_at(2)),
    )
    return situation


def _blockers_asked() -> Situation:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    situation: Situation = builder.with_battlefield("Llanowar Elves").build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    acted(situation, advance(situation.game, situation.deck, S1, to="declare_blockers"))
    return situation


def _blocking(situation: Situation) -> Result:
    choice = situation.game.pending[0].choice_id
    return choose(
        situation.game,
        situation.deck,
        S2,
        choice_id=choice,
        blocks={"Llanowar Elves": "Grizzly Bears"},
    )


CASES: dict[str, Case] = {
    "goldfish mulligan kept": Case(
        lambda: a_game().in_mulligan().build(),
        lambda s: mulligan(s.game, s.deck, TESTED, keep=True),
    ),
    "goldfish land played": Case(
        lambda: a_game().with_hand("Forest").build(),
        lambda s: play(s.game, s.deck, TESTED, card="Forest"),
    ),
    "goldfish effect recorded": Case(
        lambda: a_game().with_battlefield("Forest").build(),
        lambda s: effect(s.game, s.deck, TESTED, source="a test effect", delta={"life": 1}),
    ),
    "goldfish look answered": Case(_goldfish_look, _choosing_the_look),
    "goldfish attack declared": Case(
        lambda: a_game().in_step(Step.MAIN1).with_battlefield("Grizzly Bears").build(),
        lambda s: attack(s.game, s.deck, TESTED, attackers=["Grizzly Bears"]),
    ),
    "goldfish step advanced": Case(
        lambda: a_game().in_step(Step.MAIN1).with_library("Forest", "Island").build(),
        lambda s: advance(s.game, s.deck, TESTED, to="main2"),
    ),
    "goldfish game ended": Case(
        lambda: a_game().build(),
        lambda s: end_game(s.game, s.deck, TESTED, result="win", notes="fast"),
    ),
    "contested spell cast": Case(
        lambda: two_seats(lambda b: b.with_hand("Lightning Bolt")),
        lambda s: play(s.game, s.deck, S1, card="Lightning Bolt", delta=bolt_at(2)),
        seat=S1,
    ),
    "contested pass resolving a spell": Case(
        _a_bolt_on_the_stack,
        lambda s: pass_(s.game, s.deck, S2),
        seat=S2,
    ),
    "contested effect recorded": Case(
        two_seats,
        lambda s: effect(
            s.game, s.deck, S1, source="a test effect", delta={"life": 1}, immediate=True
        ),
        seat=S1,
    ),
    "contested blocks declared": Case(_blockers_asked, _blocking, seat=S2),
    "contested step advanced": Case(
        two_seats, lambda s: advance(s.game, s.deck, S1, to="end"), seat=S1
    ),
    "contested concession": Case(
        two_seats, lambda s: end_game(s.game, s.deck, S2, result="loss"), seat=S2
    ),
}


def _applied(case: Case) -> tuple[Game, Game, Applied]:
    """The game given, a copy of it taken before the call, and the applied result."""
    situation = case.arrange()
    given = situation.game
    before = given.copy()
    result = case.operate(situation)
    assert isinstance(result, Applied), result
    return given, before, result


# @spec APP-097
@pytest.mark.parametrize("name", CASES)
def test_an_applied_operation_leaves_the_game_it_was_given_as_it_was(name: str) -> None:
    given, before, _ = _applied(CASES[name])

    assert given == before


# @spec APP-097
@pytest.mark.parametrize("name", CASES)
def test_counting_an_applied_change_leaves_the_game_given_as_it_was(name: str) -> None:
    case = CASES[name]
    given, before, result = _applied(case)

    accept_change(result, case.seat, "a test call", {}, before=given)

    assert given == before
