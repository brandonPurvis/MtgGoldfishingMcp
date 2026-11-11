"""The stack, an open response window and a `resolve` choice are stored and read back whole;
a loaded deck stored before step triggers were read with whose turns they happen on is read
with its triggers on its controller's turns; and stack items and log entries stored before
cast triggers read as holding none."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase, SqliteStores
from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.domain.deck.model import DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.reading.model import CardReading, FaceReading
from mtg_goldfishing.domain.records.model import LogEntry
from mtg_goldfishing.domain.stack.passing import pass_
from tests.support.acting import S2, acted
from tests.support.library import card
from tests.support.stored import a_log_entry
from tests.support.tables import bolt_at, three_seats, two_seats


def round_trip(game: Game) -> Game:
    read: Game = decode(encode(game, Game), Game)
    return read


# @spec STOR-015
def test_the_stack_and_an_open_window_are_stored_whole() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2), to="exile"),
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}, disturbed=True),
        lambda b: b.with_window("stack", asking=3, passed=(1,)),
    )

    assert round_trip(situation.game) == situation.game


# @spec STOR-015
def test_a_resolve_choice_stating_an_error_is_stored_whole() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack(
            "Lightning Bolt", delta={"move": {"graveyard": ["Shivan Dragon"]}}
        ),
        lambda b: b.with_window("stack", asking=2),
    )
    acted(situation, pass_(situation.game, situation.deck, S2))
    assert situation.game.pending[0].kind == "resolve"

    assert round_trip(situation.game) == situation.game


def test_a_deck_stored_before_whose_turns_were_read_reads_its_triggers_as_its_controllers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "goldfishing.db"
    SqliteDatabase(path, migrations=MIGRATIONS[:2]).close()
    deck = LoadedDeck(
        deck_id="dold",
        commanders=(),
        entries=(DeckEntry("Phyrexian Arena", 1),),
        cards=(DeckCard(card("Phyrexian Arena"), CardReading((FaceReading(),))),),
    )
    document: Any = json.loads(encode(deck, LoadedDeck))
    document["cards"][0]["reading"]["faces"][0]["step_triggers"] = ["upkeep"]
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "INSERT INTO decks (deck_id, deck, created_at) VALUES (?, ?, ?)",
            ("dold", json.dumps(document), "2026-01-01T00:00:00+00:00"),
        )
    connection.close()

    stores = SqliteStores.open(path)
    try:
        loaded = stores.decks.get("dold")
    finally:
        stores.database.close()

    assert loaded is not None
    (trigger,) = loaded.cards[0].reading.faces[0].step_triggers
    assert (trigger.step.value, trigger.whose.value) == ("upkeep", "controller")  # type: ignore[attr-defined]


# @spec STOR-040
@pytest.mark.xfail(strict=True, reason="M2: not implemented yet")
def test_a_stack_item_stored_without_cast_with_reads_as_no_cast_trigger() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}),
    )
    document: Any = json.loads(encode(situation.game, Game))
    for item in document["stack"]:
        item.pop("cast_with", None)

    read: Game = decode(json.dumps(document), Game)

    assert [item.cast_with for item in read.stack] == [None, None]


# @spec STOR-040
@pytest.mark.xfail(strict=True, reason="M2: not implemented yet")
def test_a_log_entry_stored_without_cast_triggers_reads_as_stating_none() -> None:
    document: Any = json.loads(encode(a_log_entry(3), LogEntry))
    document.pop("cast_triggers", None)

    read: LogEntry = decode(json.dumps(document), LogEntry)

    assert read.cast_triggers == ()
