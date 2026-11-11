"""The outcome every use case returns: a status, a headline, events and the game summary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mtg_goldfishing.domain.events import Event
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.summary import GameSummary


class Status(Enum):
    OK = "OK"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
    CHOICE = "CHOICE"


@dataclass(frozen=True)
class DigestElement:
    """One change another seat made: that seat, the change number and the change's events
    as the calling seat may see them."""

    seat: SeatNumber
    change: int
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Outcome:
    """What a call did. Response text and the log entry are both built from this.

    `payload` carries `get_state`'s listing or `get_log`'s export. `seat` is the calling
    seat in a contested game, and None in a goldfish game. `digest` holds, oldest first, the
    changes other seats made since the calling seat's digest baseline; it is None in a
    goldfish game and for `get_log`.
    """

    status: Status
    summary: Event
    events: tuple[Event, ...] = ()
    game: GameSummary | None = None
    payload: object | None = None
    seat: SeatNumber | None = None
    digest: tuple[DigestElement, ...] | None = None


@dataclass(frozen=True)
class Answer:
    """A use case's result: the outcome and the response text it was rendered to."""

    outcome: Outcome
    response: str
