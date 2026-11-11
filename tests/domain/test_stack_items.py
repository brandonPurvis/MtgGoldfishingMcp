"""A stack item is a value object, and the stack and the response window are held by the game
they belong to."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from mtg_goldfishing.domain.game.model import (
    Destination,
    Game,
    StackItem,
    StackItemKind,
    Window,
    WindowKind,
)
from tests.support.acting import S1, S2
from tests.support.tables import bolt_at, two_seats


def a_spell(**changes: Any) -> StackItem:
    fields: dict[str, Any] = {
        "id": "s1",
        "controller": S1,
        "kind": StackItemKind.SPELL,
        "source": "Lightning Bolt",
        "tool": "play",
        "delta": bolt_at(2),
        "card": "c3",
    }
    return StackItem(**{**fields, **changes})


# @spec APP-032
def test_a_stack_item_cannot_be_changed() -> None:
    item = a_spell()
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.disturbed = True  # type: ignore[misc]


# @spec APP-032
def test_stack_items_with_the_same_values_are_equal() -> None:
    assert a_spell() == a_spell()
    assert a_spell() != a_spell(disturbed=True)


# @spec APP-032
@pytest.mark.parametrize(
    "changes",
    [
        {"id": "x1"},
        {"id": "s0"},
        {"card": None},
        {"kind": StackItemKind.ABILITY, "tool": "effect"},
        {"kind": StackItemKind.ABILITY, "tool": "effect", "card": None, "to": Destination.EXILE},
        {"tool": "advance"},
    ],
    ids=["not s<n>", "s0", "spell without card", "ability with card", "ability with to", "tool"],
)
def test_a_stack_item_rejects_an_invalid_value(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"."):
        a_spell(**changes)


# @spec APP-029
def test_the_stack_and_the_response_window_are_held_by_the_game() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_window("stack", asking=2),
    )
    copied = situation.game.copy()

    assert {"stack", "window"} <= {field.name for field in dataclasses.fields(Game)}
    assert copied.stack == situation.game.stack
    assert copied.window == Window(WindowKind.STACK, S2, ())
    assert copied.stack is not situation.game.stack
