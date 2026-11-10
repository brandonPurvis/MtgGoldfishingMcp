"""The time from the operating system's clock."""

from __future__ import annotations

from datetime import UTC, datetime

from mtg_goldfishing.application.ports import Clock


class SystemClock(Clock):
    """The current time in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
