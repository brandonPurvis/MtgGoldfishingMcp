"""What the seats to act are asked, and since which change they have been asked it.

The seats to act are the seats the game is waiting on. A contested game keeps the change
number since which they have been asked what they are asked now, so that a seat that waits
can be told how long; the time itself is the application's to find, since the domain reads
no clock.
"""

from __future__ import annotations

from dataclasses import dataclass

from mtg_goldfishing.domain.events import Asked, AskedKind
from mtg_goldfishing.domain.game.model import Game, GameStatus
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.waiting import waiting_reminders
from mtg_goldfishing.domain.steps import Step


def _responding(game: Game) -> Asked | None:
    """The seat an open window is asking, and about which item, when it asks one."""
    window = game.window
    if window is None or window.asking is None:
        return None
    newest = game.stack[-1] if game.stack else None
    return Asked(
        (window.asking,),
        AskedKind.RESPOND,
        window=window.kind.value,
        item=newest.id if newest is not None else None,
        source=newest.source if newest is not None else None,
        controller=newest.controller if newest is not None else None,
    )


# @spec GAME-108, GAME-109, GAME-111, GAME-112, GAME-113, TURN-041, GAME-164, TURN-051
# @spec TURN-053, TURN-054, TURN-067, STACK-042, STACK-044, STACK-045, STACK-056
def seats_to_act(game: Game) -> Asked | None:
    """The seats the game is waiting on and what they are asked, in order of precedence:
    during mulligans every seat still in the game that has not kept; then the seat the
    oldest waiting pending choice is addressed to; then a seat other than the active seat
    with reminders waiting, the first in turn order after the active seat; then the seat an
    open response window is asking; otherwise the active seat.

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
    reminded = waiting_reminders(game)
    if reminded:
        seat, reminders = reminded[0]
        cards = tuple(dict.fromkeys(reminder.name for reminder in reminders))
        return Asked((seat,), AskedKind.TRIGGER, step=game.step, cards=cards)
    responding = _responding(game)
    if responding is not None:
        return responding
    if game.active is None:
        return None
    return Asked((game.active,), AskedKind.TURN)


@dataclass(frozen=True)
class Question:
    """What the seats to act are asked, as far as it decides whether they are asked anew:
    the seats and the kind, and what the question is about within its kind."""

    seats: tuple[SeatNumber, ...]
    kind: AskedKind
    choice_id: str | None = None
    step: Step | None = None
    reminded: tuple[str, ...] = ()
    window: str | None = None
    item: str | None = None
    turn: int | None = None


# @spec GAME-183
def question(game: Game) -> Question | None:
    """What the seats to act are asked now, or None when the game waits on no seat.

    Within one kind a question is about: the pending choice's choice id; the reminder's step
    and the permanents reminded; the response window's kind and the stack item it asks
    about; for a seat's turn, the table turn.
    """
    asked = seats_to_act(game)
    if asked is None:
        return None
    match asked.kind:
        case AskedKind.CHOICE:
            choice = game.waiting_choice
            return Question(asked.seats, asked.kind, choice_id=choice.choice_id if choice else None)
        case AskedKind.TRIGGER:
            reminded = next(
                (reminders for seat, reminders in waiting_reminders(game) if seat in asked.seats),
                [],
            )
            ids = tuple(sorted(reminder.instance_id for reminder in reminded))
            return Question(asked.seats, asked.kind, step=asked.step, reminded=ids)
        case AskedKind.RESPOND:
            return Question(asked.seats, asked.kind, window=asked.window, item=asked.item)
        case AskedKind.TURN:
            return Question(asked.seats, asked.kind, turn=game.turn)
        case AskedKind.KEEP:
            return Question(asked.seats, asked.kind)


# @spec GAME-180, GAME-181, GAME-182, GAME-184, GAME-185
def follow_asked_since(before: Game | None, after: Game) -> None:
    """Keep the change since which the seats to act have been asked, once `after` has been
    counted as the game's next change; `before` is the game before it, None for the change
    that creates the game.

    A contested game is asked since the change that creates it; while it is in mulligans the
    change stays as it was; after any other change it becomes that change when the seats to
    act or what they are asked differ from before, and is kept otherwise. A goldfish game
    holds none.
    """
    if not after.contested:
        after.asked_since = None
        return
    if before is None:
        after.asked_since = after.change
        return
    if after.status is GameStatus.MULLIGAN:
        return
    if question(after) != question(before):
        after.asked_since = after.change
