"""Reminders the game waits on: those issued to seats other than the active seat in the step
it is in, which a seat answers with an `effect` naming the permanent or passes on with `pass`.

A reminder for the active seat never makes the game wait.
"""

from __future__ import annotations

from mtg_goldfishing.domain.game.model import Game, Reminder
from mtg_goldfishing.domain.game.seats import SeatNumber


# @spec TURN-052, TURN-053, TURN-066
def waiting_reminders(game: Game) -> list[tuple[SeatNumber, list[Reminder]]]:
    """Each seat other than the active seat that the game waits on for its reminders of the
    current step and table turn, neither answered nor passed, with those reminders, in turn
    order from the seat after the active seat."""
    if not game.contested or game.active is None:
        return []
    waiting: list[tuple[SeatNumber, list[Reminder]]] = []
    for seat in game.others_from(game.active):
        if not seat.in_game:
            continue
        open_reminders = [
            reminder
            for reminder in seat.reminders
            if reminder.turn == game.turn
            and reminder.step is game.step
            and not reminder.answered
            and not reminder.passed
        ]
        if open_reminders:
            waiting.append((seat.number, open_reminders))
    return waiting
