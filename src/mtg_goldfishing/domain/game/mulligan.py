"""`mulligan`: keep the opening hand, or shuffle it away and draw seven more."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    CheckKind,
    Error,
    ErrorKind,
    Event,
    FailedCheck,
    HandKept,
    MulliganTaken,
)
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import OPENING_HAND, Destination, Game, GameStatus, Zone
from mtg_goldfishing.domain.game.movement import draw
from mtg_goldfishing.domain.game.naming import resolve
from mtg_goldfishing.domain.game.results import Applied, Problems, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.shuffling import shuffle_library
from mtg_goldfishing.domain.turn import Walk, begin_turn


def cards_to_bottom(mulligans: int) -> int:
    """The first mulligan is free: after k mulligans, k - 1 cards go to the bottom, at most 7."""
    return min(OPENING_HAND, max(0, mulligans - 1))


# @spec GAME-151
def _take_mulligan(game: Game, seat: SeatNumber) -> Applied:
    """The seat's hand to the bottom of its library in instance order, a shuffle, seven more."""
    taking = game.seat(seat)
    for card in game.hand_of(seat):
        game.put(card, Destination.LIBRARY_BOTTOM)
    shuffle_library(game, seat)
    draw(game, seat, OPENING_HAND)
    taking.mulligans += 1
    hand = tuple(c.name for c in game.hand_of(seat))
    return Applied(game, MulliganTaken(taking.mulligans, hand))


def _start(game: Game, decks: Decks) -> Walk:
    """Start a game every seat has kept: the first seat in turn order still in the game
    takes the first turn, through its untap, upkeep and draw steps to its first main step,
    as an advance to `main1` would; in a contested game it stops where a reminder stops it."""
    game.status = GameStatus.ACTIVE
    game.active = next(seat.number for seat in game.seats if seat.in_game)
    walk = Walk()
    begin_turn(game, decks, walk, stopping=game.contested)
    return walk


# @spec GAME-021, GAME-022, GAME-023, GAME-024, GAME-025, GAME-026, GAME-027, GAME-028
# @spec GAME-103, GAME-105, APP-031, GAME-102, GAME-106
def mulligan(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    keep: object,
    bottom: object = None,
    override: str | None = None,
    decks: Decks | None = None,
) -> Result:
    """Take a mulligan or keep, as the calling seat. When the last seat still in the game
    keeps, the game starts. `decks` gives each seat's deck; omitted, every seat plays `deck`.
    """
    if not isinstance(keep, bool):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="keep"))
    if bottom is not None and not (
        isinstance(bottom, list) and all(isinstance(name, str) for name in bottom)
    ):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="bottom"))
    changed = game.copy()
    if not keep:
        if bottom is not None:
            return Refusal.error(Error(ErrorKind.BOTTOM_WITHOUT_KEEP))
        return _take_mulligan(changed, seat)
    names: list[str] = list(bottom or [])
    found = resolve(changed, deck, seat, names, [Zone.HAND])
    if isinstance(found, Error):
        return Refusal.error(Error(ErrorKind.BOTTOM_NOT_IN_HAND, subject=found.subject))
    problems = Problems()
    keeping = changed.seat(seat)
    required = cards_to_bottom(keeping.mulligans)
    if len(names) != required:
        problems.add(FailedCheck(CheckKind.BOTTOM_COUNT, number=len(names), expected=required))
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    for card in found[0]:
        changed.put(card, Destination.LIBRARY_BOTTOM)
    keeping.kept = True
    summary = HandKept(
        tuple(c.name for c in found[0]), tuple(c.name for c in changed.hand_of(seat))
    )
    if not all(other.kept for other in changed.seats if other.in_game):
        return Applied(changed, summary, (judged,) if judged is not None else ())
    walk = _start(changed, decks or Decks.everyone_playing(changed, deck))
    events: list[Event] = [walk.summary]
    if judged is not None:
        events.append(judged)
    events.extend(walk.events)
    return Applied(changed, summary, tuple(events))
