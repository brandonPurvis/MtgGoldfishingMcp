"""The MCP server's name, and the short guide to playing a game it gives every client."""

from __future__ import annotations

SERVER_NAME = "goldfishing"

SERVER_INSTRUCTIONS = """\
MTG Goldfishing keeps the state of a Commander goldfish game you play against three \
imaginary opponents who take no actions. You make every decision and say what each card \
does; the service owns the shuffle, the bookkeeping, the checks and the records.

1. Call `load_deck` once with the deck list, then `new_game` with its deck id for each game.
2. Call `mulligan` until you keep.
3. Each turn: play a land, cast spells with `play`, record abilities and triggers with \
`effect`, declare attackers with `attack`, then `advance` to the next turn's main step \
(`advance` with to="main1").
4. State what each card does in `delta` (where things end up); the service pays costs, \
moves the card and shuffles when needed.
5. A `REJECTED` response is a failed rule check: nothing was applied, and you may resubmit \
the same call with `override` and a reason. An `ERROR` cannot be overridden: correct the call.
6. A `CHOICE` response shows cards revealed by a look or search; call `choose` to say \
where they go before doing anything else.
7. `advance` may stop early: at a step where one of your permanents has a step trigger, so \
you can resolve it with `effect`, or before cleanup when you must discard. The response \
says why; send `advance` again to continue.
8. Every response ends with a status line (turn, step, hand, lands, mana pool, life, damage \
dealt, commander damage, commander tax); use `get_state` only when that is not enough.
9. The status line ends with the game's change number (`#41`). Pass it as `after` on your \
next changing call so that a call sent twice is applied once.
10. When a notice says an end condition is reached, or you judge the game decided, call \
`end_game` with the result and your verdict. `get_log` returns the game's records as JSON.
"""
