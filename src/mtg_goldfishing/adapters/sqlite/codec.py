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

How to write and read each declared type is worked out once, the first time the codec meets
it, and kept: a writer or reader is a function from a value to data, or back, that already
holds the writers or readers of the type's parts. A dataclass's fields are worked out the
first time a value of that class is written or read, so types that refer to themselves need
nothing special. What depends on the value itself is still decided per value: which member
of a union it is, which class a tag names, and how a free-form value describes itself.

A value or document the codec cannot handle raises `CodecError`: that is a defect.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import threading
import types
import typing
from collections.abc import Callable, Hashable
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
_JSON_WRITER = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))

Convert = Callable[[Any], Any]
"""A writer (a value to JSON-ready data) or a reader (JSON-ready data to a value)."""


class CodecError(Exception):
    """A value that cannot be stored, or a document that cannot be read. Always a defect."""


# @spec STOR-047, STOR-049, STOR-051, STOR-052
def encode(value: object, kind: object) -> str:
    """The JSON document for a value declared as `kind`."""
    return _JSON_WRITER.encode(to_data(value, kind))


def decode(text: str, kind: object) -> Any:
    """The value of type `kind` a JSON document written by `encode` holds."""
    return from_data(json.loads(text), kind)


# @spec STOR-048, STOR-050
def to_data(value: object, kind: object) -> Any:
    """A value declared as `kind`, as JSON-ready data."""
    return _writer(kind)(value)


# @spec STOR-062, STOR-063
def from_data(data: Any, kind: object) -> Any:
    """The value of type `kind` that JSON-ready data written by `to_data` stands for."""
    return _reader(kind)(data)


# ---------------------------------------------------------------------------------------
# Working out a type once
# ---------------------------------------------------------------------------------------

_writers: dict[Hashable, Convert] = {}
_readers: dict[Hashable, Convert] = {}
_building = threading.local()


def _writer(kind: object) -> Convert:
    return _planned(_writers, _make_writer, kind)


def _reader(kind: object) -> Convert:
    return _planned(_readers, _make_reader, kind)


def _planned(
    made: dict[Hashable, Convert], make: Callable[[object], Convert], kind: object
) -> Convert:
    """The converter for `kind`, worked out on first use and kept.

    A type met again while its own converter is being worked out (an alias that refers to
    itself) gets a stand-in that looks the finished converter up when it is first called.
    Two threads that meet a new type at once may both work it out; the results are equal.
    """
    key: Hashable = kind
    found = made.get(key)
    if found is not None:
        return found
    building: set[tuple[int, Hashable]] | None = getattr(_building, "kinds", None)
    if building is None:
        building = _building.kinds = set()
    mark = (id(made), key)
    if mark in building:

        def stand_in(value: Any) -> Any:
            return made[key](value)

        return stand_in
    building.add(mark)
    try:
        converter = make(kind)
    finally:
        building.discard(mark)
    return made.setdefault(key, converter)


# ---------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------


def _make_writer(kind: object) -> Convert:
    kind = _unaliased(kind)
    if kind is object or kind is Any:
        return _free_to_data
    if _is_union(kind):
        return _union_writer(typing.get_args(kind))
    if kind is _NONE:
        return _none_writer
    if kind is ManaString:
        return _mana_writer
    if _is_dataclass_type(kind):
        return _declared_dataclass_writer(kind)
    if isinstance(kind, type) and issubclass(kind, Enum):
        return _enum_writer(kind)
    if kind is datetime:
        return _datetime_writer
    if kind in _PRIMITIVES:
        return _primitive_writer(kind)
    origin, arguments = typing.get_origin(kind), typing.get_args(kind)
    if origin is tuple:
        return _tuple_writer(kind, arguments)
    if origin is list:
        return _list_writer(kind, _writer(arguments[0]))
    if origin in (frozenset, set):
        return _set_writer(kind, origin, _writer(arguments[0]))
    if origin is dict:
        return _dict_writer(kind, arguments[0], _writer(arguments[1]))
    return _cannot_write(kind)


def _none_writer(value: object) -> None:
    _expect(value, _NONE, _NONE)


def _mana_writer(value: object) -> str:
    _expect(value, ManaString, ManaString)
    return str(value)


