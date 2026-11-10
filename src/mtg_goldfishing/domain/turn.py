"""Moving through the steps of a turn: `advance`.

Entering a step performs its automatic action. Leaving any step empties the mana pool.
An advance stops short of its target when a step it enters has a reminder, or before
cleanup when cards must be discarded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mtg_goldfishing.domain.combat.damage import deal_combat_damage
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    CardsDiscarded,
    CheckKind,
    ChecksOverridden,
    EnteredStep,
    Error,
    ErrorKind,
    Event,
    FailedCheck,
    ReminderIssued,
    StepsEntered,
    StopReason,
)
from mtg_goldfishing.domain.game.cards_in_play import face_name, reading_of
from mtg_goldfishing.domain.game.model import (
    MAXIMUM_HAND,
    CardInstance,
    Destination,
    Game,
    Reminder,
    TurnStats,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw, move
from mtg_goldfishing.domain.game.naming import resolve
from mtg_goldfishing.domain.game.notices import examine_turn_limit
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.mana import ManaPool
from mtg_goldfishing.domain.payment.potential import mana_available
from mtg_goldfishing.domain.records.model import TurnSnapshot
from mtg_goldfishing.domain.records.snapshots import take_snapshot
from mtg_goldfishing.domain.steps import Step


@dataclass
class Walk:
    """What happened while the game moved through steps."""

    entered: list[EnteredStep] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    snapshots: list[TurnSnapshot] = field(default_factory=list)
    reminded: bool = False

    @property
    def summary(self) -> StepsEntered:
        return StepsEntered(tuple(self.entered))


def _remind(game: Game, deck: LoadedDeck, step: Step) -> ReminderIssued | None:
    counts: dict[str, int] = {}
    for card in game.battlefield:
        if step in reading_of(deck, card).step_triggers:
            name = face_name(deck, card)
            counts[name] = counts.get(name, 0) + 1
            game.reminders.append(Reminder(card.id, name, step))
    if not counts:
        return None
    return ReminderIssued(step, tuple(counts.items()))


# @spec TURN-002, TURN-003, TURN-004, TURN-005, TURN-011, TURN-014
def enter_step(
    game: Game,
    deck: LoadedDeck,
    step: Step,
    walk: Walk,
    discard: Sequence[CardInstance] = (),
) -> None:
    """Leave the current step (emptying the pool) and enter `step`, doing its automatic action."""
    game.mana_pool = ManaPool()
    game.step = step
    if step is Step.UNTAP:
        game.turn += 1
        for card in game.battlefield:
            card.tapped = False
        game.land_drops_used = 0
        game.turn_stats = TurnStats()
        game.reminders = []
    walk.entered.append(EnteredStep(game.turn, step))
    if step is Step.UNTAP:
        walk.events.extend(examine_turn_limit(game))
    elif step is Step.DRAW and not (game.turn == 1 and not game.draw_first_turn):
        walk.events.extend(draw(game, 1))
    elif step is Step.MAIN1:
        game.turn_stats.mana_available = mana_available(game, deck)
    elif step is Step.COMBAT_DAMAGE:
        walk.events.extend(deal_combat_damage(game, deck))
    elif step is Step.CLEANUP:
        if discard:
            for card in discard:
                walk.events.extend(move(game, deck, card, Destination.GRAVEYARD))
            walk.events.append(CardsDiscarded(tuple(card.name for card in discard)))
        snapshot = take_snapshot(game, deck)
        if snapshot is not None:
            walk.snapshots.append(snapshot)
    reminder = _remind(game, deck, step)
    if reminder is not None:
        walk.events.append(reminder)
        walk.reminded = True


def _discard_list(value: object) -> list[str] | Error | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject="discard")


def _cleanup_discard(
    game: Game, deck: LoadedDeck, names: list[str], override: str | None
) -> tuple[list[CardInstance], FailedCheck | None] | Refusal:
    """The cards to discard, and the discard-count check an `override` overrode, if any."""
    excess = max(0, len(game.hand) - MAXIMUM_HAND)
    found = resolve(game, deck, names, [Zone.HAND])
    if isinstance(found, Error):
        return Refusal.error(Error(ErrorKind.DISCARD_NOT_IN_HAND, subject=found.subject))
    if len(found[0]) == excess:
        return found[0], None
    check = FailedCheck(CheckKind.DISCARD_COUNT, number=len(found[0]), expected=excess)
    if not override:
        return Refusal(checks=(check,))
    return found[0], check


# @spec TURN-001, TURN-006, TURN-007, TURN-008, TURN-009, TURN-010, TURN-012, TURN-013
# @spec TURN-015, TURN-016, TURN-017, TURN-018, TURN-019, TURN-020, TURN-021, TURN-022
# @spec TURN-023, TURN-024, TURN-025
def advance(
    game: Game,
    deck: LoadedDeck,
    *,
    to: object = None,
    discard: object = None,
    override: str | None = None,
) -> Result:
    """Move to the next step, or forward through every step to the next occurrence of `to`."""
    target: Step | None = None
    if to is not None:
        target = Step.named(to) if isinstance(to, str) else None
        if target is None:
            return Refusal.error(Error(ErrorKind.UNKNOWN_STEP, subject=str(to)))
    names = _discard_list(discard)
    if isinstance(names, Error):
        return Refusal.error(names)
    moved = game.copy()
    walk = Walk()
    entered_cleanup = False
    while True:
        upcoming = Step.UNTAP if moved.step is None else moved.step.next
        to_discard: list[CardInstance] = []
        if upcoming is Step.CLEANUP:
            excess = len(moved.hand) - MAXIMUM_HAND
            if names is None and excess > 0:
                check = FailedCheck(CheckKind.HAND_TOO_BIG, number=excess)
                if override:
                    walk.events.append(ChecksOverridden((check,), override))
                elif not walk.entered:
                    return Refusal(checks=(check,))
                else:
                    stopped_in = moved.step or Step.END
                    walk.events.append(
                        AdvanceStopped(StopReason.DISCARD, stopped_in, target, excess)
                    )
                    break
            if names is not None:
                chosen = _cleanup_discard(moved, deck, names, override)
                if isinstance(chosen, Refusal):
                    return chosen
                to_discard, overridden = chosen
                if overridden is not None and override:
                    walk.events.append(ChecksOverridden((overridden,), override))
            entered_cleanup = True
        enter_step(moved, deck, upcoming, walk, to_discard)
        if target is None or moved.step is target:
            break
        if walk.reminded:
            walk.events.append(AdvanceStopped(StopReason.REMINDER, upcoming, target))
            break
    if names is not None and not entered_cleanup:
        return Refusal.error(Error(ErrorKind.DISCARD_WITHOUT_CLEANUP))
    return Applied(moved, walk.summary, tuple(walk.events), tuple(walk.snapshots))


def walk_to(game: Game, deck: LoadedDeck, target: Step, walk: Walk) -> None:
    """Move a game (in place) forward to the next occurrence of a step, stopping for nothing."""
    while True:
        upcoming = Step.UNTAP if game.step is None else game.step.next
        enter_step(game, deck, upcoming, walk)
        if game.step is target:
            return


# @spec TURN-026
def return_to_declare_attackers(game: Game, deck: LoadedDeck, walk: Walk) -> None:
    """An additional combat: back to declare attackers in the same turn."""
    enter_step(game, deck, Step.DECLARE_ATTACKERS, walk)
