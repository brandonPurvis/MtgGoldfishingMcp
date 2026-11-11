"""The MCP server's name, and the short guide to playing a game it gives every client."""

from __future__ import annotations

SERVER_NAME = "goldfishing"

# @spec TOOL-012, TOOL-034, TOOL-078, TOOL-084, TOOL-085, TOOL-100, TOOL-101, TOOL-102
# @spec TOOL-108
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
11. When you are unsure what a card does, read its rules text with `get_state` and `card` \
rather than relying on memory.

Contested games:
1. `new_game` with `opponents` starts a contested game and returns one seat id per seat; each \
seat's agent passes its own seat id as `game_id`.
2. Seats act one at a time. When your seat is not the seat to act, call `wait`; it returns \
when it is, with what you are asked. Until the game ends or your seat is eliminated, call \
`wait` again after every answer that says you are still waiting, however long: another seat \
taking its time is not a stalled game, and the answer says which seat is asked and for how \
long.
3. `wait` answers within its `timeout`: 30 seconds unless you give one, at most 60. Leave it \
at the default unless your client is known to wait longer than 60 seconds for a call. A \
`wait` that fails or comes back empty means your client stopped waiting, not that the game \
stalled; call `wait` again.
4. Spells and abilities go on the stack and resolve once every other seat has passed. When \
asked to respond, `play` or `effect` to respond, or `pass`.
5. Answer a `CHOICE` addressed to you with `choose`: blocks, a decision another seat's effect \
asks of you, or whether a spell still does what was stated. When an `ask` has you name a card, \
guess or choose a number, give it as `text`; every seat sees it.
6. State your own "whenever you cast" triggers in the `play` that casts the spell, as \
`cast_triggers`: a spell no other seat can answer resolves within that call.
7. After blocks, the attacking seat states what happens to the creatures with `effect` and \
`immediate: true`; the service deals the damage to seats, so the `effect` does not repeat it. \
A blocked attacker deals a seat nothing unless the attacking seat states its trample damage \
with `attack` and `trample` before combat damage.
8. Each response begins with what the other seats did since your last call.
9. Only the tested seat ends the game; an opposing seat's `end_game` concedes.
"""
