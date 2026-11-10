"""The card cache on SQLite: a row per card and a lookup row per face name."""

from __future__ import annotations

from mtg_goldfishing.adapters.sqlite.codec import decode, encode
from mtg_goldfishing.adapters.sqlite.database import SqliteDatabase
from mtg_goldfishing.adapters.sqlite.repositories import Now, utc_now
from mtg_goldfishing.domain.cards import Card


def _key(name: str) -> str:
    """A card or face name as it is looked up: ignoring case and surrounding whitespace."""
    return name.strip().casefold()


# @spec STOR-001, CARD-006, CARD-007, CARD-017, CARD-018
class SqliteCardCache:
    """Cached cards keyed by lower-cased full name, with a `card_names` row per face name.

    A face name that several cards share resolves to the card whose full name sorts first.
    """

    def __init__(self, database: SqliteDatabase, *, now: Now = utc_now) -> None:
        self._database = database
        self._now = now

    def get(self, name: str) -> Card | None:
        key = _key(name)
        connection = self._database.connection()
        row = connection.execute("SELECT card FROM card_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT card_cache.card FROM card_names"
                " JOIN card_cache ON card_cache.key = card_names.card_key"
                " WHERE card_names.face_key = ?"
                " ORDER BY card_cache.key, card_cache.name LIMIT 1",
                (key,),
            ).fetchone()
        return None if row is None else decode(row[0], Card)

    def put(self, card: Card) -> None:
        """Store a card, replacing the cached card with the same full name and its face rows."""
        key = _key(card.name)
        with self._database.writing() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO card_cache (key, name, card, fetched_at)"
                " VALUES (?, ?, ?, ?)",
                (key, card.name, encode(card, Card), self._now().isoformat()),
            )
            connection.execute("DELETE FROM card_names WHERE card_key = ?", (key,))
            connection.executemany(
                "INSERT OR IGNORE INTO card_names (face_key, card_key) VALUES (?, ?)",
                [(_key(face.name), key) for face in card.faces],
            )
