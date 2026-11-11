"""Holding a play or an effect on the stack: what is checked when it is made, and the item it
becomes.

A held delta is written for the board the item will meet when it resolves, so only what does
not depend on where cards are is checked now: its shape (already read), its seat numbers and
its `counter` entries, each held from now on as the id of the item it named.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from mtg_goldfishing.domain.events import Error, ErrorKind, ItemStacked
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import (
    CardInstance,
    Destination,
    Game,
    StackItem,
    StackItemKind,
    Zone,
)
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.arguments import Delta
from mtg_goldfishing.domain.play.delta import check_seats
from mtg_goldfishing.domain.stack.items import find_item, new_item_id, put_on_stack


# @spec STACK-064, STACK-065, STACK-066, PLAY-078
def held_delta(
    game: Game, decks: Decks, seat: SeatNumber, data: object, delta: Delta
) -> dict[str, object] | Error:
    """The delta as it will be held: as stated, with each `counter` entry replaced by the id of
    the item it names now. A seat number not in the game or out of it, or a `counter` entry
    naming nothing on the stack, is an error; no card the delta names is looked for."""
    named = check_seats(game, seat, delta)
    if named is not None:
        return named
    held: dict[str, object] = (
        {str(key): copy.deepcopy(value) for key, value in data.items()}
        if isinstance(data, Mapping)
        else {}
    )
    if delta.counter:
        ids: list[str] = []
        for entry in delta.counter:
            item = find_item(game, decks, entry)
            if item is None:
                return Error(ErrorKind.NOT_ON_STACK, subject=entry)
            ids.append(item.id)
        held["counter"] = ids
    return held


def _choices(data: object) -> dict[str, object] | None:
    if not isinstance(data, Mapping):
        return None
    return {str(key): copy.deepcopy(value) for key, value in data.items()}


# @spec STACK-003, STACK-006, STACK-012, STACK-013
def hold_spell(
    game: Game,
    card: CardInstance,
    seat: SeatNumber,
    *,
    delta: dict[str, object],
    to: Destination | None,
    choices: object,
) -> ItemStacked:
    """Put a spell on the stack: its card moves to the zone `stack`, keeping the face it was
    cast as, and its item holds the delta, destination and choices as stated."""
    if card.zone is Zone.LIBRARY:
        game.take_from_library(card)
    card.zone = Zone.STACK
    card.controller = card.owner
    item = StackItem(
        id=new_item_id(game),
        controller=seat,
        kind=StackItemKind.SPELL,
        source=card.name,
        tool="play",
        delta=delta,
        card=card.id,
        to=to,
        choices=_choices(choices),
    )
    return put_on_stack(game, item)


# @spec STACK-007, STACK-012, STACK-013
def hold_ability(
    game: Game, seat: SeatNumber, *, source: str, delta: dict[str, object], choices: object
) -> ItemStacked:
    """Put an ability on the stack, holding the call's source and delta as stated."""
    item = StackItem(
        id=new_item_id(game),
        controller=seat,
        kind=StackItemKind.ABILITY,
        source=source,
        tool="effect",
        delta=delta,
        choices=_choices(choices),
    )
    return put_on_stack(game, item)


# @spec STACK-086
def hold_cast_trigger(
    game: Game,
    seat: SeatNumber,
    *,
    source: str,
    delta: dict[str, object],
    choices: dict[str, object] | None,
    cast_with: str,
) -> ItemStacked:
    """Put a cast trigger on the stack: an ability of the casting seat holding the trigger's
    source, delta and choices as stated and the id of the spell it was stated with."""
    item = StackItem(
        id=new_item_id(game),
        controller=seat,
        kind=StackItemKind.ABILITY,
        source=source,
        tool="play",
        delta=delta,
        choices=_choices(choices),
        cast_with=cast_with,
    )
    return put_on_stack(game, item)
