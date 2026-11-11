"""`wait`: hold the call open until the calling seat has something to do. Changes nothing.

The game is loaded, and the call answered and recorded, only under the game's lock; while
the call waits it holds no lock, so the seats it waits on can act. It returns when the seat
is a seat to act, is eliminated, or the game has ended, and when its timeout passes. In a
goldfish game the only seat is always the seat to act, so `wait` returns at once.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from functools import partial

from mtg_goldfishing.application.outcome import Answer, Outcome, Status
from mtg_goldfishing.application.ports import SeatOfGame
from mtg_goldfishing.application.use_cases.arguments import malformed
from mtg_goldfishing.application.use_cases.handling import (
    Call,
    Ports,
    an_error,
    find_seat,
    load,
)
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.game.acting import still_waiting, what_ends_a_wait

TOOL = "wait"
DEFAULT_TIMEOUT = 30
SHORTEST_TIMEOUT = 1
LONGEST_TIMEOUT = 60


def _timeout(arguments: Mapping[str, object]) -> float | Error:
    """The seconds to wait: 30 when omitted; a number from 1 to 60, fractions included."""
    value = arguments.get("timeout")
    if value is None:
        return DEFAULT_TIMEOUT
    if isinstance(value, bool) or not isinstance(value, int | float):
        return malformed("timeout")
    if not SHORTEST_TIMEOUT <= value <= LONGEST_TIMEOUT:
        return Error(
            ErrorKind.BAD_TIMEOUT,
            subject=str(value),
            number=SHORTEST_TIMEOUT,
            expected=LONGEST_TIMEOUT,
        )
    return value


# @spec APP-063, APP-064, APP-065, APP-066, APP-067, APP-068, APP-069, APP-070, APP-071
# @spec APP-072, APP-073, APP-074, APP-075, APP-078, APP-088, APP-089, APP-090, APP-091
# @spec REC-026, REC-053, GAME-114, APP-096
def wait(ports: Ports, arguments: Mapping[str, object]) -> Answer:
    """Wait until the calling seat has something to do, and say what it is.

    Each look at the game is made under its lock: if the seat is a seat to act, is
    eliminated, or the game has ended, the call is answered so; if the time is up, it is
    answered with the seats the game still waits on. Otherwise the lock is released and the
    call waits for a change after the one it saw, for what remains of its timeout. A
    `timeout` out of range is an error about the game found. Nothing is saved but the call
    record, and nothing is announced.
    """
    game_id = arguments.get("game_id")
    if not isinstance(game_id, str):
        call = Call(ports, TOOL, arguments, None)
        return call.guarded(lambda: call.finish(an_error(malformed("game_id"), None)))
    call = Call(ports, TOOL, arguments, game_id)

    def answer() -> Answer:
        found = find_seat(ports.games, game_id)
        if found is None:
            return call.finish(an_error(Error(ErrorKind.UNKNOWN_GAME, subject=game_id), None))
        call.game_id = found.game_id
        return _waiting(call, found, arguments)

    return call.guarded(answer)


def _waiting(call: Call, found: SeatOfGame, arguments: Mapping[str, object]) -> Answer:
    ports = call.ports
    deadline: datetime | None = None
    timed_out = False
    while True:
        with ports.locks.hold(found.game_id):
            looked = call.guarded(partial(_look, call, found, arguments, deadline, timed_out))
        if isinstance(looked, Answer):
            return looked
        seen, deadline, remaining = looked
        timed_out = not ports.changes.wait_for_change(found.game_id, seen, remaining)


def _look(
    call: Call,
    found: SeatOfGame,
    arguments: Mapping[str, object],
    deadline: datetime | None,
    timed_out: bool,
) -> Answer | tuple[int, datetime, float]:
    """One look at the game, under its lock: the answer when the wait is over, else the
    change number seen, the deadline and the seconds left to wait for a later change."""
    loaded = load(call, found)
    timeout = _timeout(arguments)
    if isinstance(timeout, Error):
        return call.finish(an_error(timeout, loaded.summary))
    now = call.ports.clock.now()
    deadline = deadline or now + timedelta(seconds=timeout)
    ended = what_ends_a_wait(loaded.game, loaded.seat)
    if ended is not None:
        return call.finish(Outcome(Status.OK, ended, (), loaded.summary))
    remaining = (deadline - now).total_seconds()
    if timed_out or remaining <= 0:
        table = loaded.summary.table
        waiting = replace(
            still_waiting(loaded.game), time_asked=table.time_asked if table else None
        )
        return call.finish(Outcome(Status.OK, waiting, (), loaded.summary))
    return loaded.game.change, deadline, remaining
