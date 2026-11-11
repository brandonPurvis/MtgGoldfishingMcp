"""The items on the stack and the open response window, as the game holds them: finding an
item, putting one on top, and beginning a window's asking again."""

from __future__ import annotations

import re
from dataclasses import replace

from mtg_goldfishing.domain.events import ItemStacked
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, StackItem, Window, WindowKind
from mtg_goldfishing.domain.game.naming import matches
from mtg_goldfishing.domain.game.seats import SeatNumber

_ITEM_ID = re.compile(r"^s\d+$", re.IGNORECASE)


def top(game: Game) -> StackItem | None:
    """The newest item on the stack, or None when the stack is empty."""
    return game.stack[-1] if game.stack else None


def is_item_id(entry: str) -> bool:
    return bool(_ITEM_ID.match(entry.strip()))


def item_named(game: Game, item_id: str) -> StackItem | None:
    """The item on the stack with this id, or None when no item on the stack has it."""
    wanted = item_id.strip().lower()
    return next((item for item in game.stack if item.id == wanted), None)


# @spec STACK-030, PLAY-078
def find_item(game: Game, decks: Decks, entry: str) -> StackItem | None:
    """The item a `counter` entry names: by its stack item id, or by the name of a spell's
    card on the stack, the newest such spell first. None when it names nothing on the
    stack."""
    if is_item_id(entry):
        return item_named(game, entry)
    for item in reversed(game.stack):
        if item.card is None:
            continue
        card = game.find(item.card)
        if card is not None and matches(decks.of(card.owner), card, entry):
            return item
    return None


def new_item_id(game: Game) -> str:
    """The next stack item id of the game, counted across the game and never reused."""
    item_id = f"s{game.next_item}"
    game.next_item += 1
    return item_id


# @spec STACK-034, STACK-039
def put_on_stack(game: Game, item: StackItem) -> ItemStacked:
    """Put an item on top of the stack and begin the asking again for it: a window of kind
    `stack` opens when none is open; an open window keeps its kind."""
    game.stack.append(item)
    if game.window is None:
        game.window = Window(WindowKind.STACK)
    else:
        game.window = Window(game.window.kind)
    return ItemStacked(item.id, item.controller, item.source, item.kind.value, item.cast_with)


# @spec STACK-035, STACK-040, STACK-084, TURN-061
def begin_asking_again(game: Game) -> None:
    """Begin the open window's asking again, with no seat counted as having passed, once the
    item asked about has left the stack. A `stack` window closes when the stack is empty; so
    does an `attack` or `end` window whose active seat has left the game."""
    window = game.window
    if window is None:
        return
    if not game.stack and (
        window.kind is WindowKind.STACK or game.active is None or not game.active_seat.in_game
    ):
        game.window = None
        return
    game.window = Window(window.kind)


# @spec STACK-023, STACK-089
def disturb_items_below(game: Game, resolved: StackItem) -> None:
    """Mark the items still on the stack as disturbed: `resolved`, above them, has resolved.
    A cast trigger disturbs neither the spell it was stated with nor that spell's other cast
    triggers, which its caster stated together with it for the board it leaves."""
    spared = resolved.cast_with

    def stated_with_it(item: StackItem) -> bool:
        return spared is not None and spared in (item.id, item.cast_with)

    game.stack = [
        item if stated_with_it(item) else replace(item, disturbed=True) for item in game.stack
    ]


def has_untapped_permanent(game: Game, seat: SeatNumber) -> bool:
    """Whether a seat controls an untapped permanent, which spares it an automatic pass."""
    return any(not card.tapped for card in game.battlefield_of(seat))
