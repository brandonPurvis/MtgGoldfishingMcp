"""Nothing a loaded deck holds can be changed, so one copy can be shared across threads."""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import types
import typing
from typing import Any

import mtg_goldfishing.domain
from mtg_goldfishing.domain.deck.model import LoadedDeck

MUTABLE = (list, dict, set, bytearray)
IMMUTABLE_GENERICS = (tuple, frozenset, typing.Union, types.UnionType, typing.Literal)
"""The only generic types a field under a loaded deck may be declared with; any other, such
as `list[...]` or `Sequence[...]`, can hold a value that is changed after the deck is built."""


def _import_the_domain() -> None:
    """Import every domain module, so every subclass of a domain dataclass is known."""
    package = mtg_goldfishing.domain
    for module in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        importlib.import_module(module.name)


def _subclasses(cls: type) -> set[type]:
    found: set[type] = set()
    subclasses: list[type] = cls.__subclasses__()
    for sub in subclasses:
        found |= {sub, *_subclasses(sub)}
    return found


def _problems_of(kind: object, where: str, seen: set[type]) -> list[str]:
    """What, reachable through the declared type `kind`, could be changed after it is built."""
    while isinstance(kind, typing.TypeAliasType):
        kind = kind.__value__
    if kind is object or kind is Any:
        return [f"{where} admits a value of any type"]
    origin = typing.get_origin(kind)
    if kind in MUTABLE or (origin is not None and origin not in IMMUTABLE_GENERICS):
        return [f"{where} is declared as {kind!r}, which can hold a changeable value"]
    problems: list[str] = []
    if origin in (typing.Union, types.UnionType, tuple, frozenset):
        for argument in typing.get_args(kind):
            if argument is not Ellipsis:
                problems += _problems_of(argument, where, seen)
    if isinstance(kind, type) and dataclasses.is_dataclass(kind):
        for cls in {kind, *_subclasses(kind)} - seen:
            seen.add(cls)
            if not cls.__dataclass_params__.frozen:  # type: ignore[attr-defined]
                problems.append(f"{cls.__name__} is not frozen")
            for name, hint in typing.get_type_hints(cls).items():
                problems += _problems_of(hint, f"{cls.__name__}.{name}", seen)
    return problems


# @spec STOR-060
def test_every_dataclass_a_loaded_deck_can_hold_is_frozen_and_holds_no_mutable_collection() -> None:
    _import_the_domain()

    assert _problems_of(LoadedDeck, "LoadedDeck", set()) == []
