"""The stored document format, pinned by documents recorded from the codec.

Each recorded document under `stored_documents/` is the exact text the codec writes for one
value built by the test support. The format is fixed by the documents already in
databases, so these files are never regenerated: a codec that writes anything else for
the same value has changed the format.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.adapters.sqlite.codec import CodecError, decode, encode, from_data, to_data
from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.deck.model import DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot
from mtg_goldfishing.domain.steps import Step
from tests.support.card_data import recorded_card
from tests.support.reference import a_reference_contested_game, a_reference_deck
from tests.support.stored import (
    a_call,
    a_contested_log_entry,
    a_contested_snapshot,
    a_log_entry,
    a_rich_deck,
    a_rich_game,
    a_snapshot,
)

DOCUMENTS = Path(__file__).parent / "stored_documents"


def _a_call_with_free_form_arguments() -> CallRecord:
    arguments: dict[str, object] = {
        "card": "Fireball",
        "pair": (1, "a"),
        "step": Step.MAIN1,
        "when": datetime(2026, 11, 18, 21, 30, tzinfo=UTC),
        "delta": {"__type__": "Game", "__tuple__": [1], "battlefield": ["Forest"]},
        "x": 3,
        "override": None,
    }
    return replace(a_call("gtest000001", 12, tool="play"), arguments=arguments)


STORED_VALUES: dict[str, tuple[Callable[[], object], object]] = {
    "rich_game": (a_rich_game, Game),
    "reference_contested_game": (a_reference_contested_game, Game),
    "rich_deck": (a_rich_deck, LoadedDeck),
    "reference_deck": (a_reference_deck, LoadedDeck),
    "log_entry": (lambda: a_log_entry(4), LogEntry),
    "contested_log_entry": (
        lambda: a_contested_log_entry(7, seat=2, table_turn=3, source="Phyrexian Arena"),
        LogEntry,
    ),
    "snapshot": (lambda: a_snapshot(3, written_by=9), TurnSnapshot),
    "contested_snapshot": (
        lambda: a_contested_snapshot(2, table_turn=6, written_by=14),
        TurnSnapshot,
    ),
    "call": (lambda: a_call("gtest000001", 5), CallRecord),
    "call_with_free_form_arguments": (_a_call_with_free_form_arguments, CallRecord),
    "multi_faced_card": (
        lambda: recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor"),
        Card,
    ),
    "adventure_card": (lambda: recorded_card("Bonecrusher Giant // Stomp"), Card),
}


def _recorded(name: str) -> str:
    return (DOCUMENTS / f"{name}.json").read_text(encoding="utf-8")


# ----------------------------------------------------------------------- the recorded text


# @spec STOR-047
@pytest.mark.parametrize("name", sorted(STORED_VALUES))
def test_a_stored_value_is_written_as_its_recorded_text(name: str) -> None:
    build, kind = STORED_VALUES[name]

    assert encode(build(), kind) == _recorded(name)


# @spec STOR-049
@pytest.mark.parametrize("name", sorted(STORED_VALUES))
def test_a_recorded_document_reads_as_the_value_it_was_written_from(name: str) -> None:
    build, kind = STORED_VALUES[name]

    assert decode(_recorded(name), kind) == build()


# @spec STOR-048
@pytest.mark.parametrize("name", sorted(STORED_VALUES))
def test_a_value_turns_into_the_recorded_data_for_a_migration(name: str) -> None:
    build, kind = STORED_VALUES[name]

    assert to_data(build(), kind) == json.loads(_recorded(name))


# @spec STOR-062
@pytest.mark.parametrize("name", sorted(STORED_VALUES))
def test_recorded_data_turns_into_the_value_for_a_migration(name: str) -> None:
    build, kind = STORED_VALUES[name]

    assert from_data(json.loads(_recorded(name)), kind) == build()


# ------------------------------------------------------------- documents migrations wrote


def _reordered(data: Any) -> Any:
    """The same data with every object's keys in reverse order."""
    if isinstance(data, dict):
        return {key: _reordered(data[key]) for key in reversed(list(data))}
    if isinstance(data, list):
        return [_reordered(item) for item in data]
    return data


def _with_unknown_keys(data: Any) -> Any:
    """The same data with a key that names no field added to every tagged object."""
    if isinstance(data, dict):
        found = {key: _with_unknown_keys(item) for key, item in data.items()}
        if "__type__" in found:
            found["retired_field"] = [1, {"x": None}]
        return found
    if isinstance(data, list):
        return [_with_unknown_keys(item) for item in data]
    return data


# @spec STOR-049
def test_a_document_with_its_keys_in_another_order_reads_as_the_same_value() -> None:
    text = json.dumps(_reordered(json.loads(_recorded("rich_game"))))

    assert decode(text, Game) == a_rich_game()


# @spec STOR-049
def test_keys_that_name_no_field_are_ignored() -> None:
    text = json.dumps(_with_unknown_keys(json.loads(_recorded("rich_deck"))))

    assert decode(text, LoadedDeck) == a_rich_deck()


@dataclass(frozen=True)
class _Measured:
    amount: float


# @spec STOR-049
def test_an_int_where_a_float_is_declared_reads_as_that_int() -> None:
    value = decode('{"__type__":"_Measured","amount":3}', _Measured)

    assert type(value.amount) is int


# @spec STOR-047
def test_an_int_where_a_float_is_declared_is_written_as_an_int() -> None:
    assert encode(_Measured(3), _Measured) == '{"__type__":"_Measured","amount":3}'


# ------------------------------------------------------------------------------ errors


# @spec STOR-050
def test_a_value_of_the_wrong_type_deep_inside_a_deck_cannot_be_stored() -> None:
    deck = a_rich_deck()
    entry: Any = deck.entries[0]
    entry = replace(entry, count="2")

    with pytest.raises(CodecError):
        encode(replace(deck, entries=(entry, *deck.entries[1:])), LoadedDeck)


# @spec STOR-050
def test_a_bool_where_an_int_is_declared_cannot_be_stored() -> None:
    entry: Any = DeckEntry("Forest", True)

    with pytest.raises(CodecError):
        encode(entry, DeckEntry)


# @spec STOR-063
def test_a_document_lacking_a_field_that_has_no_default_cannot_be_read() -> None:
    data = json.loads(_recorded("rich_deck"))
    del data["entries"][0]["count"]

    with pytest.raises(CodecError):
        from_data(data, LoadedDeck)


# @spec STOR-063
def test_a_tag_that_names_no_storable_class_cannot_be_read() -> None:
    data = json.loads(_recorded("log_entry"))
    data["__type__"] = "NoSuchClass"

    with pytest.raises(CodecError):
        from_data(data, LogEntry)


# @spec STOR-063
def test_a_value_of_a_kind_its_declared_type_does_not_accept_cannot_be_read() -> None:
    data = json.loads(_recorded("rich_deck"))
    data["entries"][0]["count"] = "two"

    with pytest.raises(CodecError):
        from_data(data, LoadedDeck)


# @spec STOR-063
def test_data_a_value_object_rejects_cannot_be_read() -> None:
    data = json.loads(_recorded("multi_faced_card"))
    data["faces"] = []

    with pytest.raises(CodecError):
        from_data(data, Card)