def _datetime_writer(value: object) -> str:
    _expect(value, datetime, datetime)
    assert isinstance(value, datetime)
    return value.isoformat()


def _enum_writer(kind: type) -> Convert:
    def write(value: object) -> Any:
        _expect(value, kind, kind)
        return _enum_value(value)

    return write


def _primitive_writer(kind: type) -> Convert:
    def write(value: object) -> Any:
        if type(value) is kind:
            return value
        _expect_primitive(value, kind)
        return value

    return write


def _declared_dataclass_writer(kind: type) -> Convert:
    def write(value: object) -> dict[str, Any]:
        if not isinstance(value, kind):
            raise CodecError(f"expected {kind!r}, found {value!r}")
        cls: type = type(value)
        return _class_writer(cls)(value)

    return write


def _tuple_writer(kind: object, arguments: tuple[Any, ...]) -> Convert:
    if len(arguments) == 2 and arguments[1] is Ellipsis:
        item = _writer(arguments[0])

        def write_items(value: object) -> list[Any]:
            if not isinstance(value, tuple):
                raise CodecError(f"expected {kind!r}, found {value!r}")
            return [item(each) for each in value]

        return write_items
    items = tuple(_writer(argument) for argument in arguments)

    def write_fixed(value: object) -> list[Any]:
        if not isinstance(value, tuple):
            raise CodecError(f"expected {kind!r}, found {value!r}")
        if len(value) != len(items):
            raise CodecError(f"expected {len(items)} items, found {len(value)}")
        return [write(each) for write, each in zip(items, value, strict=True)]

    return write_fixed


def _list_writer(kind: object, item: Convert) -> Convert:
    def write(value: object) -> list[Any]:
        if not isinstance(value, list):
            raise CodecError(f"expected {kind!r}, found {value!r}")
        return [item(each) for each in value]

    return write


def _set_writer(kind: object, origin: type, item: Convert) -> Convert:
    def write(value: object) -> list[Any]:
        if not isinstance(value, origin):
            raise CodecError(f"expected {kind!r}, found {value!r}")
        assert isinstance(value, (frozenset, set))
        return sorted((item(each) for each in value), key=_canonical)

    return write


