"""The players of an HTTP scenario: the agent that loads decks and starts games, and one agent
per seat, each calling the real service through its own MCP client with its own id.

Nothing here looks inside the service: everything a step knows it read in a response, as an
agent would.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import takewhile
from typing import Any

from tests.e2e.seat_clients import Answer, SeatClients
from tests.support.responses import digest_lines, headline

STARTED = re.compile(r"^OK Started contested game (g\w+) with seed (\d+)\. Seats in turn order:$")
SEAT_LINE = re.compile(r"^S(\d+) (g\w+): deck (\w+), life (\d+)(, the tested seat)?\.$")
TURN = re.compile(r"^(?:Out · )?T(\d+) (\w+) \(S(\d+)\) · ")
ACT = re.compile(r" · Act (you|S\d+) (\w+) · ")
MULLIGAN_ACT = re.compile(r"^Mulligan \d+ · Hand \d+ · Act ([^#]+) · #\d+$")
CHANGE = re.compile(r"#(\d+)$")
CHOICE = re.compile(r"Choice (x\d+) \((\w+)\) for S(\d+)")
SEAT_HEADER = re.compile(r"^S(\d+)(?: \(you\))? · Life ")
ORCHESTRATOR = "orchestrator"
LOADED = re.compile(r"^OK (?:Loaded deck|Deck) (\w+)")


@dataclass(frozen=True)
class SeatLine:
    """One seat as `new_game` listed it."""

    number: int
    seat_id: str
    deck_id: str
    life: int
    tested: bool


@dataclass(frozen=True)
class StatusLine:
    """The facts a contested game's status line gives the seat that reads it."""

    text: str

    @property
    def change(self) -> int:
        found = CHANGE.search(self.text)
        assert found, self.text
        return int(found.group(1))

    @property
    def ended(self) -> bool:
        return self.text.startswith("Ended")

    @property
    def out(self) -> bool:
        return self.text.startswith("Out · ")

    @property
    def turn(self) -> int:
        """The number of turns the reading seat has begun."""
        found = TURN.match(self.text)
        assert found, self.text
        return int(found.group(1))

    @property
    def step(self) -> str:
        found = TURN.match(self.text)
        assert found, self.text
        return found.group(2)

    @property
    def active(self) -> int:
        found = TURN.match(self.text)
        assert found, self.text
        return int(found.group(3))

    @property
    def to_keep(self) -> list[str]:
        """During mulligans, the seats still to keep (`you` for the reading seat)."""
        found = MULLIGAN_ACT.match(self.text)
        return found.group(1).split() if found else []

    @property
    def act(self) -> tuple[str, str] | None:
        """Who is to act (`you` or `S<n>`) and what it is asked, once the game has begun."""
        found = ACT.search(self.text)
        return (found.group(1), found.group(2)) if found else None

    def field(self, name: str) -> str:
        """The value of a field such as `Life` or `Hand`."""
        found = re.search(rf"(?:^| · ){name} ([^·]+?)(?: · |$)", self.text)
        assert found, (name, self.text)
        return found.group(1)


def status_line(answer: Answer) -> StatusLine:
    return StatusLine(answer.text.splitlines()[-1])


def choice_for(answer: Answer, number: int) -> str:
    """The id of the latest pending choice an answer shows addressed to seat `number`."""
    found = [c.group(1) for c in CHOICE.finditer(answer.text) if int(c.group(3)) == number]
    assert found, answer.text
    return found[-1]


def hand(answer: Answer) -> list[str]:
    """The calling seat's hand, as its `get_state` lists it."""
    for line in answer.text.splitlines():
        if line.startswith("Hand ("):
            names = line.partition(": ")[2]
            return [] if names == "none" else names.split(", ")
    raise AssertionError(f"no hand listed in: {answer.text}")


def zone_of(answer: Answer, number: int, zone: str) -> list[str]:
    """The cards a `get_state` listing shows in seat `number`'s public zone (`Battlefield`,
    `Graveyard`, `Command zone`), by name."""
    lines = answer.text.splitlines()
    start = next(i for i, line in enumerate(lines) if _seat_header(line) == number)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if _seat_header(line) is not None:
            break
        if line.startswith(f"{zone} ("):
            names = line.partition(": ")[2]
            if names:
                return [] if names == "none" else names.split(", ")
            entries = takewhile(lambda entry: entry.startswith("  "), lines[index + 1 :])
            return [_permanent_name(entry) for entry in entries]
    return []


def _seat_header(line: str) -> int | None:
    found = SEAT_HEADER.match(line)
    return int(found.group(1)) if found else None


def _permanent_name(entry: str) -> str:
    """A battlefield line's card name (`  c98 Sol Ring: mana {T}: {C}{C}` gives `Sol Ring`)."""
    name = entry.strip().split(" ", 1)[1]
    return name.split(": ", 1)[0].split(" (owner ", 1)[0]


class Table:
    """The game the scenario plays over HTTP and the players at it."""

    def __init__(self, url: str) -> None:
        self.clients = SeatClients(url)
        self.deck_id: str | None = None
        self.opposing_deck_id: str | None = None
        self.game_id: str | None = None
        self.seats: dict[int, SeatLine] = {}
        self.answers: list[Answer] = []

    def close(self) -> None:
        self.clients.close()

    # -------------------------------------------------------------- calls

    def call(self, who: str, tool: str, **arguments: object) -> Answer:
        answer = self.clients.call(who, tool, arguments)
        self.answers.append(answer)
        return answer

    def as_seat(self, number: int, tool: str, **arguments: object) -> Answer:
        """A call by the agent playing seat `number`, through its own client and seat id."""
        return self.call(f"S{number}", tool, game_id=self.seat_id(number), **arguments)

    def load(self, cards: str, commander: str) -> str:
        """Load a deck, or find it already loaded by an earlier scenario on the same service."""
        answer = self.call(ORCHESTRATOR, "load_deck", cards=cards, commander=commander)
        loaded = LOADED.match(headline(answer.text))
        assert loaded, answer.text
        return loaded.group(1)

    def start(self, opponents: list[str], seed: int, **arguments: object) -> Answer:
        answer = self.call(
            ORCHESTRATOR,
            "new_game",
            deck_id=self.deck_id,
            opponents=opponents,
            seed=seed,
            **arguments,
        )
        lines = answer.text.splitlines()
        started = STARTED.match(lines[0])
        if started:
            self.game_id = started.group(1)
            self.seats = {}
            for line in lines[1:]:
                found = SEAT_LINE.match(line)
                if found:
                    number, seat_id, deck_id, life, tested = found.groups()
                    self.seats[int(number)] = SeatLine(
                        int(number), seat_id, deck_id, int(life), tested is not None
                    )
        return answer

    # -------------------------------------------------------------- reading

    def seat_id(self, number: int) -> str:
        return self.seats[number].seat_id

    @property
    def tested(self) -> int:
        return next(seat.number for seat in self.seats.values() if seat.tested)

    @property
    def last(self) -> Answer:
        return self.answers[-1]

    @property
    def status_line(self) -> StatusLine:
        return status_line(self.last)

    @property
    def digest(self) -> list[str]:
        return digest_lines(self.last.text)

    def state_of(self, number: int) -> Answer:
        """The seat's own `get_state`, which is not kept as the scenario's latest answer."""
        return self.clients.call(f"S{number}", "get_state", {"game_id": self.seat_id(number)})

    def log(self, number: int, **arguments: object) -> dict[str, Any]:
        answer = self.as_seat(number, "get_log", **arguments)
        log: dict[str, Any] = json.loads(answer.text)
        return log
