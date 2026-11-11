"""`end_game`: the agent's result, trusted."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, GameEnded
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, GameResult, GameStatus, Result
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.records.snapshots import take_snapshot


# @spec GAME-045, GAME-046, GAME-047, REC-012, REC-070, APP-031
def end_game(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    result: object,
    notes: object = None,
    decks: Decks | None = None,
) -> Applied | Refusal:
    """End the game with the tested seat's result.

    A turn in progress without a snapshot gets one now, describing the active seat with its
    own deck (`decks` gives each seat's; omitted, every seat plays `deck`); during mulligans
    no turn has begun, so none is written.
    """
    del seat  # in a goldfish game the only seat, the tested seat, is the one that ends it
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
    ended.pending = []
    ended.declared_attack = None
    active_deck = deck
    if ended.active is not None:
        active_deck = (decks or Decks.everyone_playing(ended, deck)).of(ended.active)
    snapshot = take_snapshot(ended, active_deck)
    ended.status = GameStatus.ENDED
    ended.result = Result(outcome, notes or "")
    return Applied(
        ended,
        GameEnded(outcome.value, notes or ""),
        snapshots=(snapshot,) if snapshot else (),
    )
