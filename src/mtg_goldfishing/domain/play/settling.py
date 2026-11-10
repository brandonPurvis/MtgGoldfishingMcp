"""What follows a change that may have ended a wait: a look at a hand that was waiting for the
asks of its delta opens once no choice waits, and the turn of an eliminated active seat ends
once nothing waits on it."""

from __future__ import annotations

from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, GameStatus
from mtg_goldfishing.domain.play.delta import open_hand_look
from mtg_goldfishing.domain.turn import Walk, pass_the_turn


# @spec PLAY-116, TURN-037, TURN-038, TURN-062, GAME-136
def settle(game: Game, decks: Decks) -> Walk:
    """Open the looks at hands that waited for answers, when no pending choice is left; then,
    when the active seat has been eliminated and nothing waits, end its turn: every mana pool
    empties and the next seat still in the game begins its turn, or, with no seat left, no
    turn begins."""
    walk = Walk()
    if not game.pending and game.hand_looks:
        looks, game.hand_looks = game.hand_looks, []
        for look in looks:
            walk.events.extend(open_hand_look(game, look))
    if game.status is GameStatus.PENDING_CHOICE and not game.pending:
        game.status = GameStatus.ACTIVE
    if (
        game.contested
        and game.status is GameStatus.ACTIVE
        and game.active is not None
        and not game.active_seat.in_game
        and not game.pending
    ):
        pass_the_turn(game, decks, walk)
    return walk
