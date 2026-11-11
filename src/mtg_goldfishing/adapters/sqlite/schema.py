"""The database layout, as forward migrations: migration n brings a database to version n.

A migration is an SQL script, or a function that changes the database through the
connection it is given. Either runs inside the one transaction that records the version
it reaches, so a migration is applied whole or not at all.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from typing import Any

from mtg_goldfishing.adapters.sqlite.codec import from_data, to_data
from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.deck.definitions import definitions_reading
from mtg_goldfishing.domain.deck.model import CardDefinition
from mtg_goldfishing.domain.reading.model import CardReading, KeywordReading
from mtg_goldfishing.domain.reading.reader import read_card

Migration = str | Callable[[sqlite3.Connection], None]

_SEATS = """
    CREATE TABLE seats (
        seat_id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL REFERENCES games (game_id),
        seat_number INTEGER NOT NULL,
        deck_id TEXT NOT NULL,
        tested INTEGER NOT NULL
    );
    INSERT INTO seats (seat_id, game_id, seat_number, deck_id, tested)
        SELECT game_id, game_id, 1, deck_id, 1 FROM games;
    ALTER TABLE calls ADD COLUMN seat INTEGER;
    CREATE INDEX calls_by_seat ON calls (game_id, seat);
"""


def _tagged(type_name: str, **fields: Any) -> dict[str, Any]:
    return {"__type__": type_name, **fields}


def _kept(stored: dict[str, Any], *names: str) -> dict[str, Any]:
    """The named fields a stored document holds. A field it lacks is left out, so that
    reading the rewritten document gives it its default, as reading the original did."""
    return {name: stored[name] for name in names if name in stored}


def seat_holding(stored: dict[str, Any]) -> dict[str, Any]:
    """A game document written before seats, rewritten into the seat-holding shape.

    What the game held for its one seat moves into the tested seat, numbered 1 and named
    by the game id, which owns and controls every card and has kept once a turn has begun.
    Pooled damage and commander damage become the imaginary opponents' tallies, the turn is
    also the round and the seat's own turn count, and the most recent change is the tested
    seat's. The rewrite works on the stored JSON alone, so it does not change as the domain
    does.
    """
    tested = _tagged("SeatNumber", value=1)
    turn = stored.get("turn", 0)
    change = stored.get("change", 0)
    started = turn >= 1
    last = stored.get("last_change")
    pending = stored.get("pending_choice")
    seat = _tagged(
        "Seat",
        number=tested,
        seat_id=_tagged("SeatId", value=stored["game_id"]),
        deck_id=stored["deck_id"],
        tested=True,
        kept=started,
        turns=turn,
        last_change=None if last is None else {**last, "change": change},
        **_kept(
            stored,
            "life",
            "mulligans",
            "shuffles",
            "land_drops_used",
            "turn_stats",
            "mana_pool",
            "commander_casts",
            "library",
            "reminders",
        ),
    )
    return _tagged(
        "Game",
        game_id=stored["game_id"],
        seed=stored["seed"],
        seats=[seat],
        active=tested if started else None,
        turn=turn,
        round=turn,
        change=change,
        pending=[] if pending is None else [{**pending, "seat": tested}],
        cards=[{**card, "owner": tested, "controller": tested} for card in stored.get("cards", [])],
        imaginary=_tagged(
            "ImaginaryOpponents",
            damage_dealt=stored.get("damage_dealt", 0),
            commander_damage=stored.get("commander_damage", {}),
        ),
        **_kept(
            stored,
            "turn_limit",
            "draw_first_turn",
            "status",
            "step",
            "declared_attack",
            "tapped_by_attacks",
            "notices",
            "result",
            "snapshot_turns",
            "next_instance",
            "next_choice",
        ),
    )


# @spec STOR-023, STOR-024, STOR-025, STOR-026, STOR-027
def add_seats(connection: sqlite3.Connection) -> None:
    """Give every stored game its tested seat: a `seats` row keyed by the game id, the
    nullable seat number of `calls` (null on every existing call record) with its index,
    and the game's document rewritten into the seat-holding shape. A game's version
    counter is left as it was: the game is the same game."""
    for statement in sqlite_statements(_SEATS):
        connection.execute(statement)
    games = connection.execute("SELECT game_id, state FROM games").fetchall()
    for game_id, state in games:
        rewritten = seat_holding(json.loads(state))
        connection.execute(
            "UPDATE games SET state = ? WHERE game_id = ?",
            (json.dumps(rewritten, ensure_ascii=False, separators=(",", ":")), game_id),
        )


def _with_trigger_turns(data: Any) -> Any:
    """A stored document with every step trigger reading written before triggers were read
    with whose turns they happen on (a bare step) rewritten as a trigger on its controller's
    turn, the turns every such reading was reminded on."""
    if isinstance(data, list):
        return [_with_trigger_turns(item) for item in data]
    if not isinstance(data, dict):
        return data
    rewritten = {key: _with_trigger_turns(value) for key, value in data.items()}
    triggers = rewritten.get("step_triggers")
    if rewritten.get("__type__") == "FaceReading" and isinstance(triggers, list):
        rewritten["step_triggers"] = [
            _tagged("StepTrigger", step=trigger, whose="controller")
            if isinstance(trigger, str)
            else trigger
            for trigger in triggers
        ]
    return rewritten


# @spec STOR-030, STOR-031, STOR-032, STOR-033
def add_step_trigger_turns(connection: sqlite3.Connection) -> None:
    """Rewrite the step trigger readings of every stored loaded deck and game, which named a
    step alone, as triggers on their controller's turn. A game's version counter is left as
    it was."""
    for table, key, column in (("decks", "deck_id", "deck"), ("games", "game_id", "state")):
        rows = connection.execute(f"SELECT {key}, {column} FROM {table}").fetchall()
        for row_key, document in rows:
            rewritten = _with_trigger_turns(json.loads(document))
            connection.execute(
                f"UPDATE {table} SET {column} = ? WHERE {key} = ?",
                (json.dumps(rewritten, ensure_ascii=False, separators=(",", ":")), row_key),
            )


EVASION_AND_REACH = ("flying", "horsemanship", "reach", "cant_be_blocked")
"""The readings migration 4 adds, by their field names in a stored face reading."""


def _with_readings(stored: dict[str, Any], reading: CardReading) -> dict[str, Any]:
    """A stored card reading with each face's evasion and reach readings added from
    `reading`, every other part of it as it was."""
    faces = stored.get("faces")
    if not isinstance(faces, list):
        return stored
    rewritten = []
    for index, face in enumerate(faces):
        made = reading.face(index)
        added = {name: to_data(getattr(made, name), KeywordReading) for name in EVASION_AND_REACH}
        rewritten.append({**face, **added} if isinstance(face, dict) else face)
    return {**stored, "faces": rewritten}


def _definitions_of(card: Card, definitions: Sequence[CardDefinition]) -> list[CardDefinition]:
    names = {card.name.casefold(), *(face.name.casefold() for face in card.faces)}
    return [d for d in definitions if d.name.strip().casefold() in names]


def _deck_with_evasion(stored: dict[str, Any]) -> dict[str, Any]:
    """A stored loaded deck whose card readings hold the evasion and reach readings made from
    the card data stored with each, card definitions applied, as `load_deck` makes them."""
    definitions = [from_data(d, CardDefinition) for d in stored.get("definitions", [])]
    cards = []
    for deck_card in stored.get("cards", []):
        card = from_data(deck_card["card"], Card)
        own = _definitions_of(card, definitions)
        reading = definitions_reading(card, own) if own else read_card(card)
        cards.append({**deck_card, "reading": _with_readings(deck_card["reading"], reading)})
    return {**stored, "cards": cards}


def _game_with_evasion(stored: dict[str, Any]) -> dict[str, Any]:
    """A stored game whose card instances that hold card data and a reading of their own have
    the evasion and reach readings made from that card data added; an instance that holds no
    reading gets none."""
    cards = []
    for instance in stored.get("cards", []):
        data, reading = instance.get("definition"), instance.get("reading")
        if data is None or reading is None:
            cards.append(instance)
            continue
        made = read_card(from_data(data, Card))
        cards.append({**instance, "reading": _with_readings(reading, made)})
    return {**stored, "cards": cards}


# @spec STOR-036, STOR-037, STOR-038, STOR-039
def add_evasion_and_reach(connection: sqlite3.Connection) -> None:
    """Add the flying, horsemanship, reach and "can't be blocked" readings to every card
    reading held in a stored loaded deck or game, made from the card data stored with it.
    Deck ids and a game's version counter are left as they were."""
    for table, key, column, rewrite in (
        ("decks", "deck_id", "deck", _deck_with_evasion),
        ("games", "game_id", "state", _game_with_evasion),
    ):
        rows = connection.execute(f"SELECT {key}, {column} FROM {table}").fetchall()
        for row_key, document in rows:
            rewritten = rewrite(json.loads(document))
            connection.execute(
                f"UPDATE {table} SET {column} = ? WHERE {key} = ?",
                (json.dumps(rewritten, ensure_ascii=False, separators=(",", ":")), row_key),
            )


