"""The migration to schema version 5: every face reading held in a stored loaded deck or game
document gains the station reading made from the card data stored with it, a station card's
keyword readings are read again, and nothing else about it changes."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase
from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.domain.deck.model import DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game.model import CardInstance, Game, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.reading.model import (
    NO_KEYWORD,
    CardReading,
    KeywordReading,
    StationReading,
)
from mtg_goldfishing.domain.reading.reader import read_card
from tests.support.builders import a_game
from tests.support.cards import a_card

BEFORE_STATION = MIGRATIONS[:4]
"""The migrations of a database written before station readings."""
DECK_ID = "dold"
GAME_ID = "gtest000001"

LABSHIP = a_card(
    "Synthesizer Labship",
    "Station (Tap another creature you control: Put charge counters equal to its power on this"
    " Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n"
    "9+ | Flying, vigilance",
    "Artifact — Spacecraft",
    pt="4/4",
)
WIND_DRAKE = a_card("Wind Drake", "Flying", "Creature — Drake", pt="2/2")


def _as_read_before(card_reading: CardReading, *, station_card: bool) -> CardReading:
    """A reading as the reader made it before station readings: a station card's first keyword
    after its station symbol unread and the rest read with no assumption."""
    face = card_reading.faces[0]
    if station_card:
        face = replace(face, flying=NO_KEYWORD, vigilance=KeywordReading(own=True))
    return CardReading((face,))


def _without_station(data: object) -> object:
    """A stored document as written before station readings: no face reading holds one."""
    if isinstance(data, list):
        return [_without_station(item) for item in data]
    if not isinstance(data, dict):
        return data
    kept = {key: _without_station(value) for key, value in data.items()}
    if kept.get("__type__") == "FaceReading":
        kept.pop("station", None)
    return kept


def _as_stored(value: object, kind: object) -> str:
    return json.dumps(_without_station(json.loads(encode(value, kind))))


def a_stored_deck() -> LoadedDeck:
    """A deck holding a station card and a flyer, read as they were before station readings;
    the flyer's flying reading is left out on purpose, to show the migration leaves a face
    with no station symbol as it was."""
    drake = _as_read_before(read_card(WIND_DRAKE), station_card=False)
    return LoadedDeck(
        deck_id=DECK_ID,
        commanders=(),
        entries=(DeckEntry("Synthesizer Labship", 1), DeckEntry("Wind Drake", 1)),
        cards=(
            DeckCard(LABSHIP, _as_read_before(read_card(LABSHIP), station_card=True)),
            DeckCard(WIND_DRAKE, CardReading((replace(drake.faces[0], flying=NO_KEYWORD),))),
        ),
    )


def a_stored_game() -> Game:
    """A game holding a station card brought from outside the game, with card data and a
    reading of its own, and a card instance read from its owner's deck, which holds none."""
    game = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat().build().game
    game.cards.append(
        CardInstance(
            "c99",
            LABSHIP.name,
            Zone.BATTLEFIELD,
            owner=SeatNumber(1),
            controller=SeatNumber(1),
            definition=LABSHIP,
            reading=_as_read_before(read_card(LABSHIP), station_card=True),
        )
    )
    return game


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "goldfishing.db"


def _stored_before_station(path: Path, *, version: int = 5) -> None:
    """A database at schema 4 holding the stored deck and the stored game."""
    SqliteDatabase(path, migrations=BEFORE_STATION).close()
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


def _stored_deck(path: Path) -> LoadedDeck:
    deck: LoadedDeck = decode(str(_query(path, "SELECT deck FROM decks")[0][0]), LoadedDeck)
    return deck


def _stored_game(path: Path) -> Game:
    game: Game = decode(str(_query(path, "SELECT state FROM games")[0][0]), Game)
    return game


def _face(deck: LoadedDeck, name: str) -> Any:
    found = deck.card(name)
    assert found is not None
    return found.reading.face(0)


# @spec STOR-043
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_stored_deck_s_station_card_gains_its_station_reading(path: Path) -> None:
    _stored_before_station(path)

    _migrated(path)

    assert _face(_stored_deck(path), "Synthesizer Labship").station == StationReading(9)


# @spec STOR-043
def test_a_stored_deck_s_card_without_station_gains_a_station_reading_of_never(
    path: Path,
) -> None:
    _stored_before_station(path)

    _migrated(path)

    assert _face(_stored_deck(path), "Wind Drake").station == StationReading()


# @spec STOR-044
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_stored_game_s_own_card_reading_gains_its_station_reading(path: Path) -> None:
    _stored_before_station(path)

    _migrated(path)

    reading = _stored_game(path).instance("c99").reading
    assert reading is not None
    assert reading.face(0).station == StationReading(9)


# @spec STOR-044
def test_the_migration_adds_no_reading_to_a_card_instance_that_holds_none(path: Path) -> None:
    _stored_before_station(path)

    _migrated(path)

    bears = next(card for card in _stored_game(path).cards if card.name == "Grizzly Bears")
    assert bears.reading is None


# @spec STOR-045
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_s_keywords_are_read_again(path: Path) -> None:
    _stored_before_station(path)

    _migrated(path)

    assumed = ("assumes it has 9 or more charge counters",)
    face = _face(_stored_deck(path), "Synthesizer Labship")
    assert face.flying == KeywordReading(own=True, assumptions=assumed)
    assert face.vigilance == KeywordReading(own=True, assumptions=assumed)


# @spec STOR-045, STOR-046
def test_a_face_with_no_station_symbol_keeps_its_keyword_readings(path: Path) -> None:
    _stored_before_station(path)

    _migrated(path)

    assert _face(_stored_deck(path), "Wind Drake").flying == NO_KEYWORD


# @spec STOR-046
def test_the_migration_leaves_the_deck_id_and_a_game_s_version_counter_as_they_were(
    path: Path,
) -> None:
    _stored_before_station(path, version=5)

    _migrated(path)

    assert _query(path, "SELECT deck_id FROM decks") == [(DECK_ID,)]
    assert _stored_deck(path).deck_id == DECK_ID
    assert _query(path, "SELECT version FROM games") == [(5,)]
