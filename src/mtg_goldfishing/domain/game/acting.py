"""The seat to act: which seats the game is waiting on, and which calls it accepts from a seat.

In a goldfish game the only seat is always the seat to act, and what it may call depends on
the game's status alone. In a contested game one rule answers whose call it is.
"""

from __future__ import annotations

from mtg_goldfishing.domain.events import (
    Asked,
    AskedKind,
    Error,
    ErrorKind,
    GameHasEnded,
    SeatOut,
    SeatToAct,
    StillWaiting,
)
from mtg_goldfishing.domain.game.calls import check_accepted
from mtg_goldfishing.domain.game.model import Game, GameStatus
from mtg_goldfishing.domain.game.seats import SeatNumber

READS = ("get_state", "get_log", "wait")
"""Calls accepted from any seat, in any status."""

ANSWERS: dict[AskedKind, tuple[str, ...]] = {
    AskedKind.KEEP: ("mulligan",),
    AskedKind.CHOICE: ("choose",),
    AskedKind.TURN: ("play", "effect", "attack", "advance"),
}
"""The calls by which a seat to act does what it is asked."""


# @spec GAME-108, GAME-109, GAME-113, TURN-041, GAME-164
def seats_to_act(game: Game) -> Asked | None:
    """The seats the game is waiting on and what they are asked, in order of precedence:
    during mulligans every seat still in the game that has not kept; then the seat the
    oldest waiting pending choice is addressed to; otherwise the active seat.

    None when the game waits on no seat: it has ended, or no seat is left in it.
    """
    if game.status is GameStatus.ENDED:
        return None
    if game.status is GameStatus.MULLIGAN:
        keeping = tuple(seat.number for seat in game.seats if seat.in_game and not seat.kept)
        return Asked(keeping, AskedKind.KEEP) if keeping else None
    choice = game.waiting_choice
    if choice is not None:
        return Asked((choice.seat,), AskedKind.CHOICE, choice.kind)
    if game.active is None:
        return None
    return Asked((game.active,), AskedKind.TURN)


# @spec GAME-102, GAME-104, GAME-114, GAME-115, GAME-116, GAME-117, GAME-118, GAME-119
# @spec GAME-148, GAME-149, GAME-150, GAME-170, TURN-043, TURN-044, GAME-161, GAME-167
# @spec CMBT-028, CMBT-029, PLAY-106
def may_call(game: Game, seat: SeatNumber, tool: str) -> Error | None:
    """The error refusing a call from `seat` now, or None when the game accepts it.

    Reads are accepted from any seat at any time. Otherwise the first reason that applies
    refuses the call: the game has ended; the calling seat is eliminated (the tested seat
    may still end the game); the calling seat is not the seat to act, or is asked for
    another call than this one. The tested seat's `end_game` is accepted whatever the game
    is waiting on.
    """
    if not game.contested:
        return check_accepted(game, tool)
    if tool in READS:
        return None
    if game.status is GameStatus.ENDED:
        return check_accepted(game, tool)
    calling = game.seat(seat)
    if tool == "end_game" and calling.tested:
        return None
    if calling.eliminated:
        return Error(ErrorKind.SEAT_ELIMINATED, subject=tool, number=seat.value)
    if tool == "end_game":
        return None
    asked = seats_to_act(game)
    if asked is None or seat not in asked.seats:
        return Error(ErrorKind.NOT_YOUR_CALL, subject=tool, asked=asked)
    if tool not in ANSWERS[asked.kind]:
        return Error(ErrorKind.NOT_ACCEPTED_NOW, subject=tool, asked=asked)
    return None


# @spec APP-063, APP-064, APP-067, APP-074, APP-088, APP-089, GAME-114
def what_ends_a_wait(game: Game, seat: SeatNumber) -> SeatToAct | SeatOut | GameHasEnded | None:
    """Why a seat's `wait` returns now, or None while it goes on waiting: the game has
    ended, whatever the seat's state; the seat is eliminated; or it is a seat to act, with
    what it is asked. A goldfish game's only seat is always the seat to act."""
    if game.status is GameStatus.ENDED:
        return GameHasEnded()
    if game.seat(seat).eliminated:
        return SeatOut(seat)
    asked = seats_to_act(game)
    if asked is None or seat not in asked.seats:
        return None
    return SeatToAct(Asked((seat,), asked.kind, asked.choice))


# @spec APP-066
def still_waiting(game: Game) -> StillWaiting:
    """A `wait` that timed out: the seats the game is waiting on, every seat still to keep
    during mulligans, and what they are asked."""
    return StillWaiting(seats_to_act(game))
