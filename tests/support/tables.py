"""Contested tables for tests of the stack and response windows.

Seat 1's turn in table turn 5 (its own turn 3). Seat 1 has a Mountain, two Islands and two
Forests untapped; every other seat has two Islands and a Mountain untapped, so it is asked
when a window opens. Each describer is given the seat's builder and returns it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import GameBuilder, Situation, a_game

S1_LANDS = ("Mountain", "Island", "Island", "Forest", "Forest")
OTHER_LANDS = ("Island", "Island", "Mountain")

Describe = Callable[[GameBuilder], GameBuilder]


def same(builder: GameBuilder) -> GameBuilder:
    return builder


def a_table(
    *describers: Describe, step: Step = Step.MAIN1, active: int = 1, lands: bool = True
) -> Situation:
    """One seat for each describer, seat 1 first, each given its lands unless `lands` is
    false; seat `active`'s turn, in `step`."""
    builder: Any = a_game().in_step(step, turn=5).in_turn_of(active)
    for number, describe in enumerate(describers, start=1):
        if number > 1:
            builder = builder.and_an_opposing_seat()
        builder = builder.with_turns_taken(3 if number <= active else 2)
        if lands:
            builder = builder.with_battlefield(*(S1_LANDS if number == 1 else OTHER_LANDS))
        builder = describe(builder)
    situation: Situation = builder.build()
    return situation


def two_seats(first: Describe = same, second: Describe = same, **options: Any) -> Situation:
    return a_table(first, second, **options)


def three_seats(
    first: Describe = same, second: Describe = same, third: Describe = same, **options: Any
) -> Situation:
    return a_table(first, second, third, **options)


def card_of(situation: Situation, name: str, owner: SeatNumber) -> Any:
    """The lowest-numbered instance of a card name that a seat owns."""
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


def bolt_at(seat: int, damage: int = 3) -> dict[str, object]:
    """A delta dealing noncombat damage to one seat."""
    return {"damage": {str(seat): damage}}
