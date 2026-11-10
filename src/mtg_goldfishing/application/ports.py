"""The ports: interfaces the application reaches the outside world through.

Ports speak in domain types. Adapters implement them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from mtg_goldfishing.domain.cards import Card, CardLookup
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot

if TYPE_CHECKING:
    from mtg_goldfishing.application.outcome import Outcome


@dataclass(frozen=True)
class StoredGame:
    """A game as loaded, with the version it was stored at."""

    game: Game
    version: int


@dataclass(frozen=True)
class GameRecords:
    entries: tuple[LogEntry, ...]
    snapshots: tuple[TurnSnapshot, ...]
    calls: tuple[CallRecord, ...]


class GameRepository(Protocol):
    """Loads and saves games."""

    def get(self, game_id: str) -> StoredGame | None: ...

    def add(self, game: Game) -> None:
        """Store a new game at version 1."""
        ...

    def save(self, game: Game, *, version: int) -> bool:
        """Save a game loaded at `version`; False, writing nothing, if it has changed since."""
        ...


class DeckRepository(Protocol):
    """Keeps loaded decks. A loaded deck never changes once added."""

    def get(self, deck_id: str) -> LoadedDeck | None: ...

    def add(self, deck: LoadedDeck) -> LoadedDeck:
        """Add a deck, leaving an existing deck with the same id in place; return the stored one."""
        ...


class RecordStore(Protocol):
    """Keeps a game's log entries, turn snapshots and call records."""

    def append_entry(self, game_id: str, entry: LogEntry) -> None: ...

    def add_snapshot(self, game_id: str, snapshot: TurnSnapshot) -> None: ...

    def add_call(self, record: CallRecord) -> None: ...

    def read(self, game_id: str, *, since: int | None = None) -> GameRecords:
        """Entries with seq > since, calls with change > since, snapshots written after since."""
        ...


class CardCatalog(Protocol):
    """Supplies card data by exact name."""

    def look_up(self, names: Iterable[str], *, refresh: bool = False) -> Mapping[str, CardLookup]:
        """For each requested name, as given: the card, not found, or unavailable."""
        ...


class CardCache(Protocol):
    """Keeps fetched card data so no card is fetched twice."""

    def get(self, name: str) -> Card | None:
        """The cached card whose full name or a face name matches, ignoring case."""
        ...

    def put(self, card: Card) -> None:
        """Store a card, replacing any cached card with the same full name."""
        ...


class UnitOfWork(Protocol):
    """Makes one call's saves atomic across `GameRepository`, `DeckRepository` and `RecordStore`."""

    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class GameLocks(Protocol):
    """Applies one game's calls one at a time."""

    def hold(self, game_id: str) -> AbstractContextManager[None]: ...


class IdSource(Protocol):
    """Supplies what must be random."""

    def new_game_id(self) -> str:
        """Ten random characters for a game id."""
        ...

    def new_seed(self) -> int: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class Rendered:
    """An outcome as response text, and the text its call record keeps."""

    response: str
    record: str


class Renderer(Protocol):
    """Turns an outcome into response text. Implemented by the MCP adapter."""

    def render(self, tool: str, outcome: Outcome) -> Rendered: ...
