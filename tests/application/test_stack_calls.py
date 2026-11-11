"""`pass` and the stack through the use cases: the change number and resends of `pass`, and the
log entries of a call that stacks an item and of the call that resolves it."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Answer, Status
from tests.support.builders import a_game
from tests.support.service import GAME_ID, ServiceHarness, a_service

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M4: not built")


def holding_two_seats() -> ServiceHarness:
    """Seat 1's turn: S1 holds Lightning Bolt with a Mountain; S2 has an untapped Island."""
    harness = a_service(renderer=TextRenderer())
    builder: Any = a_game().with_hand("Lightning Bolt").with_battlefield("Mountain")
    harness.holding(builder.and_an_opposing_seat().with_battlefield("Island").build())
    return harness


def call_as(harness: ServiceHarness, seat: int, tool: str, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME_ID, seat)
    method = "pass_" if tool == "pass" else tool
    answer: Answer = getattr(harness.service, method)({"game_id": seat_id, **arguments})
    return answer


def bolt(harness: ServiceHarness) -> Answer:
    return call_as(harness, 1, "play", card="Lightning Bolt", delta={"damage": {"2": 3}})


# @spec STACK-055, TOOL-032
@NOT_BUILT
def test_a_pass_with_a_stale_after_is_an_error() -> None:
    harness = holding_two_seats()
    bolt(harness)
    change = harness.game().change

    answer = call_as(harness, 2, "pass", after=change - 1)

    assert answer.outcome.status is Status.ERROR
    assert harness.game().change == change


# @spec STACK-055, TOOL-032
@NOT_BUILT
def test_a_pass_with_the_current_after_is_applied() -> None:
    harness = holding_two_seats()
    bolt(harness)
    change = harness.game().change

    answer = call_as(harness, 2, "pass", after=change)

    assert answer.outcome.status is Status.OK
    assert harness.game().change == change + 1
    assert harness.game().seat(harness.game().seats[1].number).life == 37


# @spec STACK-055
@NOT_BUILT
def test_a_pass_sent_twice_is_applied_once() -> None:
    harness = holding_two_seats()
    bolt(harness)
    change = harness.game().change
    first = call_as(harness, 2, "pass", after=change)

    again = call_as(harness, 2, "pass", after=change)

    assert harness.game().change == change + 1
    assert again.response.splitlines()[0] == first.response.splitlines()[0]


# @spec REC-032, REC-034, REC-035
@NOT_BUILT
def test_the_entry_that_stacked_an_item_stays_as_it_was_when_another_call_resolves_it() -> None:
    harness = holding_two_seats()
    bolt(harness)
    stacking = harness.records().entries[-1]

    call_as(harness, 2, "pass")

    entries = harness.records().entries
    assert entries[-2] == stacking
    contested: Any = entries[-1].contested
    assert [resolved.item for resolved in contested.resolved] == ["s1"]
    assert stacking.contested is not None
    assert stacking.contested.stacked == "s1"  # type: ignore[attr-defined]
