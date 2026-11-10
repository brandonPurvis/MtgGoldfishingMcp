"""The real id source, clock and game locks, behind `IdSource`, `Clock` and `GameLocks`."""

from mtg_goldfishing.adapters.system.clock import SystemClock
from mtg_goldfishing.adapters.system.ids import RandomIdSource
from mtg_goldfishing.adapters.system.locks import InProcessGameLocks

__all__ = ["InProcessGameLocks", "RandomIdSource", "SystemClock"]
