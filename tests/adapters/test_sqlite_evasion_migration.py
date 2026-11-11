"""The migration to schema version 4: every card reading held in a stored loaded deck or game
document gains the flying, horsemanship, reach and "can't be blocked" readings made from the
card data stored with it, and nothing else about it changes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase
from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.domain.deck.model import CardDefinition, DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game.model import CardInstance, Game, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.reading.model import KeywordReading
from mtg_goldfishing.domain.reading.reader import read_card
from tests.support.builders import a_game
from tests.support.cards import a_card

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M1: not implemented yet")
BEFORE_EVASION = MIGRATIONS[:3]
"""The migrations of a database written before evasion and reach readings."""
NEW_READINGS = ("flying", "horsemanship", "reach", "cant_be_blocked")
DECK_ID = "dold"
GAME_ID = "gtest000001"

WIND_DRAKE = a_card("Wind Drake", "Flying", "Creature — Drake")
DEFINED_BEARS = a_card("Grizzly Bears", "", "Creature — Bear", keywords=("Reach",))
SNEAK = a_card("Phantom Warrior", "This creature can't be blocked.", "Creature — Illusion")


def _without_new_readings(data: object) -> object:
    """A stored document as written before evasion and reach readings: no face reading holds
    them."""
    if isinstance(data, list):
        return [_without_new_readings(item) for item in data]
    if not isinstance(data, dict):
        return data
    kept = {key: _without_new_readings(value) for key, value in data.items()}
    if kept.get("__type__") == "FaceReading":
        for name in NEW_READINGS:
            kept.pop(name, None)
    return kept


def _as_stored(value: object, kind: object) -> str:
    return json.dumps(_without_new_readings(json.loads(encode(value, kind))))


def a_stored_deck() -> LoadedDeck:
    """A deck holding a flyer read from its text and a card whose definition gives reach."""
    return LoadedDeck(
        deck_id=DECK_ID,
        commanders=(),
        entries=(DeckEntry("Wind Drake", 1), DeckEntry("Grizzly Bears", 1)),
        cards=(
            DeckCard(WIND_DRAKE, read_card(WIND_DRAKE)),
            DeckCard(DEFINED_BEARS, read_card(DEFINED_BEARS)),
        ),
        definitions=(CardDefinition(name="Grizzly Bears", keywords=("Reach",)),),
    )


def a_stored_game() -> Game:
    """A game holding a card brought from outside the game, with card data and a reading of
    its own, and a card instance read from its owner's deck, which holds none."""
    game = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat().build().game
    game.cards.append(
        CardInstance(
            "c99",
            SNEAK.name,
            Zone.BATTLEFIELD,
            owner=SeatNumber(1),
            controller=SeatNumber(1),
            definition=SNEAK,
            reading=read_card(SNEAK),
        )
    )
    return game


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "goldfishing.db"


def _stored_before_evasion(path: Path, *, version: int = 5) -> None:
    """A database at schema 3 holding the stored deck and the stored game."""
    SqliteDatabase(path, migrations=BEFORE_EVASION).close()
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "INSERT INTO decks (deck_id, deck, created_at) VALUES (?, ?, 't')",
            (DECK_ID, _as_stored(a_stored_deck(), LoadedDeck)),
        )
        connection.execute(
            "INSERT INTO games (game_id, deck_id, seed, status, result, state, version,"
            " created_at, updated_at) VALUES (?, ?, 1, 'active', NULL, ?, ?, 't', 't')",
            (GAME_ID, DECK_ID, _as_stored(a_stored_game(), Game), version),
        )
    connection.close()


def _migrated(path: Path) -> None:
    SqliteDatabase(path).close()


def _query(path: Path, sql: str) -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def _stored_deck_text(path: Path) -> str:
    return str(_query(path, "SELECT deck FROM decks")[0][0])


def _stored_game_text(path: Path) -> str:
    return str(_query(path, "SELECT state FROM games")[0][0])


def _face(deck: LoadedDeck, name: str) -> Any:
    found = deck.card(name)
    assert found is not None
    return found.reading.face(0)


# @spec STOR-036
@NOT_BUILT
def test_a_stored_deck_s_readings_gain_evasion_read_from_its_card_data(path: Path) -> None:
    _stored_before_evasion(path)

    _migrated(path)

    deck: LoadedDeck = decode(_stored_deck_text(path), LoadedDeck)
    assert _face(deck, "Wind Drake").flying == KeywordReading(own=True)


# @spec STOR-036
@NOT_BUILT
def test_a_stored_deck_s_readings_gain_reach_from_a_card_definition_s_keywords(path: Path) -> None:
    _stored_before_evasion(path)

    _migrated(path)

    deck: LoadedDeck = decode(_stored_deck_text(path), LoadedDeck)
    assert _face(deck, "Grizzly Bears").reach == KeywordReading(own=True)


# @spec STOR-037
@NOT_BUILT
def test_a_stored_game_s_own_card_readings_gain_evasion_read_from_their_card_data(
    path: Path,
) -> None:
    _stored_before_evasion(path)

    _migrated(path)

    game: Game = decode(_stored_game_text(path), Game)
    reading = game.instance("c99").reading
    assert reading is not None
    assert reading.face(0).cant_be_blocked == KeywordReading(own=True)


# @spec STOR-037
def test_the_migration_adds_no_reading_to_a_card_instance_that_holds_none(path: Path) -> None:
    _stored_before_evasion(path)

    _migrated(path)

    game: Game = decode(_stored_game_text(path), Game)
    bears = next(card for card in game.cards if card.name == "Grizzly Bears")
    assert bears.reading is None


# @spec STOR-038
@NOT_BUILT
def test_the_migration_leaves_every_other_part_of_a_reading_and_the_deck_id_unchanged(
    path: Path,
) -> None:
    _stored_before_evasion(path)
    before = json.loads(_stored_deck_text(path))

    _migrated(path)

    after = json.loads(_stored_deck_text(path))
    assert _without_new_readings(after) == before
    assert _query(path, "SELECT deck_id FROM decks") == [(DECK_ID,)]
    assert after["deck_id"] == DECK_ID
    assert after != before


# @spec STOR-039
def test_the_migration_leaves_a_game_s_version_counter_as_it_was(path: Path) -> None:
    _stored_before_evasion(path, version=5)

    _migrated(path)

    assert _query(path, "SELECT version FROM games") == [(5,)]


# @spec STOR-036
def test_a_card_with_no_evasion_is_stored_with_no_evasion_reading(path: Path) -> None:
    _stored_before_evasion(path)

    _migrated(path)

    deck: LoadedDeck = decode(_stored_deck_text(path), LoadedDeck)
    assert _face(deck, "Grizzly Bears").flying == KeywordReading()
