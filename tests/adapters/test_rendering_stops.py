"""What an advance that stopped short says: why, and what to send next with `after`."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.events import AdvanceStopped, StepsEntered, StopReason
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import a_game

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
S1 = SeatNumber(1)


def stopped(reason: StopReason, step: Step, to: Step, *, contested: bool = True) -> str:
    builder: Any = a_game().in_step(step)
    if contested:
        builder = builder.and_an_opposing_seat()
    situation = builder.build()
    situation.game.change = 7
    summary = summarize(situation.game, situation.deck, S1)
    seat = S1 if contested else None
    event = AdvanceStopped(reason, step, to, 1)
    outcome = Outcome(Status.OK, StepsEntered(()), (event,), summary, seat=seat)
    return TextRenderer().render("advance", outcome).response


# @spec TURN-046
def test_an_advance_stopped_for_a_reminder_says_to_send_it_again_with_after() -> None:
    text = stopped(StopReason.REMINDER, Step.UPKEEP, Step.MAIN1)
    assert 'Send advance(to="main1", after=7) again to continue.' in text


# @spec TURN-046
def test_an_advance_stopped_for_a_discard_says_what_to_send_with_after() -> None:
    text = stopped(StopReason.DISCARD, Step.END, Step.MAIN1, contested=False)
    assert 'advance(to="main1", discard=[1 card from hand], after=7)' in text


# @spec TURN-046
@NOT_BUILT
def test_an_advance_stopped_for_blocks_says_what_to_send_once_they_are_declared_and_after() -> None:
    text = stopped(StopReason.BLOCKS, Step.DECLARE_BLOCKERS, Step.MAIN2)
    (line,) = [line for line in text.splitlines() if line.startswith("Stopped at")]
    assert 'advance(to="main2")' in line
    assert "after" in line
