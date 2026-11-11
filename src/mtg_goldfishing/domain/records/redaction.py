"""Seat ids in records: no record of a contested game keeps an opposing seat's seat id.

A seat id is the whole of a seat's access control, and every seat may read the records. A
call made with an opposing seat's seat id is kept under the game id, and wherever an
opposing seat's seat id of the game occurs inside a stored string it is replaced by the
redaction mark, the rest of the string being kept. A goldfish game has no opposing seat, so
its records are kept as they are.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Mapping
from enum import Enum
from typing import Any, cast

from mtg_goldfishing.domain.game.model import Game

REDACTION_MARK = "[redacted]"


def opposing_seat_ids(game: Game) -> tuple[str, ...]:
    """The seat ids no record of the game may hold: every seat's but the tested seat's,
    which is the game id."""
    return tuple(seat.seat_id.value for seat in game.seats if not seat.tested)


def _redacted_text(text: str, seat_ids: Collection[str]) -> str:
    for seat_id in seat_ids:
        text = text.replace(seat_id, REDACTION_MARK)
    return text


def _redacted(value: object, seat_ids: Collection[str]) -> object:
    if isinstance(value, str):
        return _redacted_text(value, seat_ids)
    if isinstance(value, Enum) or value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Mapping):
        return {_redacted(key, seat_ids): _redacted(item, seat_ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item, seat_ids) for item in value]
    if isinstance(value, tuple):
        return tuple(_redacted(item, seat_ids) for item in value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        changes = {
            field.name: _redacted(getattr(value, field.name), seat_ids)
            for field in dataclasses.fields(value)
            if field.init
        }
        return dataclasses.replace(cast(Any, value), **changes)
    return value


# @spec REC-057, REC-065
def redacted[T](value: T, seat_ids: Collection[str]) -> T:
    """The value with every occurrence of the seat ids, in any string at any depth,
    replaced by the redaction mark."""
    if not seat_ids:
        return value
    return cast(T, _redacted(value, seat_ids))


# @spec REC-058, REC-065
def stored_arguments(
    arguments: Mapping[str, object], game_id: str, seat_ids: Collection[str]
) -> dict[str, object]:
    """A call's arguments as its records keep them: a `game_id` naming an opposing seat
    becomes the game id, and the seat ids are redacted from every other string."""
    kept = dict(arguments)
    if kept.get("game_id") in seat_ids:
        kept["game_id"] = game_id
    return redacted(kept, seat_ids)
