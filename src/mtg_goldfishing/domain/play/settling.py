"""What follows a change that may have ended a wait: a look at a hand that was waiting for the
asks of its delta opens once no choice waits; the open response window goes on asking; and the
turn of an eliminated active seat ends once nothing waits on it."""

from __future__ import annotations

from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, GameStatus
from mtg_goldfishing.domain.game.waiting import waiting_reminders
from mtg_goldfishing.domain.play.delta import open_hand_look
from mtg_goldfishing.domain.stack.windows import go_on
from mtg_goldfishing.domain.turn import Walk, pass_the_turn


def _open_hand_looks(game: Game, walk: Walk) -> None:
    if not game.pending and game.hand_looks:
        looks, game.hand_looks = game.hand_looks, []
        for look in looks:
            walk.events.extend(open_hand_look(game, look))


def _nothing_waits(game: Game) -> bool:
    return (
        not game.pending and not game.stack and game.window is None and not waiting_reminders(game)
    )


# @spec PLAY-116, TURN-037, TURN-038, TURN-062, GAME-136, STACK-071
def settle(game: Game, decks: Decks) -> Walk:
    """Open the looks at hands that waited for answers, when no pending choice is left; go on
    with the open response window's asking; then, when the active seat has been eliminated
    and nothing waits — no pending choice, no item on the stack, no open window — end its
    turn: every mana pool empties and the next seat still in the game begins its turn, or,
    with no seat left, no turn begins."""
    walk = Walk()
    _open_hand_looks(game, walk)
    if game.contested:
        walk.events.extend(go_on(game, decks))
        _open_hand_looks(game, walk)
    if game.status is GameStatus.PENDING_CHOICE and not game.pending:
        game.status = GameStatus.ACTIVE
    if (
        game.contested
        and game.status is GameStatus.ACTIVE
        and game.active is not None
        and not game.active_seat.in_game
        and _nothing_waits(game)
    ):
        pass_the_turn(game, decks, walk)
    return walk
