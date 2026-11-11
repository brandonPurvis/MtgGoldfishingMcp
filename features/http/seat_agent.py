"""A plain agent for one seat of a game played over HTTP: it waits until its seat is asked
something, answers it, and waits again, as an agent following the player brief would.

On its turn it plays a land and one cheap spell when it has them, then ends the turn; asked
to respond or reminded of a trigger, it passes; asked for blocks, it blocks nothing. It keeps
its opening hand, concedes or ends the game when told to, and stops once the game has ended
or its seat is out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from features.http.players import StatusLine, choice_for, hand, status_line
from tests.e2e.seat_clients import Answer, SeatClients
from tests.support.responses import headline

LANDS = ("Forest", "Command Tower", "City of Brass", "Ancient Tomb", "Evolving Wilds")
CHEAP_SPELLS = ("Sol Ring", "Llanowar Elves", "Elvish Mystic", "Birds of Paradise")
MOST_CALLS = 400
MOST_ERRORS = 30
STALE = "so your picture of it is stale"
"""An `ERROR` is expected now and then: during mulligans every seat keeps at once, and a seat
whose `after` another seat's keep made stale sends its keep again."""


@dataclass
class SeatAgent:
    """The agent playing seat `number` through its own client, with the id it was given."""

    clients: SeatClients
    number: int
    seat_id: str
    concede_on_turn: int | None = None
    end_on_turn: int | None = None
    calls: int = 0
    errors: list[str] = field(default_factory=list)
    last: Answer | None = None
    stopped: str | None = None
    """Why the agent stopped: `ended` or `out`."""
    _acted_on_turn: int = 0

    @property
    def unexpected_errors(self) -> list[str]:
        """Errors other than a keep sent after another seat's keep made its `after` stale."""
        return [e for e in self.errors if not (e.startswith("mulligan") and STALE in e)]

    def play(self) -> None:
        """Play the seat until the game has ended or the seat is out."""
        while self.calls < MOST_CALLS and len(self.errors) <= MOST_ERRORS:
            line = status_line(self._call("wait", timeout=30))
            if line.ended:
                self.stopped = "ended"
                return
            if line.out:
                self.stopped = "out"
                return
            self._answer(line)
        raise AssertionError(f"S{self.number} did not finish: {self.errors[-3:]}")

    def _answer(self, line: StatusLine) -> None:
        if "you" in line.to_keep:
            self._call("mulligan", keep=True, after=line.change)
            return
        act = line.act
        if act is None or act[0] != "you":
            return  # the wait timed out: the game is waiting on another seat
        asked = act[1]
        if asked == "turn":
            self._take_turn(line)
        elif asked in ("respond", "trigger"):
            self._call("pass", after=line.change)
        elif asked == "blocks":
            assert self.last is not None
            choice = choice_for(self.last, self.number)
            self._call("choose", choice_id=choice, blocks={}, after=line.change)
        else:
            raise AssertionError(f"S{self.number} was asked what it cannot answer: {line.text}")

    def _take_turn(self, line: StatusLine) -> None:
        if self.end_on_turn is not None and line.turn >= self.end_on_turn:
            self._call(
                "end_game",
                result="stalled",
                notes="Played over HTTP to the turn limit of the check.",
                after=line.change,
            )
            return
        if self.concede_on_turn is not None and line.turn >= self.concede_on_turn:
            self._call("end_game", result="loss", notes="Conceding.", after=line.change)
            return
        if line.step == "main1" and line.turn != self._acted_on_turn:
            self._acted_on_turn = line.turn
            self._main_phase(line.change)
            return
        if line.step != "end":
            self._call("advance", to="end", after=line.change)
            return
        held = hand(self._call("get_state"))
        arguments: dict[str, object] = {"to": "main1", "after": line.change}
        if len(held) > 7:
            arguments["discard"] = held[7:]
        self._call("advance", **arguments)

    def _main_phase(self, change: int) -> None:
        """Play a land, then cast one cheap spell, which goes on the stack."""
        held = hand(self._call("get_state"))
        land = next((card for card in held if card in LANDS), None)
        if land is not None:
            change = status_line(self._call("play", card=land, after=change)).change
        spell = next((card for card in held if card in CHEAP_SPELLS), None)
        if spell is not None:
            self._call("play", card=spell, after=change)

    def _call(self, tool: str, **arguments: object) -> Answer:
        self.calls += 1
        answer = self.clients.call(f"S{self.number}", tool, {"game_id": self.seat_id, **arguments})
        self.last = answer
        if headline(answer.text).startswith("ERROR"):
            self.errors.append(f"{tool} {arguments}: {answer.text}")
        return answer
