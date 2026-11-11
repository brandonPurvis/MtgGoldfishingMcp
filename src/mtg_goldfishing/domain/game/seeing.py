"""What a seat may see of the events of a call."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.events import Event
from mtg_goldfishing.domain.game.seats import SeatNumber


def as_seen_by(events: Sequence[Event], seat: SeatNumber) -> tuple[Event, ...]:
    """The events as `seat` may see them; not built yet."""
    raise NotImplementedError("M3a: what a seat may see is not built")
