"""The change number shared by every seat: a resend is recognised against the sending seat's
own most recent change, even when other seats have changed the game since."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.events import AlreadyApplied
from mtg_goldfishing.domain.game.calls import accept_change, follow_change
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.results import Refusal, Resent
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.support.acting import S1, S2, S3
from tests.support.builders import Situation, a_game

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
TAKE_A_MULLIGAN = {"keep": False}


def three_seats_in_mulligans() -> Situation:
    builder: Any = a_game().in_mulligan()
    for number in (1, 2, 3):
        if number > 1:
            builder = builder.and_an_opposing_seat()
        builder = builder.with_hand(*["Island"] * 7).with_library(*["Forest"] * 14)
    return builder.build()


def mulliganed(situation: Situation, seat: SeatNumber) -> None:
    """The seat takes a mulligan, sent with the change number it saw."""
    result = mulligan(situation.game, situation.deck, seat, keep=False)
    arguments = {**TAKE_A_MULLIGAN, "after": situation.game.change}
    applied = accept_change(result, seat, "mulligan", arguments)  # type: ignore[arg-type]
    situation.game = applied.game


# @spec GAME-126
def test_a_seat_s_resend_is_recognised_after_other_seats_have_changed_the_game() -> None:
    situation = three_seats_in_mulligans()
    mulliganed(situation, S1)
    mulliganed(situation, S2)
    mulliganed(situation, S3)
    followed = follow_change(situation.game, S1, "mulligan", {**TAKE_A_MULLIGAN, "after": 0}, 0)
    assert isinstance(followed, Resent)
    assert type(followed.summary).__name__ == "MulliganTaken"


# @spec GAME-126
@NOT_BUILT
def test_a_resend_says_the_change_number_the_seat_s_change_was_applied_as() -> None:
    situation = three_seats_in_mulligans()
    mulliganed(situation, S1)
    mulliganed(situation, S2)
    followed = follow_change(situation.game, S1, "mulligan", {**TAKE_A_MULLIGAN, "after": 0}, 0)
    assert isinstance(followed, Resent)
    (applied,) = [event for event in followed.events if isinstance(event, AlreadyApplied)]
    assert applied.change == 1


# @spec GAME-127
def test_repeating_another_seat_s_change_with_a_stale_after_is_an_error_naming_the_change() -> None:
    situation = three_seats_in_mulligans()
    mulliganed(situation, S1)
    mulliganed(situation, S2)
    followed = follow_change(situation.game, S3, "mulligan", {**TAKE_A_MULLIGAN, "after": 1}, 1)
    assert isinstance(followed, Refusal)
    assert [(error.kind.value, error.number) for error in followed.errors] == [("stale_change", 2)]
