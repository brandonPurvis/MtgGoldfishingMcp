"""`end_game`: the agent's result, trusted."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, GameEnded
from mtg_goldfishing.domain.game.model import Game, GameResult, GameStatus, Result
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.records.snapshots import take_snapshot


# @spec GAME-045, GAME-046, GAME-047, REC-012
def end_game(
    game: Game, deck: LoadedDeck, *, result: object, notes: object = None
) -> Applied | Refusal:
    """End the game with the agent's result. A turn without a snapshot gets one now."""
    outcome = GameResult(result) if result in {r.value for r in GameResult} else None
    if outcome is None:
        return Refusal.error(
            Error(
                ErrorKind.BAD_RESULT, subject=str(result), names=tuple(r.value for r in GameResult)
            )
        )
    if notes is not None and not isinstance(notes, str):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="notes"))
    ended = game.copy()
    ended.pending_choice = None
    ended.declared_attack = None
    snapshot = take_snapshot(ended, deck)
    ended.status = GameStatus.ENDED
    ended.result = Result(outcome, notes or "")
    return Applied(
        ended,
        GameEnded(outcome.value, notes or ""),
        snapshots=(snapshot,) if snapshot else (),
    )
