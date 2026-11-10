"""Acting as the seats of a built contested game, and reading what each call returned.

situation = a_game().and_an_opposing_seat().with_hand("Island").build()
asked = acted(situation, effect(situation.game, situation.deck, S1, source="x", delta=...))
"""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from tests.support.builders import Situation

S1, S2, S3, S4 = SeatNumber(1), SeatNumber(2), SeatNumber(3), SeatNumber(4)


def acted(situation: Situation, result: object) -> Applied:
    """The applied result of a call; the situation then holds the changed game."""
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def errors_of(result: object) -> list[Any]:
    assert isinstance(result, Refusal), result
    assert result.errors, result
    return list(result.errors)


def error_kinds(result: object) -> list[str]:
    return [error.kind.value for error in errors_of(result)]


def check_kinds(result: object) -> list[str]:
    assert isinstance(result, Refusal), result
    assert not result.errors, result
    return [check.kind.value for check in result.checks]


def events_named(result: Applied, name: str) -> list[Any]:
    """The events of an applied call of one event type, by the type's name."""
    return [event for event in (result.summary, *result.events) if type(event).__name__ == name]


def choice_ids(situation: Situation) -> list[str]:
    return [choice.choice_id for choice in situation.game.pending]
