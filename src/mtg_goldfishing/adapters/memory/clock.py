"""A clock for tests: it tells the time it was set to."""

from __future__ import annotations

from datetime import UTC, datetime

DEFAULT_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _in_utc(time: datetime) -> datetime:
    if time.tzinfo is None:
        raise ValueError(f"{time} has no time zone")
    return time.astimezone(UTC)


# @spec APP-013
class FixedClock:
    """Tells the time it was last set to, in UTC, until the test sets another."""

    def __init__(self, time: datetime = DEFAULT_TIME) -> None:
        self._time = _in_utc(time)

    def set(self, time: datetime) -> None:
        self._time = _in_utc(time)

    def now(self) -> datetime:
        return self._time
