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
from mtg_goldfishing.domain.game.model import OPENING_HAND, Destination, Game, GameStatus, Zone
from mtg_goldfishing.domain.game.movement import draw
from mtg_goldfishing.domain.game.naming import resolve
from mtg_goldfishing.domain.game.results import Applied, Problems, Refusal, Result
from mtg_goldfishing.domain.game.shuffling import shuffle_library
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import Walk, walk_to


def cards_to_bottom(mulligans: int) -> int:
    """The first mulligan is free: after k mulligans, k - 1 cards go to the bottom, at most 7."""
    return min(OPENING_HAND, max(0, mulligans - 1))


def _take_mulligan(game: Game) -> Applied:
    for card in game.hand:
        card.zone = Zone.LIBRARY
        game.library.append(card.id)
    shuffle_library(game)
    draw(game, OPENING_HAND)
    game.mulligans += 1
    return Applied(game, MulliganTaken(game.mulligans, tuple(c.name for c in game.hand)))


# @spec GAME-021, GAME-022, GAME-023, GAME-024, GAME-025, GAME-026, GAME-027, GAME-028
def mulligan(
    game: Game,
    deck: LoadedDeck,
    *,
    keep: object,
    bottom: object = None,
    override: str | None = None,
) -> Result:
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
        return _take_mulligan(changed)
    names: list[str] = list(bottom or [])
    found = resolve(changed, deck, names, [Zone.HAND])
    if isinstance(found, Error):
        return Refusal.error(Error(ErrorKind.BOTTOM_NOT_IN_HAND, subject=found.subject))
    problems = Problems()
    required = cards_to_bottom(changed.mulligans)
    if len(names) != required:
        problems.add(FailedCheck(CheckKind.BOTTOM_COUNT, number=len(names), expected=required))
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    for card in found[0]:
        changed.put(card, Destination.LIBRARY_BOTTOM)
    kept = tuple(c.name for c in changed.hand)
    changed.status = GameStatus.ACTIVE
    walk = Walk()
    walk_to(changed, deck, Step.MAIN1, walk)
    events: list[Event] = [walk.summary]
    if judged is not None:
        events.append(judged)
    events.extend(walk.events)
    return Applied(changed, HandKept(tuple(c.name for c in found[0]), kept), tuple(events))