def sqlite_statements(script: str) -> list[str]:
    """The SQL statements of a script, one at a time, so that each can run inside an open
    transaction (`executescript` would commit it first)."""
    statements: list[str] = []
    pending = ""
    for piece in script.split(";"):
        pending += piece + ";"
        if sqlite3.complete_statement(pending):
            if pending.replace(";", "").strip():
                statements.append(pending)
            pending = ""
    if pending.replace(";", "").strip():
        statements.append(pending)
    return statements


MIGRATIONS: tuple[Migration, ...] = (
    """
    CREATE TABLE schema_version (version INTEGER NOT NULL);
    CREATE TABLE card_cache (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        card TEXT NOT NULL,
        fetched_at TEXT NOT NULL
    );
    CREATE TABLE card_names (
        face_key TEXT NOT NULL,
        card_key TEXT NOT NULL REFERENCES card_cache (key) ON DELETE CASCADE,
        PRIMARY KEY (face_key, card_key)
    );
    CREATE TABLE decks (
        deck_id TEXT PRIMARY KEY,
        deck TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE games (
        game_id TEXT PRIMARY KEY,
        deck_id TEXT NOT NULL,
        seed INTEGER NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        state TEXT NOT NULL,
        version INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE log_entries (
        game_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        entry TEXT NOT NULL,
        PRIMARY KEY (game_id, seq)
    );
    CREATE TABLE snapshots (
        game_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        written_by INTEGER NOT NULL,
        snapshot TEXT NOT NULL,
        PRIMARY KEY (game_id, turn)
    );
    CREATE TABLE calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT,
        tool TEXT NOT NULL,
        arguments TEXT NOT NULL,
        status TEXT NOT NULL,
        response TEXT NOT NULL,
        is_override INTEGER NOT NULL,
        change INTEGER,
        time TEXT NOT NULL,
        record TEXT NOT NULL
    );
    CREATE INDEX calls_by_game ON calls (game_id, change);
    """,
    add_seats,
    add_step_trigger_turns,
    add_evasion_and_reach,
)
"""A database at version n has had the first n migrations applied."""


SCHEMA_VERSION = len(MIGRATIONS)
"""The newest layout this service knows."""
