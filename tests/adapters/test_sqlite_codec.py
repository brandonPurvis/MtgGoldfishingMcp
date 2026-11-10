"""The codec that turns games, loaded decks and records into JSON documents and back."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from mtg_goldfishing.adapters.sqlite.codec import CodecError, decode, encode
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import CardPlayed, Event
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot
from mtg_goldfishing.domain.steps import Step
from tests.support.stored import a_call, a_log_entry, a_rich_deck, a_rich_game, a_snapshot


# @spec STOR-004, STOR-005
def test_a_game_with_every_kind_of_state_survives_a_round_trip() -> None:
    game = a_rich_game()

    assert decode(encode(game, Game), Game) == game


# @spec STOR-004
def test_a_game_is_one_json_document() -> None:
    document = json.loads(encode(a_rich_game(), Game))

    assert document["__type__"] == "Game"


def test_a_loaded_deck_with_multi_faced_cards_and_readings_survives_a_round_trip() -> None:
    deck = a_rich_deck()

    assert decode(encode(deck, LoadedDeck), LoadedDeck) == deck


def test_a_log_entry_survives_a_round_trip() -> None:
    entry = a_log_entry(4)

    assert decode(encode(entry, LogEntry), LogEntry) == entry


def test_a_turn_snapshot_survives_a_round_trip() -> None:
    snapshot = a_snapshot(2, written_by=5)

    assert decode(encode(snapshot, TurnSnapshot), TurnSnapshot) == snapshot


def test_a_call_record_with_its_time_survives_a_round_trip() -> None:
    call = a_call("gtest000001", 3)

    assert decode(encode(call, CallRecord), CallRecord) == call


def test_a_mana_string_is_stored_as_its_text() -> None:
    assert json.loads(encode(ManaString.parse("{2}{G/U}{W/P}"), ManaString)) == "{2}{G/U}{W/P}"


def test_an_event_is_tagged_with_its_type_so_a_union_reads_back_the_right_one() -> None:
    event = CardPlayed("Forest", "Forest", "hand", "battlefield", is_land=True)

    assert decode(encode(event, Event), Event) == event


def test_tuples_inside_free_form_arguments_survive_a_round_trip() -> None:
    arguments: dict[str, object] = {"pair": (1, "a"), "step": Step.MAIN1, "when": datetime.now(UTC)}

    assert decode(encode(arguments, dict[str, object]), dict[str, object]) == arguments


def test_free_form_arguments_that_look_like_a_tagged_value_survive_a_round_trip() -> None:
    arguments: dict[str, object] = {"delta": {"__type__": "Game", "__tuple__": [1]}}

    assert decode(encode(arguments, dict[str, object]), dict[str, object]) == arguments


def test_a_document_missing_a_field_that_has_a_default_reads_with_the_default() -> None:
    document = json.loads(encode(a_snapshot(1, written_by=2), TurnSnapshot))
    del document["written_by"]

    assert decode(json.dumps(document), TurnSnapshot) == a_snapshot(1, written_by=0)


@dataclass(frozen=True)
class _NotADomainType:
    value: int


def test_a_value_outside_the_domain_cannot_be_stored_free_form() -> None:
    with pytest.raises(CodecError):
        decode(encode({"x": _NotADomainType(1)}, dict[str, object]), dict[str, object])


def test_a_value_of_the_wrong_type_cannot_be_encoded() -> None:
    with pytest.raises(CodecError):
        encode("not a game", Game)
