"""Builders for outcomes, the renderer's input.

outcome = outcome_of(situation, play(situation.game, situation.deck, card="Forest"))
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.events import Refused
from mtg_goldfishing.domain.game.model import GameStatus
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent
from mtg_goldfishing.domain.game.summary import CommanderStatus, GameSummary, summarize
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import TESTED, Situation

ATRAXA = "Atraxa, Praetors' Voice"


def a_summary(**changes: Any) -> GameSummary:
    """The status-line facts of an active game in turn 6, changed as the test says."""
    summary = GameSummary(
        game_id="gtest000001",
        status=GameStatus.ACTIVE,
        turn=6,
        step=Step.MAIN1,
        hand=4,
        lands=6,
        untapped_lands=5,
        pool="{}",
        life=40,
        damage_dealt=22,
        commanders=(CommanderStatus(ATRAXA, (7, 0, 0), 2),),
        change=41,
        mulligans=0,
        result=None,
        notices=(),
    )
    return replace(summary, **changes)


def outcome_of(situation: Situation, result: Applied | Refusal | Resent) -> Outcome:
    """The outcome a use case would return for a domain result on the situation's game."""
    if isinstance(result, Refusal):
        status = Status.ERROR if result.errors else Status.REJECTED
        return Outcome(
            status,
            Refused(result.errors, result.checks),
            game=summarize(situation.game, situation.deck, TESTED),
        )
    game = result.game
    status = Status.CHOICE if game.status is GameStatus.PENDING_CHOICE else Status.OK
    return Outcome(
        status, result.summary, result.events, game=summarize(game, situation.deck, TESTED)
    )
