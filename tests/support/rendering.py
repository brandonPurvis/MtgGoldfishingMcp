"""A renderer for tests: one plain line naming the status, the summary's type and the change.

The real wording belongs to the MCP adapter; application tests need only text that can be
told apart and traced to the outcome it came from.
"""

from __future__ import annotations

import json

from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.application.ports import Rendered, Renderer


def plain_text(outcome: Outcome) -> str:
    """`<STATUS> <summary type>`, then ` #<change>` when the outcome is about a game."""
    text = f"{outcome.status.value} {type(outcome.summary).__name__}"
    if outcome.game is not None:
        text += f" #{outcome.game.change}"
    return text


def size_note(payload: object) -> str:
    return f"log export of {len(json.dumps(payload, default=str))} characters"


class PlainRenderer(Renderer):
    """Renders every outcome as `plain_text`; a successful `get_log` keeps a size note."""

    def render(self, tool: str, outcome: Outcome) -> Rendered:
        response = plain_text(outcome)
        if tool == "get_log" and outcome.status is Status.OK:
            return Rendered(response, size_note(outcome.payload))
        return Rendered(response, response)
