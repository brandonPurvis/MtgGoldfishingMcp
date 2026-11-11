"""Moving through the steps of a turn, and from one seat's turn to the next: `advance`.

Every step is a step of the active seat's turn. Entering a step performs its automatic
action. Leaving any step empties every seat's mana pool. An advance stops short of its
target when a step it enters has a reminder, or before cleanup when cards must be discarded.
In a contested game an advance ends when the active seat leaves cleanup, and the next seat's
turn then proceeds within the same call to its first main step.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mtg_goldfishing.domain.combat.blocks import request_blocks
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
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import (
    MAXIMUM_HAND,
    CardInstance,
    Destination,
    Game,
    Reminder,
    TurnStats,
    WindowKind,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw, move
from mtg_goldfishing.domain.game.naming import resolve
from mtg_goldfishing.domain.game.notices import examine_turn_limit
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.waiting import waiting_reminders
from mtg_goldfishing.domain.mana import ManaPool
from mtg_goldfishing.domain.payment.potential import mana_available
from mtg_goldfishing.domain.records.model import TurnSnapshot
from mtg_goldfishing.domain.records.snapshots import take_snapshot
from mtg_goldfishing.domain.stack.windows import go_on, open_window
from mtg_goldfishing.domain.steps import Step


@dataclass
class Walk:
    """What happened while the game moved through steps."""

    entered: list[EnteredStep] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    snapshots: list[TurnSnapshot] = field(default_factory=list)
    reminded: bool = False
    blocks_asked: bool = False

    @property
    def summary(self) -> StepsEntered:
        return StepsEntered(tuple(self.entered))


# @spec TURN-011, TURN-047, TURN-048, TURN-049, TURN-050, TURN-055
def _remind(game: Game, decks: Decks, step: Step) -> list[ReminderIssued]:
    """Remind each seat of the step triggers of the permanents it controls, each permanent
    read from its owner's deck: the active seat of triggers on its controller's turn or each
    turn; in a contested game every other seat still in the game of triggers on each turn or
    each opponent's turn. One reminder per permanent, listed by name and count per seat."""
    active = game.active_seat
    seats = [active]
    if game.contested:
        seats.extend(other for other in game.others_from(active.number) if other.in_game)
    issued: list[ReminderIssued] = []
    for seat in seats:
        own_turn = seat.number == active.number
        counts: dict[str, int] = {}
        for card in game.battlefield_of(seat.number):
            deck = decks.of(card.owner)
            triggers = reading_of(deck, card).step_triggers
            if not any(t.step is step and t.on_turn_of(controller=own_turn) for t in triggers):
                continue
            name = face_name(deck, card)
            counts[name] = counts.get(name, 0) + 1
            seat.reminders.append(
                Reminder(card.id, name, step, card_name=card.name, turn=game.turn)
            )
        if counts:
            shown = seat.number if game.contested else None
            issued.append(ReminderIssued(step, tuple(counts.items()), shown))
    return issued


# @spec TURN-032, TURN-034
def _begin_turn(game: Game, previous: SeatNumber | None) -> None:
    """The active seat begins a turn: one more table turn and one more of its own turns.

    A turn begins a round when it is the game's first, or when it passes to a seat that is
    not later in turn order than `previous`, the seat whose turn just ended; a goldfish
    game's one seat begins a round with every turn.
    """
    active = game.active_seat
    if previous is None or active.number <= previous:
        game.round += 1
    game.turn += 1
    active.turns += 1
    for card in game.battlefield_of(active.number):
        card.tapped = False
    active.land_drops_used = 0
    active.turn_stats = TurnStats()
    active.reminders = []
    game.tapped_by_attacks = []


# @spec TURN-002, TURN-003, TURN-004, TURN-005, TURN-011, TURN-014, TURN-027, TURN-028
def enter_step(
    game: Game,
    decks: Decks,
    step: Step,
    walk: Walk,
    discard: Sequence[CardInstance] = (),
    *,
    previous: SeatNumber | None = None,
) -> None:
    """Leave the current step (emptying every pool) and enter `step` of the active seat's
    turn, doing its automatic action with the active seat's deck.

    Entering untap begins a turn; `previous` is the seat whose turn just ended, when that
    is not the active seat itself.
    """
    for seat in game.seats:
        seat.mana_pool = ManaPool()
    game.step = step
    active = game.active_seat
    deck = decks.of(active.number)
    if step is Step.UNTAP:
        _begin_turn(game, previous or (game.active if game.turn > 0 else None))
    if game.contested:
        walk.entered.append(EnteredStep(active.turns, step, active.number))
    else:
        walk.entered.append(EnteredStep(game.turn, step))
    if step is Step.UNTAP:
        walk.events.extend(examine_turn_limit(game))
    elif step is Step.DRAW and not (game.turn == 1 and not game.draw_first_turn):
        walk.events.extend(draw(game, active.number, 1))
    elif step is Step.MAIN1:
        active.turn_stats.mana_available = mana_available(game, deck, active.number)
    elif step is Step.DECLARE_BLOCKERS and game.contested:
        asked = request_blocks(game, decks)
        walk.events.extend(asked)
        walk.blocks_asked = bool(game.pending)
    elif step is Step.COMBAT_DAMAGE:
        walk.events.extend(deal_combat_damage(game, deck, decks))
    elif step is Step.CLEANUP:
        if discard:
            for card in discard:
                walk.events.extend(move(game, deck, card, Destination.GRAVEYARD))
            walk.events.append(CardsDiscarded(tuple(card.name for card in discard)))
        snapshot = take_snapshot(game, deck)
        if snapshot is not None:
            walk.snapshots.append(snapshot)
    reminders = _remind(game, decks, step)
    if reminders:
        walk.events.extend(reminders)
        walk.reminded = True
    if step is Step.END and game.contested:
        open_window(game, WindowKind.END)