def _dict_writer(kind: object, key_kind: object, item: Convert) -> Convert:
    def write(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise CodecError(f"expected {kind!r}, found {value!r}")
        _expect_string_keys(key_kind, value)
        return {key: item(each) for key, each in value.items()}

    return write


def _union_writer(members: tuple[object, ...]) -> Convert:
    """The first member, in declared order, that the value is an instance of, writes it."""
    choices = tuple((_instance_check(member), _writer(member)) for member in members)

    def write(value: object) -> Any:
        for is_instance, write_member in choices:
            if is_instance(value):
                return write_member(value)
        raise CodecError(f"{value!r} is none of {members!r}")

    return write


def _cannot_write(kind: object) -> Convert:
    def write(value: object) -> Any:
        raise CodecError(f"cannot store a value declared as {kind!r}")

    return write


class _ClassWriter:
    """Writes values of one dataclass: its tag first, then every field in declaration order."""

    __slots__ = ("_cls", "_fields", "_tag")

    def __init__(self, cls: type) -> None:
        self._cls = cls
        self._tag = cls.__name__
        self._fields: tuple[tuple[str, Convert], ...] | None = None

    def __call__(self, value: object) -> dict[str, Any]:
        fields = self._fields
        if fields is None:
            hints = _field_hints(self._cls)
            fields = self._fields = tuple(
                (item.name, _writer(hints[item.name])) for item in dataclasses.fields(self._cls)
            )
        data: dict[str, Any] = {TYPE_TAG: self._tag}
        for name, write in fields:
            data[name] = write(getattr(value, name))
        return data


@cache
def _class_writer(cls: type) -> _ClassWriter:
    return _ClassWriter(cls)


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
        return _class_writer(type(value))(value)
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
# Reading
# ---------------------------------------------------------------------------------------


def _make_reader(kind: object) -> Convert:
    kind = _unaliased(kind)
    if kind is object or kind is Any:
        return _free_from_data
    if _is_union(kind):
        return _union_reader(typing.get_args(kind))
    if kind is _NONE:
        return _none_reader
    if kind is ManaString:
        return _mana_reader
    if _is_dataclass_type(kind):
        return _declared_dataclass_reader(kind)
    if isinstance(kind, type) and issubclass(kind, Enum):
        return _enum_reader(kind)
    if kind is datetime:
        return _datetime_reader
    if kind in _PRIMITIVES:
        return _primitive_reader(kind)
    origin, arguments = typing.get_origin(kind), typing.get_args(kind)
    if origin is tuple:
        return _tuple_reader(kind, arguments)
    if origin is list:
        return _list_reader(kind, _reader(arguments[0]))
    if origin in (frozenset, set):
        return _set_reader(kind, origin, _reader(arguments[0]))
    if origin is dict:
        return _dict_reader(kind, _reader(arguments[1]))
    return _cannot_read(kind)


def _none_reader(data: Any) -> None:
    _expect(data, _NONE, _NONE)


def _mana_reader(data: Any) -> ManaString:
    mana = ManaString.read(data) if isinstance(data, str) else None
    if mana is None:
        raise CodecError(f"not a mana string: {data!r}")
    return mana


def _datetime_reader(data: Any) -> datetime:
    _expect(data, str, datetime)
    try:
        return datetime.fromisoformat(data)
    except ValueError as error:
        raise CodecError(f"not a time: {data!r}") from error


def _enum_reader(kind: type[Enum]) -> Convert:
    def read(data: Any) -> Enum:
        return _enum_member(kind, data)

    return read


def _primitive_reader(kind: type) -> Convert:
    def read(data: Any) -> Any:
        if type(data) is kind:
            return data
        _expect_primitive(data, kind)
        return data

    return read


def _declared_dataclass_reader(declared: type) -> Convert:
    def read(data: Any) -> Any:
        if not isinstance(data, dict):
            raise CodecError(f"expected a stored {declared.__name__}, found {data!r}")
        tag = data.get(TYPE_TAG)
        if tag == declared.__name__:
            return _class_reader(declared)(data)
        if not isinstance(tag, str):
            raise CodecError(f"expected a stored {declared.__name__}, found {data!r}")
        return _class_reader(_resolve(tag, (declared,)))(data)

    return read


def _tuple_reader(kind: object, arguments: tuple[Any, ...]) -> Convert:
    if len(arguments) == 2 and arguments[1] is Ellipsis:
        item = _reader(arguments[0])

        def read_items(data: Any) -> tuple[Any, ...]:
            if not isinstance(data, list):
                raise CodecError(f"expected {kind!r}, found {data!r}")
            return tuple([item(each) for each in data])

        return read_items
    items = tuple(_reader(argument) for argument in arguments)

    def read_fixed(data: Any) -> tuple[Any, ...]:
        if not isinstance(data, list):
            raise CodecError(f"expected {kind!r}, found {data!r}")
        if len(data) != len(items):
            raise CodecError(f"expected {len(items)} items, found {len(data)}")
        return tuple(read(each) for read, each in zip(items, data, strict=True))

    return read_fixed


def _list_reader(kind: object, item: Convert) -> Convert:
    def read(data: Any) -> list[Any]:
        if not isinstance(data, list):
            raise CodecError(f"expected {kind!r}, found {data!r}")
        return [item(each) for each in data]

    return read


def _set_reader(kind: object, origin: type, item: Convert) -> Convert:
    def read(data: Any) -> Any:
        if not isinstance(data, list):
            raise CodecError(f"expected {kind!r}, found {data!r}")
        return origin(item(each) for each in data)

    return read


def _dict_reader(kind: object, item: Convert) -> Convert:
    def read(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise CodecError(f"expected {kind!r}, found {data!r}")
        return {key: item(each) for key, each in data.items()}

    return read


def _union_reader(members: tuple[object, ...]) -> Convert:
    """Null reads as None when None is a member; tagged data reads as the dataclass member
    its tag names; anything else reads as the first member, in declared order, that accepts
    it."""
    takes_none = _NONE in members
    declared: tuple[type, ...] = tuple(m for m in members if _is_dataclass_type(m))
    tries = tuple(_reader(member) for member in members if member is not _NONE)

    def read(data: Any) -> Any:
        if data is None and takes_none:
            return None
        if isinstance(data, dict):
            tag = data.get(TYPE_TAG)
            if isinstance(tag, str):
                return _class_reader(_resolve(tag, declared))(data)
        for read_member in tries:
            try:
                return read_member(data)
            except CodecError:
                continue
        raise CodecError(f"{data!r} reads as none of {members!r}")

    return read


def _cannot_read(kind: object) -> Convert:
    def read(data: Any) -> Any:
        raise CodecError(f"cannot read a value declared as {kind!r}")

    return read


class _ClassReader:
    """Reads stored data as one dataclass, by its fields' readers.

    A field missing from the data is left to its default, or is an error if it has none;
    keys that name no field are ignored.
    """

    __slots__ = ("_cls", "_fields")

    def __init__(self, cls: type) -> None:
        self._cls = cls
        self._fields: tuple[tuple[str, Convert, bool, bool], ...] | None = None

    # @spec STOR-040, STOR-041
    def __call__(self, data: dict[str, Any]) -> Any:
        fields = self._fields
        if fields is None:
            hints = _field_hints(self._cls)
            fields = self._fields = tuple(
                (item.name, _reader(hints[item.name]), _has_default(item), item.init)
                for item in dataclasses.fields(self._cls)
            )
        cls = self._cls
        given: dict[str, Any] = {}
        set_after: dict[str, Any] | None = None
        for name, read, has_default, init in fields:
            if name in data:
                if init:
                    given[name] = read(data[name])
                else:
                    if set_after is None:
                        set_after = {}
                    set_after[name] = read(data[name])
            elif not has_default:
                raise CodecError(f"a stored {cls.__name__} lacks {name}")
        try:
            built = cls(**given)
        except (TypeError, ValueError) as error:
            raise CodecError(f"a stored {cls.__name__} is not valid: {error}") from error
        if set_after:
            for name, value in set_after.items():
                object.__setattr__(built, name, value)
        return built


@cache
def _class_reader(cls: type) -> _ClassReader:
    return _ClassReader(cls)


def _free_from_data(data: Any) -> Any:
    if isinstance(data, list):
        return [_free_from_data(item) for item in data]
    if not isinstance(data, dict):
        return data
    if TYPE_TAG in data:
        tag = data[TYPE_TAG]
        if not isinstance(tag, str):
            raise CodecError(f"expected a stored dataclass, found {data!r}")
        return _class_reader(_resolve(tag, ()))(data)
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
    if isinstance(name, str):
        return _resolve_name(name, declared)
    return _resolve_uncached(name, declared)


@cache
def _resolve_name(name: str, declared: tuple[type, ...]) -> type:
    return _resolve_uncached(name, declared)


def _resolve_uncached(name: object, declared: tuple[type, ...]) -> type:
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
    return _instance_check(kind)(value)


def _instance_check(kind: object) -> Callable[[object], bool]:
    """Whether a value is an instance of the declared type `kind`, as the codec judges it:
    `bool` is not an `int` or a `float`, an `int` is a `float`, and a generic type is judged
    by its origin."""
    kind = _unaliased(kind)
    if kind is object or kind is Any:
        return lambda value: True
    if _is_union(kind):
        checks = tuple(_instance_check(member) for member in typing.get_args(kind))
        return lambda value: any(check(value) for check in checks)
    if kind is int:
        return lambda value: isinstance(value, int) and not isinstance(value, bool)
    if kind is float:
        return lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
    runtime = typing.get_origin(kind) or kind
    if not isinstance(runtime, type):
        return lambda value: False
    return lambda value: isinstance(value, runtime)


def _expect(value: object, runtime: type, kind: object) -> None:
    if not isinstance(value, runtime):
        raise CodecError(f"expected {kind!r}, found {value!r}")


def _expect_primitive(value: object, kind: object) -> None:
    if not _is_instance(value, kind):
        raise CodecError(f"expected {kind!r}, found {value!r}")


def _expect_string_keys(key_kind: object, value: dict[Any, Any]) -> None:
    if key_kind is not str or not all(isinstance(key, str) for key in value):
        raise CodecError(f"only dicts with string keys can be stored, found {value!r}")


def _canonical(item: Any) -> str:
    """An item's JSON text with its keys sorted: the order a set's items are written in."""
    return json.dumps(item, sort_keys=True)


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
