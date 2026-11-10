"""The database layout, as forward migrations: migration n brings a database to version n."""

from __future__ import annotations

MIGRATIONS: tuple[str, ...] = (
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
)
"""Each entry is one SQL script; a database at version n has had the first n applied."""

SCHEMA_VERSION = len(MIGRATIONS)
"""The newest layout this service knows."""
