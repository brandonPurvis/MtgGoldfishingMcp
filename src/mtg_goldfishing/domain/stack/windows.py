"""Response windows: asking the seats one at a time in turn order whether they respond,
passing automatically for a seat with no untapped permanents, resolving the top item once
every other seat has passed, and closing a window once everyone has passed on an empty stack.

The asking waits for what comes first: while a pending choice waits, or a reminder waits for
a seat other than the active seat, no seat is asked, no automatic pass is made and nothing
resolves.
"""

from __future__ import annotations

from dataclasses import replace

from mtg_goldfishing.domain.events import AutomaticPass, Event
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, Window, WindowKind
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.waiting import waiting_reminders
from mtg_goldfishing.domain.stack.items import has_untapped_permanent, top
from mtg_goldfishing.domain.stack.resolution import reach_resolution


# @spec STACK-038
def open_window(game: Game, kind: WindowKind) -> None:
    """Open a response window of kind `attack` or `end`; its asking begins from the seat after
    the active seat."""
    game.window = Window(kind)


def waits_on_others(game: Game) -> bool:
    """Whether the asking waits: a pending choice, or a reminder for a seat other than the
    active seat, is waiting."""
    return bool(game.pending) or bool(waiting_reminders(game))


def seats_asked(game: Game) -> list[SeatNumber]:
    """The seats the open window asks, in order: every seat still in the game other than the
    top item's controller, from the seat after it; with an empty stack, every seat other than
    the active seat, from the seat after it (none once the active seat has left the game)."""
    newest = top(game)
    if newest is not None:
        anchor = newest.controller
    elif game.active is not None and game.active_seat.in_game:
        anchor = game.active
    else:
        return []
    return [seat.number for seat in game.others_from(anchor) if seat.in_game]


# @spec STACK-014, STACK-015, STACK-034, STACK-035, STACK-036, STACK-037, STACK-039
# @spec STACK-040, STACK-041, STACK-046, STACK-049, STACK-060, STACK-062, STACK-070
# @spec STACK-071, STACK-084, STACK-083, TURN-066, STACK-042, STACK-047, STACK-048, STACK-090
def go_on(game: Game, decks: Decks) -> list[Event]:
    """Go on with the open window's asking as far as it goes without a seat's call: pass
    automatically for each seat about to be asked that has no untapped permanent (a seat
    already being asked stays asked, though it tapped its last permanent), resolve the top
    item once every other seat has passed on it, and close an `attack` or `end` window once
    every other seat has passed with the stack empty. Stop at the first seat that must be
    asked, which the window then names, or when the asking must wait."""
    events: list[Event] = []
    while game.window is not None and not waits_on_others(game):
        window = game.window
        if window.kind is WindowKind.STACK and not game.stack:
            game.window = None
            break
        still_to_ask = [seat for seat in seats_asked(game) if seat not in window.passed]
        if not still_to_ask:
            if game.stack:
                events.extend(reach_resolution(game, decks))
                continue
            game.window = None
            break
        seat = still_to_ask[0]
        if seat == window.asking or has_untapped_permanent(game, seat):
            game.window = replace(window, asking=seat)
            break
        newest = top(game)
        events.append(
            AutomaticPass(seat, newest.id if newest is not None else None, window.kind.value)
        )
        game.window = replace(window, asking=None, passed=(*window.passed, seat))
    if game.window is not None and waits_on_others(game):
        game.window = replace(game.window, asking=None)
    return events
