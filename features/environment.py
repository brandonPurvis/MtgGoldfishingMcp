"""The agent each scenario plays as: it calls the MCP adapter's tool functions in-process, over
the service with in-memory adapters and recorded card data, and reads the text they answer.

Nothing here opens a database file, reaches the network or starts a server.
"""

# @spec APP-024, APP-025

from __future__ import annotations

import io
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import parse
from behave import register_type

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.mcp.tools import ToolResponse, ToolSurface
from mtg_goldfishing.domain.game.model import Game, Zone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.service import a_service  # noqa: E402  (needs the repository root on the path)

GAME_SCOPED = (
    "mulligan",
    "get_state",
    "play",
    "effect",
    "choose",
    "attack",
    "advance",
    "end_game",
    "get_log",
)
STATUS_LINE_CHANGE = re.compile(r"#(\d+)(?: · CHOICE pending)?$")


@parse.with_pattern(r'[^"]+')
def _quoted(text: str) -> str:
    return text


register_type(Quoted=_quoted)


class Agent:
    """The agent at play: it calls tools by name and reads the text each one answers."""

    def __init__(self) -> None:
        self.harness = a_service(
            renderer=TextRenderer(),
            game_ids=tuple(f"featgame{n:02d}" for n in range(20)),
            seeds=tuple(range(1000, 1020)),
        )
        self.tools = ToolSurface(self.harness.service)
        self.deck_id: str | None = None
        self.game_id: str | None = None
        self.games: list[str] = []
        self.responses: list[ToolResponse] = []
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.change_before: int | None = None
        """The game's change number just before the latest call."""
        self.change_at_start: int | None = None
        """The change number a scenario's first changing call was sent after."""
        self.hand_before_look: int | None = None
        self.look = ""
        """The response that revealed cards for a pending choice."""
        self.log: dict[str, Any] = {}
        """The last log export read."""

    def call(self, tool: str, **arguments: object) -> ToolResponse:
        """Call a tool as an agent would; game-scoped tools go to the current game."""
        if tool in GAME_SCOPED and "game_id" not in arguments:
            arguments = {"game_id": self.game_id, **arguments}
        if self.game_id is not None and self.harness.stores.games.get(self.game_id):
            self.change_before = self.harness.game(self.game_id).change
        response = self.tools.call(tool, arguments)
        self.calls.append((tool, dict(arguments)))
        self.responses.append(response)
        return response

    @property
    def last(self) -> ToolResponse:
        return self.responses[-1]

    @property
    def text(self) -> str:
        return self.last.text

    @property
    def status_line(self) -> str:
        return self.text.splitlines()[-1]

    def change(self) -> int:
        """The change number at the end of the last status line."""
        found = STATUS_LINE_CHANGE.search(self.status_line)
        assert found, self.status_line
        return int(found.group(1))

    def game(self) -> Game:
        assert self.game_id is not None, "no game started"
        return self.harness.game(self.game_id)

    def names_in(self, zone: Zone) -> list[str]:
        game = self.game()
        return [card.name for card in game.in_zone(zone, game.tested.number)]

    def start_game(self, seed: int) -> ToolResponse:
        """Start a game on the loaded deck; it becomes the current game."""
        response = self.call("new_game", deck_id=self.deck_id, seed=seed)
        assert response.text.startswith("OK Started game "), response.text
        self.game_id = response.text.split()[3]
        self.games.append(self.game_id)
        return response

    def arrange(self, names: Sequence[str], zone: Zone) -> None:
        """See that the game holds these cards in `zone` (hand or battlefield).

        Missing cards are brought there with one `effect` call, as an agent recording an
        effect would: moved from the hand or the command zone, fetched from the library.
        """
        move: list[str] = []
        fetch: list[str] = []
        for name, wanted in Counter(names).items():
            missing = wanted - self.names_in(zone).count(name)
            sources = [Zone.COMMAND] if zone is Zone.HAND else [Zone.HAND, Zone.COMMAND]
            for source in sources:
                taken = min(missing, self.names_in(source).count(name))
                move.extend([name] * taken)
                missing -= taken
            fetch.extend([name] * max(missing, 0))
        delta: dict[str, object] = {}
        if move:
            delta["move"] = {zone.value: move}
        if fetch:
            delta["fetch"] = {zone.value: fetch}
        if delta:
            response = self.call("effect", source="arranging the scenario", delta=delta)
            assert response.text.startswith("OK"), response.text

    def discard_down_to(self, size: int) -> None:
        """Discard the last cards in hand until it holds `size`, with one `effect` call."""
        hand = self.names_in(Zone.HAND)
        if len(hand) > size:
            discard = hand[size:]
            response = self.call(
                "effect", source="arranging the scenario", delta={"discard": discard}
            )
            assert response.text.startswith("OK"), response.text


def before_all(context: Any) -> None:
    # Steps quote response text (`·`, `→`); a console on a legacy code page cannot print it.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def before_scenario(context: Any, scenario: Any) -> None:
    context.agent = Agent()
