"""`end_game`: the tested seat's result, trusted; from an opposing seat, a concession."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    EliminationCause,
    Error,
    ErrorKind,
    Event,
    GameEnded,
    ItemRemoved,
)
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.elimination import eliminate
from mtg_goldfishing.domain.game.model import Game, GameResult, GameStatus, Result
from mtg_goldfishing.domain.game.mulligan import start_first_turn
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.settling import settle
from mtg_goldfishing.domain.records.model import TurnSnapshot
from mtg_goldfishing.domain.records.snapshots import take_snapshot


# @spec GAME-131, GAME-158, GAME-159, GAME-161
def _concede(game: Game, decks: Decks, seat: SeatNumber, notes: str) -> Applied:
    """An opposing seat leaves the game; the game goes on without it.

    During mulligans, a concession that leaves no seat still to keep starts the game; once
    the game has started, a conceding active seat's turn ends when nothing waits on it.
    """
    conceded = game.copy()
    (summary, *events) = eliminate(conceded, seat, EliminationCause.CONCEDE, notes)
    reported: list[Event] = list(events)
    snapshots: tuple[TurnSnapshot, ...] = ()
    if conceded.status is GameStatus.MULLIGAN:
        if all(other.kept for other in conceded.seats if other.in_game):
            walk = start_first_turn(conceded, decks)
            reported = [walk.summary, *reported, *walk.events]
    else:
        walk = settle(conceded, decks)
        if walk.entered:
            reported.append(walk.summary)
        reported.extend(walk.events)
        snapshots = tuple(walk.snapshots)
    return Applied(conceded, summary, tuple(reported), snapshots)


# @spec GAME-045, GAME-046, GAME-047, REC-012, REC-070, APP-031, GAME-148, GAME-149, REC-050
# @spec GAME-147, STACK-033
def end_game(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    result: object,
    notes: object = None,
    decks: Decks | None = None,
) -> Applied | Refusal:
    """End the game with the tested seat's result, whatever it is waiting on; from an
    opposing seat of a contested game, concede instead.

    A turn in progress without a snapshot gets one now, describing the active seat with its
    own deck (`decks` gives each seat's; omitted, every seat plays `deck`); during mulligans
    no turn has begun, so none is written.
    """
    every = decks or Decks.everyone_playing(game, deck)
    outcome = GameResult(result) if result in {r.value for r in GameResult} else None
    if outcome is None:
        return Refusal.error(
            Error(
                ErrorKind.BAD_RESULT, subject=str(result), names=tuple(r.value for r in GameResult)
            )
        )
    if notes is not None and not isinstance(notes, str):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="notes"))
    if not game.seat(seat).tested:
        return _concede(game, every, seat, notes or "")
    ended = game.copy()
    removed = tuple(ItemRemoved(item.id, item.controller, item.source) for item in ended.stack)
    ended.pending = []
    ended.hand_looks = []
    ended.declared_attack = None
    ended.stack = []
    ended.window = None
    active_deck = deck
    if ended.active is not None:
        active_deck = every.of(ended.active)
    snapshot = take_snapshot(ended, active_deck)
    ended.status = GameStatus.ENDED
    ended.result = Result(outcome, notes or "")
    return Applied(
        ended,
        GameEnded(outcome.value, notes or ""),
        removed,
        snapshots=(snapshot,) if snapshot else (),
    )
