"""In-memory implementations of the ports, for tests."""

from mtg_goldfishing.adapters.memory.cards import InMemoryCardCache, InMemoryCardCatalog
from mtg_goldfishing.adapters.memory.clock import FixedClock
from mtg_goldfishing.adapters.memory.ids import FixedIdSource
from mtg_goldfishing.adapters.memory.storage import (
    InMemoryDeckRepository,
    InMemoryGameRepository,
    InMemoryRecordStore,
    InMemoryStores,
    InMemoryUnitOfWork,
)

__all__ = [
    "FixedClock",
    "FixedIdSource",
    "InMemoryCardCache",
    "InMemoryCardCatalog",
    "InMemoryDeckRepository",
    "InMemoryGameRepository",
    "InMemoryRecordStore",
    "InMemoryStores",
    "InMemoryUnitOfWork",
]
