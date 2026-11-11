"""Combat in a built contested game, as the seats would play it.

situation = a_duel(attackers=("Wind Drake",), blockers=("Llanowar Elves",))
at_blocks(situation, attackers=["Wind Drake"])
refused = blocking(situation, S2, {"Llanowar Elves": "Wind Drake"})

Seat 1 is the active seat and attacks; the seat a `blocks` choice is addressed to answers it.
Calls are made through each domain operation with untyped arguments, so that a test may pass
an argument the operation does not take yet and fail for that reason alone.
"""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game.model import CardInstance
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.stack.passing import pass_
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, acted
from tests.support.builders import Situation, a_game


def a_duel(
    *,
    attackers: tuple[str, ...],
    blockers: tuple[str, ...] = ("Llanowar Elves",),
    attacking_seat_also: tuple[str, ...] = (),
    blocking_seat_also: tuple[str, ...] = (),
    attacking_seat_hand: tuple[str, ...] = (),
    seats: int = 2,
) -> Situation:
    """Seat 1's first main step: it controls `attackers` (and `attacking_seat_also`) and holds
    `attacking_seat_hand`, and every other seat controls `blockers` (and
    `blocking_seat_also`)."""
    builder: Any = a_game().with_battlefield(*attackers, *attacking_seat_also)
    if attacking_seat_hand:
        builder = builder.with_hand(*attacking_seat_hand)
    for _ in range(seats - 1):
        builder = builder.and_an_opposing_seat()
        if blockers or blocking_seat_also:
            builder = builder.with_battlefield(*blockers, *blocking_seat_also)
    situation: Situation = builder.build()
    return situation


def attacking(situation: Situation, seat: SeatNumber = S1, **arguments: object) -> Any:
    """`attack` as `seat`, with these arguments; the result, applied or not."""
    operate: Any = attack
    return operate(situation.game, situation.deck, seat, **arguments)


def attacked(situation: Situation, **arguments: object) -> Situation:
    """Seat 1 declares the attack, and every seat its window asks passes."""
    acted(situation, attacking(situation, **arguments))
    while situation.game.window is not None and situation.game.window.asking is not None:
        acted(situation, pass_(situation.game, situation.deck, situation.game.window.asking))
    return situation


def advanced(situation: Situation, to: str, seat: SeatNumber = S1) -> Applied:
    return acted(situation, advance(situation.game, situation.deck, seat, to=to))


def at_blocks(situation: Situation, **arguments: object) -> Situation:
    """Seat 1 declares the attack, and the game enters declare blockers, asking for blocks."""
    attacked(situation, **arguments)
    advanced(situation, "declare_blockers")
    return situation


def blocking(situation: Situation, seat: SeatNumber, blocks: object, **more: object) -> Any:
    """`seat` answers the oldest waiting `blocks` choice; the result, applied or not."""
    operate: Any = choose
    choice = situation.game.pending[0].choice_id
    return operate(situation.game, situation.deck, seat, choice_id=choice, blocks=blocks, **more)


def blocked(situation: Situation, seat: SeatNumber, blocks: object, **more: object) -> Applied:
    """`seat` answers its `blocks` choice, and the answer is applied."""
    return acted(situation, blocking(situation, seat, blocks, **more))


def stating_trample(situation: Situation, trample: object, **more: object) -> Any:
    """Seat 1 states trample damage with `attack`; the result, applied or not."""
    return attacking(situation, trample=trample, **more)


def immediately(situation: Situation, delta: object, seat: SeatNumber = S1) -> Applied:
    """`seat` records an immediate effect, and it is applied."""
    result = effect(
        situation.game, situation.deck, seat, source="a test effect", delta=delta, immediate=True
    )
    return acted(situation, result)


def card_of(situation: Situation, name: str, controller: SeatNumber) -> CardInstance:
    return next(c for c in situation.game.cards if c.name == name and c.controller == controller)
