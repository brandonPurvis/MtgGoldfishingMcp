"""The operating system's randomness and clock, behind the `IdSource` and `Clock` ports."""

from mtg_goldfishing.adapters.system.clock import SystemClock
from mtg_goldfishing.adapters.system.ids import RandomIdSource

__all__ = ["RandomIdSource", "SystemClock"]