def _discard_list(value: object) -> list[str] | Error | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject="discard")


def _cleanup_discard(
    game: Game, deck: LoadedDeck, seat: SeatNumber, names: list[str], override: str | None
) -> tuple[list[CardInstance], FailedCheck | None] | Refusal:
    """The cards to discard, and the discard-count check an `override` overrode, if any."""
    excess = max(0, len(game.hand_of(seat)) - MAXIMUM_HAND)
    found = resolve(game, deck, seat, names, [Zone.HAND])
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
# @spec TURN-023, TURN-024, TURN-025, APP-031, TURN-039, TURN-060, CMBT-038, TURN-056
# @spec TURN-068, TURN-069, TURN-059, STACK-037, STACK-085, TURN-051
def advance(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    to: object = None,
    discard: object = None,
    override: str | None = None,
    decks: Decks | None = None,
) -> Result:
    """Move to the next step, or forward through every step to the next occurrence of `to`.

    The calling seat is the active seat, whose hand alone is checked before cleanup. In a
    contested game the advance never goes past the end of the calling seat's turn: leaving
    cleanup ends it, and the next seat's turn begins. `decks` gives each seat's deck;
    omitted, every seat plays `deck`.
    """
    every = decks or Decks.everyone_playing(game, deck)
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
    turn_ends = False
    while True:
        upcoming = Step.UNTAP if moved.step is None else moved.step.next
        if moved.contested and moved.step is Step.CLEANUP:
            turn_ends = True
            break
        to_discard: list[CardInstance] = []
        if upcoming is Step.CLEANUP:
            excess = len(moved.hand_of(seat)) - MAXIMUM_HAND
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
                chosen = _cleanup_discard(moved, deck, seat, names, override)
                if isinstance(chosen, Refusal):
                    return chosen
                to_discard, overridden = chosen
                if overridden is not None and override:
                    walk.events.append(ChecksOverridden((overridden,), override))
            entered_cleanup = True
        enter_step(moved, every, upcoming, walk, to_discard)
        if moved.step is Step.END and moved.contested:
            walk.events.extend(go_on(moved, every))
        if target is None or moved.step is target:
            break
        if walk.blocks_asked:
            walk.events.append(AdvanceStopped(StopReason.BLOCKS, upcoming, target))
            break
        if walk.reminded:
            walk.events.append(AdvanceStopped(StopReason.REMINDER, upcoming, target))
            break
        if moved.window is not None:
            asked = moved.window.asking
            walk.events.append(AdvanceStopped(StopReason.END_WINDOW, upcoming, target, seat=asked))
            break
    if names is not None and not entered_cleanup:
        return Refusal.error(Error(ErrorKind.DISCARD_WITHOUT_CLEANUP))
    if turn_ends:
        pass_the_turn(moved, every, walk)
    return Applied(moved, walk.summary, tuple(walk.events), tuple(walk.snapshots))


# @spec TURN-031, TURN-033, TURN-040, TURN-041, REC-064, REC-071
def pass_the_turn(game: Game, decks: Decks, walk: Walk) -> None:
    """End the active seat's turn: the next seat in turn order still in the game becomes the
    active seat and its turn proceeds to its first main step, stopping where a reminder
    stops it. When no other seat is left in the game, the same seat takes the next turn.

    A turn ended by its active seat's elimination never entered cleanup; its snapshot is
    written now, describing that seat as its elimination left it."""
    previous = game.active_seat
    if not previous.in_game:
        snapshot = take_snapshot(game, decks.of(previous.number))
        if snapshot is not None:
            walk.snapshots.append(snapshot)
    following = next((seat for seat in game.others_from(previous.number) if seat.in_game), None)
    if following is None:
        if not previous.in_game:
            game.active = None
            return
        following = previous
    game.active = following.number
    begin_turn(game, decks, walk, previous=previous.number, stopping=True)


def begin_turn(
    game: Game,
    decks: Decks,
    walk: Walk,
    *,
    previous: SeatNumber | None = None,
    stopping: bool,
) -> None:
    """The active seat begins a turn: through untap, upkeep and draw to its first main step,
    as an advance to `main1` would, stopping in a step with a reminder when `stopping`."""
    walk.reminded = False
    enter_step(game, decks, Step.UNTAP, walk, previous=previous)
    while game.step is not Step.MAIN1 and not (stopping and walk.reminded):
        assert game.step is not None
        enter_step(game, decks, game.step.next, walk)


def walk_to(game: Game, decks: Decks, target: Step, walk: Walk) -> bool:
    """Move a game (in place) forward to the next occurrence of a step of the active seat's
    turn, stopping for nothing but, in a contested game, a step where a seat other than the
    active seat is reminded. Whether it reached `target`."""
    while True:
        upcoming = Step.UNTAP if game.step is None else game.step.next
        enter_step(game, decks, upcoming, walk)
        if game.step is target:
            return True
        if waiting_reminders(game):
            return False


# @spec TURN-026
def return_to_declare_attackers(
    game: Game, deck: LoadedDeck, walk: Walk, decks: Decks | None = None
) -> None:
    """An additional combat: back to declare attackers in the same turn. `decks` gives each
    seat's deck; omitted, every seat plays `deck`."""
    enter_step(game, decks or Decks.everyone_playing(game, deck), Step.DECLARE_ATTACKERS, walk)
