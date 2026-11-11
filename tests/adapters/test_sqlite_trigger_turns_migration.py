"""The migration to schema version 3: step trigger readings stored before triggers were read with
whose turns they happen on are rewritten as triggers on their controller's turn. And how every
migration is applied: whole or not at all, with no copy of the database written first."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase

BEFORE_TRIGGER_TURNS = MIGRATIONS[:2]
"""The migrations of a database written before step triggers recorded whose turns."""
THROUGH_TRIGGER_TURNS = MIGRATIONS[:3]
"""The migrations up to and including the one to step triggers that record whose turns."""

EACH = {"__type__": "StepTrigger", "step": "end", "whose": "each"}


def _reading(*triggers: object) -> dict[str, Any]:
    return {"__type__": "FaceReading", "mana_abilities": [], "step_triggers": list(triggers)}


def _deck(*triggers: object) -> str:
    card = {"__type__": "DeckCard", "card": {}, "reading": {"faces": [_reading(*triggers)]}}
    return json.dumps({"__type__": "LoadedDeck", "deck_id": "dold", "cards": [card]})


def _game(*triggers: object) -> str:
    card = {"__type__": "CardInstance", "id": "c1", "reading": {"faces": [_reading(*triggers)]}}
    return json.dumps({"__type__": "Game", "game_id": "gold", "cards": [card]})


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "goldfishing.db"


def _stored_before_trigger_turns(path: Path, deck: str, game: str, version: int = 5) -> None:
    """A database at schema 2 holding one loaded deck and one game."""
    SqliteDatabase(path, migrations=BEFORE_TRIGGER_TURNS).close()
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "INSERT INTO decks (deck_id, deck, created_at) VALUES ('dold', ?, 't')", (deck,)
        )
        connection.execute(
            "INSERT INTO games (game_id, deck_id, seed, status, result, state, version,"
            " created_at, updated_at) VALUES ('gold', 'dold', 1, 'active', NULL, ?, ?, 't', 't')",
            (game, version),
        )
    connection.close()


def _migrated(path: Path) -> None:
    """Migrated to schema 3. The documents here hold only what that migration reads, not the
    card data later migrations read again."""
    SqliteDatabase(path, migrations=THROUGH_TRIGGER_TURNS).close()


def _query(path: Path, sql: str) -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def _triggers(document: str) -> list[object]:
    """Every step trigger reading a stored document holds, in the order they appear."""
    found: list[object] = []

    def walk(data: object) -> None:
        if isinstance(data, list):
            for item in data:
                walk(item)
        elif isinstance(data, dict):
            if data.get("__type__") == "FaceReading":
                found.extend(data["step_triggers"])
            for value in data.values():
                walk(value)

    walk(json.loads(document))
    return found


def _stored_deck(path: Path) -> str:
    return str(_query(path, "SELECT deck FROM decks")[0][0])


def _stored_game(path: Path) -> str:
    return str(_query(path, "SELECT state FROM games")[0][0])


# @spec STOR-030
def test_a_stored_deck_s_bare_step_triggers_become_triggers_on_their_controller_s_turn(
    path: Path,
) -> None:
    _stored_before_trigger_turns(path, _deck("upkeep", "end"), _game())

    _migrated(path)

    assert _triggers(_stored_deck(path)) == [
        {"__type__": "StepTrigger", "step": "upkeep", "whose": "controller"},
        {"__type__": "StepTrigger", "step": "end", "whose": "controller"},
    ]


# @spec STOR-031
def test_a_stored_game_s_bare_step_triggers_become_triggers_on_their_controller_s_turn(
    path: Path,
) -> None:
    _stored_before_trigger_turns(path, _deck(), _game("draw"))

    _migrated(path)

    assert _triggers(_stored_game(path)) == [
        {"__type__": "StepTrigger", "step": "draw", "whose": "controller"}
    ]


# @spec STOR-032
def test_a_step_trigger_that_already_says_whose_turns_is_left_as_it_is(path: Path) -> None:
    _stored_before_trigger_turns(path, _deck(EACH), _game(EACH))

    _migrated(path)

    assert (_triggers(_stored_deck(path)), _triggers(_stored_game(path))) == ([EACH], [EACH])


# @spec STOR-033
def test_the_migration_leaves_a_game_s_version_counter_as_it_was(path: Path) -> None:
    _stored_before_trigger_turns(path, _deck(), _game("upkeep"), version=5)

    _migrated(path)

    assert _query(path, "SELECT version FROM games") == [(5,)]


# @spec STOR-035
def test_migrating_writes_no_copy_of_the_database(path: Path) -> None:
    _stored_before_trigger_turns(path, _deck("upkeep"), _game("upkeep"))
    before = {p.name for p in path.parent.iterdir()}

    _migrated(path)

    written = {p.name for p in path.parent.iterdir()} - before
    assert written <= {f"{path.name}-wal", f"{path.name}-shm"}


# @spec STOR-034
def test_a_migration_that_fails_part_way_applies_none_of_its_changes(path: Path) -> None:
    _stored_before_trigger_turns(path, _deck("upkeep"), _game("upkeep"))
    before = (_stored_deck(path), _stored_game(path))

    def rewrite_then_fail(connection: sqlite3.Connection) -> None:
        connection.execute("UPDATE decks SET deck = '{}'")
        raise sqlite3.OperationalError("the migration fails part way")

    with pytest.raises(sqlite3.OperationalError):
        SqliteDatabase(path, migrations=(*BEFORE_TRIGGER_TURNS, rewrite_then_fail)).close()

    assert (_stored_deck(path), _stored_game(path)) == before
    assert _query(path, "SELECT version FROM schema_version") == [(len(BEFORE_TRIGGER_TURNS),)]
