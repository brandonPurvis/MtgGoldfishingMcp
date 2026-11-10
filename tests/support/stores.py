"""The persistence adapters behind one shape, so a contract suite can run against each."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

from mtg_goldfishing.adapters.memory import InMemoryStores
from mtg_goldfishing.adapters.sqlite import SqliteStores
from mtg_goldfishing.application.ports import (
    DeckRepository,
    GameRepository,
    RecordStore,
    UnitOfWork,
)


@dataclass(frozen=True)
class Stores:
    """The persistence ports one adapter implements."""

    games: GameRepository
    decks: DeckRepository
    records: RecordStore
    unit_of_work: UnitOfWork


OpenStores = Callable[[Path], AbstractContextManager[Stores]]
"""Opens one adapter's stores in a scratch directory, closing them afterwards."""


@contextmanager
def memory_stores(_: Path) -> Iterator[Stores]:
    stores = InMemoryStores()
    yield Stores(stores.games, stores.decks, stores.records, stores.unit_of_work)


@contextmanager
def sqlite_stores(directory: Path) -> Iterator[Stores]:
    stores = SqliteStores.open(directory / "goldfishing.db")
    try:
        yield Stores(stores.games, stores.decks, stores.records, stores.unit_of_work)
    finally:
        stores.database.close()


STORE_ADAPTERS = [memory_stores, sqlite_stores]
STORE_ADAPTER_IDS = ["memory", "sqlite"]
