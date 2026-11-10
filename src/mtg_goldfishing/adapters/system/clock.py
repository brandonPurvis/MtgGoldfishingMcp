"""The time from the operating system's clock."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """The current time in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
