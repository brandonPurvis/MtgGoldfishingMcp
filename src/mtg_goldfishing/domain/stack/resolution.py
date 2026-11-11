"""Resolving the top item of the stack: its card to its destination, then its delta, applied as
its controller; or, when it was disturbed or its held delta can no longer be applied, a
`resolve` pending choice for its controller to confirm or restate it.

The service keeps the stack's order, not its meaning: it never works out what an item does,
it applies the delta the controller stated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields

from mtg_goldfishing.domain.events import (
    CardMoved,
    Error,
    Event,
    ItemResolved,
    LibraryShuffled,
    ResolveAsked,
)
from mtg_goldfishing.domain.game.cards_in_play import card_of
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.elimination import check_eliminations
from mtg_goldfishing.domain.game.model import (
    Destination,
    Game,
    GameStatus,
    PendingChoice,
    StackItem,
    Zone,
)
from mtg_goldfishing.domain.game.movement import move
from mtg_goldfishing.domain.game.notices import examine_end_conditions
from mtg_goldfishing.domain.play.arguments import read_delta
from mtg_goldfishing.domain.play.delta import apply_delta
from mtg_goldfishing.domain.stack.items import begin_asking_again, disturb_every_item


def _added(events: Sequence[Event]) -> dict[str, object]:
    """What the service added to a resolving delta: shuffles, commanders sent to the command
    zone instead, and tokens that ceased to exist."""
    moves = [event for event in events if isinstance(event, CardMoved)]
    return {
        "shuffles": sum(1 for event in events if isinstance(event, LibraryShuffled)),
        "commander_redirected": [m.card for m in moves if m.commander_redirected],
        "tokens_gone": [m.card for m in moves if m.token_gone],
    }


def _default_destination(game: Game, decks: Decks, item: StackItem) -> Destination:
    """Where a spell's card goes with no `to`: a permanent to the battlefield, an instant or
    sorcery to the graveyard, as its played face says."""
    card = game.instance(str(item.card))
    data = card_of(decks.of(card.owner), card)
    face = data.faces[card.face] if data is not None and card.face < len(data.faces) else None
    permanent = face.is_permanent if face is not None else False
    return Destination.BATTLEFIELD if permanent else Destination.GRAVEYARD


def _apply(
    game: Game,
    decks: Decks,
    item: StackItem,
    delta: Mapping[str, object],
    to: Destination | None,
) -> list[Event] | Error:
    """Resolve `item`, the top of the stack, in place: the item leaves the stack, its card
    goes to its destination, its delta is applied as its controller, the items below are
    disturbed, and every seat is checked for elimination."""
    read = read_delta(dict(delta), contested=True)
    if isinstance(read, Error):
        return read
    game.stack.remove(item)
    events: list[Event] = []
    went: str | None = None
    if item.card is not None:
        card = game.find(item.card)
        if card is not None:
            destination = to or _default_destination(game, decks, item)
            moved = move(
                game,
                decks.of(card.owner),
                card,
                destination,
                commander_stays=read.commander_stays,
                arriving_under=item.controller,
            )
            if card.zone is not Zone.BATTLEFIELD:
                card.face = 0
            arrived = next(e for e in moved if isinstance(e, CardMoved))
            went = arrived.to
            events.extend(moved)
    applied = apply_delta(
        game, decks.of(item.controller), item.controller, read, source=item.source, decks=decks
    )
    if isinstance(applied, Error):
        return applied
    events.extend(applied)
    disturb_every_item(game)
    resolved = ItemResolved(
        item.id, item.controller, item.source, {**dict(delta), "added": _added(events)}, went
    )
    events.extend(examine_end_conditions(game))
    events.extend(check_eliminations(game))
    begin_asking_again(game)
    return [resolved, *events]


# @spec STACK-016, STACK-017, STACK-018, STACK-019, STACK-020, STACK-021, STACK-022
# @spec STACK-072, STACK-073, STACK-074, STACK-080, STACK-081, STACK-023
def resolve_item(
    game: Game,
    decks: Decks,
    item: StackItem,
    delta: Mapping[str, object],
    to: Destination | None,
) -> list[Event] | Error:
    """Resolve the top item with the given delta and destination, wholly or not at all: on an
    error the game is left as it was."""
    trial = game.copy()
    done = _apply(trial, decks, item, delta, to)
    if isinstance(done, Error):
        return done
    for field in fields(Game):
        setattr(game, field.name, getattr(trial, field.name))
    return done


# @spec STACK-025, STACK-067, STACK-068
def ask_to_resolve(game: Game, item: StackItem, error: Error | None) -> ResolveAsked:
    """A `resolve` pending choice for the item's controller, showing its held delta and
    destination and, when the held delta cannot be applied, the error."""
    choice_id = game.new_choice_id()
    game.pending.append(
        PendingChoice(
            choice_id, item.controller, item.source, "resolve", [], None, item=item.id, error=error
        )
    )
    game.status = GameStatus.PENDING_CHOICE
    held_to = item.to.value if item.to is not None else None
    return ResolveAsked(
        choice_id, item.controller, item.id, item.source, dict(item.delta), held_to, error
    )


# @spec STACK-014, STACK-015, STACK-024, STACK-025, STACK-067
def reach_resolution(game: Game, decks: Decks) -> list[Event]:
    """The top item reaches resolution: it resolves as held when nothing resolved above it
    and its held delta can be applied; otherwise its controller is asked to confirm or
    restate it."""
    item = game.stack[-1]
    if item.disturbed:
        return [ask_to_resolve(game, item, None)]
    done = resolve_item(game, decks, item, item.delta, item.to)
    if isinstance(done, Error):
        return [ask_to_resolve(game, item, done)]
    return done
