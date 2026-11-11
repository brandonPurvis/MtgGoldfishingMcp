"""Domain values as JSON documents and back, by reflecting on their type hints.

One codec serves every stored shape — games, loaded decks, log entries, snapshots, call
records, cards — so a field added to a domain dataclass is stored without touching this
module. Encoding and decoding are both driven by the type the value is declared as:

- a dataclass becomes an object tagged with its class name under `__type__`, so a union of
  dataclasses (an `Event`, a `Produces`) reads back as the right member;
- an Enum becomes its value; a `datetime` its ISO text; a `ManaString` its text;
- tuples, lists and frozensets become arrays; dicts with string keys become objects.

Where the declared type is `object` (a call's arguments as received), values are written so
they describe themselves: tuples, enums, datetimes and objects that would be mistaken for
one of these are wrapped in a tagged object. Tag names resolve against the declared type
first, then against the classes defined in `mtg_goldfishing.domain`.

A value or document the codec cannot handle raises `CodecError`: that is a defect.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import types
import typing
from datetime import datetime
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any

import mtg_goldfishing.domain
from mtg_goldfishing.domain.mana import ManaString

TYPE_TAG = "__type__"
_TUPLE = "__tuple__"
_ENUM = "__enum__"
_DATETIME = "__datetime__"
_DICT = "__dict__"
_RESERVED = frozenset({TYPE_TAG, _TUPLE, _ENUM, _DATETIME, _DICT})
_NONE = type(None)
_PRIMITIVES = (bool, int, float, str)


class CodecError(Exception):
    """A value that cannot be stored, or a document that cannot be read. Always a defect."""


def encode(value: object, kind: object) -> str:
    """The JSON document for a value declared as `kind`."""
    return json.dumps(to_data(value, kind), ensure_ascii=False, separators=(",", ":"))


def decode(text: str, kind: object) -> Any:
    """The value of type `kind` a JSON document written by `encode` holds."""
    return from_data(json.loads(text), kind)


# ---------------------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------------------


def to_data(value: object, kind: object) -> Any:
    """A value declared as `kind`, as JSON-ready data."""
    kind = _unaliased(kind)
    if kind is object or kind is Any:
        return _free_to_data(value)
    if _is_union(kind):
        return _union_to_data(value, typing.get_args(kind))
    if kind is _NONE:
        _expect(value, _NONE, kind)
        return None
    if kind is ManaString:
        _expect(value, ManaString, kind)
        return str(value)
    if _is_dataclass_type(kind):
        _expect(value, kind, kind)
        return _dataclass_to_data(value)
    if isinstance(kind, type) and issubclass(kind, Enum):
        _expect(value, kind, kind)
        return _enum_value(value)
    if kind is datetime:
        _expect(value, datetime, kind)
        assert isinstance(value, datetime)
        return value.isoformat()
    if kind in _PRIMITIVES:
        _expect_primitive(value, kind)
        return value
    origin, arguments = typing.get_origin(kind), typing.get_args(kind)
    if origin is tuple:
        _expect(value, tuple, kind)
        assert isinstance(value, tuple)
        return [
            to_data(item, hint)
            for item, hint in zip(value, _tuple_hints(arguments, value), strict=True)
        ]
    if origin is list:
        _expect(value, list, kind)
        assert isinstance(value, list)
        return [to_data(item, arguments[0]) for item in value]
    if origin in (frozenset, set):
        _expect(value, origin, kind)
        assert isinstance(value, (frozenset, set))
        items = [to_data(item, arguments[0]) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    if origin is dict:
        _expect(value, dict, kind)
        assert isinstance(value, dict)
        _expect_string_keys(arguments[0], value)
        return {key: to_data(item, arguments[1]) for key, item in value.items()}
    raise CodecError(f"cannot store a value declared as {kind!r}")


def _dataclass_to_data(value: object) -> dict[str, Any]:
    cls: type = type(value)
    hints = _field_hints(cls)
    data: dict[str, Any] = {TYPE_TAG: cls.__name__}
    for item in dataclasses.fields(cls):
        data[item.name] = to_data(getattr(value, item.name), hints[item.name])
    return data


def _union_to_data(value: object, members: tuple[object, ...]) -> Any:
    for member in members:
        if _is_instance(value, member):
            return to_data(value, member)
    raise CodecError(f"{value!r} is none of {members!r}")


def _free_to_data(value: object) -> Any:
    """A value declared only as `object`, written so that it describes itself."""
    if value is None or isinstance(value, _PRIMITIVES):
        return value
    if isinstance(value, Enum):
        _resolve(type(value).__name__, ())
        return {_ENUM: type(value).__name__, "value": _enum_value(value)}
    if isinstance(value, datetime):
        return {_DATETIME: value.isoformat()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        _resolve(type(value).__name__, ())
        return _dataclass_to_data(value)
    if isinstance(value, tuple):
        return {_TUPLE: [_free_to_data(item) for item in value]}
    if isinstance(value, list):
        return [_free_to_data(item) for item in value]
    if isinstance(value, dict):
        _expect_string_keys(str, value)
        data = {key: _free_to_data(item) for key, item in value.items()}
        return {_DICT: data} if _RESERVED & data.keys() else data
    raise CodecError(f"cannot store {value!r} where any value is allowed")


# ---------------------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------------------


def from_data(data: Any, kind: object) -> Any:
    """The value of type `kind` that JSON-ready data written by `to_data` stands for."""
    kind = _unaliased(kind)
    if kind is object or kind is Any:
        return _free_from_data(data)
    if _is_union(kind):
        return _union_from_data(data, typing.get_args(kind))
    if kind is _NONE:
        _expect(data, _NONE, kind)
        return None
    if kind is ManaString:
        mana = ManaString.read(data) if isinstance(data, str) else None
        if mana is None:
            raise CodecError(f"not a mana string: {data!r}")
        return mana
    if _is_dataclass_type(kind):
        return _dataclass_from_data(data, kind)
    if isinstance(kind, type) and issubclass(kind, Enum):
        return _enum_member(kind, data)
    if kind is datetime:
        _expect(data, str, kind)
        try:
            return datetime.fromisoformat(data)
        except ValueError as error:
            raise CodecError(f"not a time: {data!r}") from error
    if kind in _PRIMITIVES:
        _expect_primitive(data, kind)
        return data
    origin, arguments = typing.get_origin(kind), typing.get_args(kind)
    if origin is tuple:
        _expect(data, list, kind)
        return tuple(
            from_data(item, hint)
            for item, hint in zip(data, _tuple_hints(arguments, data), strict=True)
        )
    if origin is list:
        _expect(data, list, kind)
        return [from_data(item, arguments[0]) for item in data]
    if origin in (frozenset, set):
        _expect(data, list, kind)
        return origin(from_data(item, arguments[0]) for item in data)
    if origin is dict:
        _expect(data, dict, kind)
        return {key: from_data(item, arguments[1]) for key, item in data.items()}
    raise CodecError(f"cannot read a value declared as {kind!r}")


# @spec STOR-040
def _dataclass_from_data(data: Any, declared: type) -> Any:
    if not isinstance(data, dict) or not isinstance(data.get(TYPE_TAG), str):
        raise CodecError(f"expected a stored {declared.__name__}, found {data!r}")
    cls = _resolve(data[TYPE_TAG], (declared,))
    hints = _field_hints(cls)
    given: dict[str, Any] = {}
    set_after: dict[str, Any] = {}
    for item in dataclasses.fields(cls):
        if item.name not in data:
            if _has_default(item):
                continue
            raise CodecError(f"a stored {cls.__name__} lacks {item.name}")
        value = from_data(data[item.name], hints[item.name])
        (given if item.init else set_after)[item.name] = value
    try:
        built = cls(**given)
    except (TypeError, ValueError) as error:
        raise CodecError(f"a stored {cls.__name__} is not valid: {error}") from error
    for name, value in set_after.items():
        object.__setattr__(built, name, value)
    return built


def _union_from_data(data: Any, members: tuple[object, ...]) -> Any:
    if data is None and _NONE in members:
        return None
    if isinstance(data, dict) and isinstance(data.get(TYPE_TAG), str):
        declared: tuple[type, ...] = tuple(m for m in members if _is_dataclass_type(m))
        return _dataclass_from_data(data, _resolve(data[TYPE_TAG], declared))
    for member in members:
        if member is _NONE:
            continue
        try:
            return from_data(data, member)
        except CodecError:
            continue
    raise CodecError(f"{data!r} reads as none of {members!r}")


def _free_from_data(data: Any) -> Any:
    if isinstance(data, list):
        return [_free_from_data(item) for item in data]
    if not isinstance(data, dict):
        return data
    if TYPE_TAG in data:
        return _dataclass_from_data(data, _resolve(data[TYPE_TAG], ()))
    if _TUPLE in data:
        return tuple(_free_from_data(item) for item in data[_TUPLE])
    if _ENUM in data:
        enum = _resolve(data[_ENUM], ())
        assert issubclass(enum, Enum)
        return _enum_member(enum, data["value"])
    if _DATETIME in data:
        return from_data(data[_DATETIME], datetime)
    if _DICT in data:
        return {key: _free_from_data(item) for key, item in data[_DICT].items()}
    return {key: _free_from_data(item) for key, item in data.items()}


# ---------------------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------------------


@cache
def _field_hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls)


@cache
def _domain_classes() -> dict[str, tuple[type, ...]]:
    """Every dataclass and Enum defined in the domain, by class name."""
    package = Path(mtg_goldfishing.domain.__file__).parent
    found: dict[str, list[type]] = {}
    for path in sorted(package.rglob("*.py")):
        parts = path.relative_to(package).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module = importlib.import_module(".".join((mtg_goldfishing.domain.__name__, *parts)))
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and value.__module__ == module.__name__
                and (dataclasses.is_dataclass(value) or issubclass(value, Enum))
            ):
                found.setdefault(value.__name__, []).append(value)
    return {name: tuple(classes) for name, classes in found.items()}


def _resolve(name: object, declared: tuple[type, ...]) -> type:
    """The class a tag names: one of the declared classes, else the domain class of that name."""
    for cls in declared:
        if cls.__name__ == name:
            return cls
    candidates = [
        cls
        for cls in _domain_classes().get(str(name), ())
        if not declared or issubclass(cls, declared)
    ]
    if len(candidates) != 1:
        raise CodecError(f"{name!r} names {len(candidates)} storable domain types, not one")
    return candidates[0]


def _unaliased(kind: object) -> object:
    while isinstance(kind, typing.TypeAliasType):
        kind = kind.__value__
    return kind


def _is_union(kind: object) -> bool:
    return typing.get_origin(kind) in (typing.Union, types.UnionType)


def _is_dataclass_type(kind: object) -> typing.TypeGuard[type]:
    return isinstance(kind, type) and dataclasses.is_dataclass(kind)


def _is_instance(value: object, kind: object) -> bool:
    kind = _unaliased(kind)
    if kind is object or kind is Any:
        return True
    if _is_union(kind):
        return any(_is_instance(value, member) for member in typing.get_args(kind))
    if kind in (int, float) and isinstance(value, bool):
        return False
    if kind is float:
        return isinstance(value, (int, float))
    runtime = typing.get_origin(kind) or kind
    return isinstance(runtime, type) and isinstance(value, runtime)


def _expect(value: object, runtime: type, kind: object) -> None:
    if not isinstance(value, runtime):
        raise CodecError(f"expected {kind!r}, found {value!r}")


def _expect_primitive(value: object, kind: object) -> None:
    if not _is_instance(value, kind):
        raise CodecError(f"expected {kind!r}, found {value!r}")


def _expect_string_keys(key_kind: object, value: dict[Any, Any]) -> None:
    if key_kind is not str or not all(isinstance(key, str) for key in value):
        raise CodecError(f"only dicts with string keys can be stored, found {value!r}")


def _tuple_hints(arguments: tuple[Any, ...], items: tuple[Any, ...] | list[Any]) -> list[Any]:
    if len(arguments) == 2 and arguments[1] is Ellipsis:
        return [arguments[0]] * len(items)
    if len(arguments) != len(items):
        raise CodecError(f"expected {len(arguments)} items, found {len(items)}")
    return list(arguments)


def _enum_value(member: Any) -> Any:
    value = member.value
    if not isinstance(value, _PRIMITIVES):
        raise CodecError(f"cannot store {member!r}: its value is not a JSON primitive")
    return value


def _enum_member(enum: type[Enum], value: Any) -> Enum:
    try:
        return enum(value)
    except ValueError as error:
        raise CodecError(f"{value!r} is not a {enum.__name__}") from error


def _has_default(item: dataclasses.Field[Any]) -> bool:
    return (
        item.default is not dataclasses.MISSING or item.default_factory is not dataclasses.MISSING
    )
