"""The ports: interfaces the application reaches the outside world through.

Ports speak in domain types. Each is an abstract base class; an adapter implements a port by
inheriting from it, so a class that leaves out an operation cannot be constructed.
"""

# @spec APP-042, APP-043, APP-044

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from mtg_goldfishing.domain.cards import Card, CardLookup
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.records.model import CallRecord, LogEntry, TurnSnapshot

if TYPE_CHECKING:
    from mtg_goldfishing.application.outcome import Outcome


@dataclass(frozen=True)
class StoredGame:
    """A game as loaded, with the version it was stored at."""

    game: Game
    version: int


@dataclass(frozen=True)
class SeatOfGame:
    """The game a seat id names, and the seat number of the seat it names in that game."""

    game_id: str
    seat: SeatNumber


@dataclass(frozen=True)
class GameRecords:
    entries: tuple[LogEntry, ...]
    snapshots: tuple[TurnSnapshot, ...]
    calls: tuple[CallRecord, ...]


# @spec APP-030, APP-045
class GameRepository(ABC):
    """Loads and saves games, and finds the game a seat id names.

    A seat is saved and loaded only as part of its game.
    """

    @abstractmethod
    def get(self, game_id: str) -> StoredGame | None: ...

    @abstractmethod
    def find_seat(self, seat_id: SeatId) -> SeatOfGame | None:
        """The game and seat number a seat id names, or None when it names no seat of any
        stored game. A game id names its game and its tested seat."""
        ...

    @abstractmethod
    def add(self, game: Game) -> None:
        """Store a new game at version 1, with the seat ids of all its seats."""
        ...

    @abstractmethod
    def save(self, game: Game, *, version: int) -> bool:
        """Save a game loaded at `version`; False, writing nothing, if it has changed since."""
        ...


class DeckRepository(ABC):
    """Keeps loaded decks. A loaded deck never changes once added."""

    @abstractmethod
    def get(self, deck_id: str) -> LoadedDeck | None: ...

    @abstractmethod
    def add(self, deck: LoadedDeck) -> LoadedDeck:
        """Add a deck, leaving an existing deck with the same id in place; return the stored one."""
        ...


# @spec APP-046, APP-092, APP-093
class RecordStore(ABC):
    """Keeps a game's log entries, turn snapshots and call records.

    A game has at most one snapshot per table turn: adding a second is a defect, and raises
    with the stored snapshot left as it was.
    """

    @abstractmethod
    def append_entry(self, game_id: str, entry: LogEntry) -> None: ...

    @abstractmethod
    def add_snapshot(self, game_id: str, snapshot: TurnSnapshot) -> None: ...

    @abstractmethod
    def add_call(self, record: CallRecord) -> None: ...

    @abstractmethod
    def read(self, game_id: str, *, since: int | None = None) -> GameRecords:
        """Entries with seq > since, calls with change > since, snapshots written after since."""
        ...

    @abstractmethod
    def digest_baseline(self, game_id: str, seat: SeatNumber) -> int | None:
        """A seat's digest baseline: the change number on its latest call record for a tool
        other than `get_log`, or None when it has no such call record."""
        ...

    @abstractmethod
    def change_time(self, game_id: str, change: int) -> datetime | None:
        """The time a game's change was made: the time on the earliest-stored call record of
        that game holding that change number, which is the record of the call that made it;
        None when the game has no such call record."""
        ...


class CardCatalog(ABC):
    """Supplies card data by exact name."""

    @abstractmethod
    def look_up(self, names: Iterable[str], *, refresh: bool = False) -> Mapping[str, CardLookup]:
        """For each requested name, as given: the card, not found, or unavailable."""
        ...


class CardCache(ABC):
    """Keeps fetched card data so no card is fetched twice."""

    @abstractmethod
    def get(self, name: str) -> Card | None:
        """The cached card a name resolves to by the card model's name-matching rule."""
        ...

    @abstractmethod
    def put(self, card: Card) -> None:
        """Store a card, replacing any cached card with the same full name."""
        ...


class UnitOfWork(ABC):
    """Makes one call's saves atomic across `GameRepository`, `DeckRepository` and `RecordStore`."""

    @abstractmethod
    def begin(self) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class GameLocks(ABC):
    """Applies one game's calls one at a time."""

    @abstractmethod
    def hold(self, game_id: str) -> AbstractContextManager[None]: ...


# @spec APP-041
class GameChanges(ABC):
    """Wakes seats waiting on a game: an applied change is announced once committed, and a
    wait returns when a change after the one it saw is announced, or when its time is up."""

    @abstractmethod
    def announce(self, game_id: str, change: int) -> None:
        """Announce that a game has changed, to the change number given."""
        ...

    @abstractmethod
    def wait_for_change(self, game_id: str, after: int, timeout: float) -> bool:
        """Wait up to `timeout` seconds for a change of the game numbered after `after`;
        True as soon as one has been announced, at once if one already has, else False."""
        ...


# @spec APP-047
class IdSource(ABC):
    """Supplies what must be random: game ids, seat ids and seeds."""

    @abstractmethod
    def new_game_id(self) -> str:
        """Ten random characters for a game id."""
        ...

    @abstractmethod
    def new_seat_id(self) -> str:
        """Ten random characters for an opposing seat's seat id, of the same form as a game
        id and drawn from the same source."""
        ...

    @abstractmethod
    def new_seed(self) -> int: ...


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class Rendered:
    """An outcome as response text, and the text its call record keeps."""

    response: str
    record: str


class Renderer(ABC):
    """Turns an outcome into response text. Implemented by the MCP adapter."""

    @abstractmethod
    def render(self, tool: str, outcome: Outcome) -> Rendered: ...
