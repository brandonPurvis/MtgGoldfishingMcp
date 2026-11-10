# Tools — Specs

Design: `tools-design.md`. Prefix: `TOOL`.

## Serving

- [ ] **TOOL-001**: The service shall serve MCP over streamable HTTP in stateless mode at the path `/mcp` of a FastAPI application, under the MCP server name `goldfishing`.
- [ ] **TOOL-002**: When `GET /health` is requested, the service shall respond with a success status.
- [ ] **TOOL-003**: The service shall listen on the address in `MTG_GOLDFISHING_HOST`, defaulting to `127.0.0.1`, and the port in `MTG_GOLDFISHING_PORT`, defaulting to `8000`.
- [ ] **TOOL-004**: The service shall keep its database at the path in `MTG_GOLDFISHING_DB`, defaulting to `data/mtg-goldfishing.sqlite3`.
- [ ] **TOOL-005**: The command `uv run mtg-goldfishing` shall start the service.
- [ ] **TOOL-006**: The repository shall carry a `.mcp.json` that connects Claude Code to `http://127.0.0.1:8000/mcp` under the server name `goldfishing`.

## Tool surface

- [ ] **TOOL-007**: The MCP adapter shall expose exactly the tools `load_deck`, `new_game`, `mulligan`, `get_state`, `play`, `effect`, `choose`, `attack`, `advance`, `end_game` and `get_log`.
- [ ] **TOOL-008**: Every game-scoped tool shall take `game_id` as its first parameter.
- [ ] **TOOL-009**: Each of `mulligan`, `play`, `effect`, `choose`, `attack`, `advance` and `end_game` shall accept an optional `after` parameter.
- [ ] **TOOL-010**: When an object or list parameter (`delta`, `choices`, `pay`, `expect`, `selections`, `definitions`) is given as a JSON string, the MCP adapter shall parse the string and use the result.
- [ ] **TOOL-011**: Each tool description shall state, in order, the tool's purpose in one sentence, what the service does automatically as a result, each parameter's meaning with an example value, and what can be overridden.
- [ ] **TOOL-012**: The MCP server's instructions shall describe: loading a deck once and starting games on it; mulligans; the shape of a turn; stating what a card does in a delta; overriding a `REJECTED` response; answering a `CHOICE` response with `choose`; why `advance` may stop early; the status line; passing the change number as `after`; and ending the game.
- [ ] **TOOL-013**: The MCP adapter shall contain no rule of play and shall reach the service only by calling use cases.

## Response format

- [x] **TOOL-014**: Every tool except a successful `get_log` shall respond with a single text item made of a status-and-summary line, zero or more event lines, and, for a response about an existing game, a status line.
- [x] **TOOL-015**: The first word of a text response shall be `OK`, `REJECTED`, `ERROR` or `CHOICE`.
- [x] **TOOL-016**: Event lines shall appear in this order when present: steps entered; payment; moves, tokens created and cards drawn; cards revealed for a pending choice with its choice id; combat damage per attacker; assumptions; reminders; why an advance stopped; expectation warnings; notices.
- [x] **TOOL-017**: The status line for a started game shall read `T<turn> <step> · Hand <n> · Lands <n> (<n> untapped) · Pool <mana> · Life <n> · Dmg <n>/120 · Cmdr <a>/<b>/<c> · Tax <n> · #<change>`.
- [x] **TOOL-018**: While a game has two commanders, the status line shall show `Cmdr` and `Tax` as one group per commander separated by `|`, in the commanders' name order.
- [x] **TOOL-019**: While a game's status is `mulligan`, the status line shall read `Mulligan <k> · Hand <n> · #<change>`.
- [x] **TOOL-020**: While a game has a pending choice, the status line shall end with ` · CHOICE pending`.
- [x] **TOOL-021**: While a game's status is `ended`, the status line shall begin with `Ended (<result>) · `.
- [x] **TOOL-022**: When a response does not concern an existing game, the response shall have no status line.
- [x] **TOOL-023**: When a response is `REJECTED`, its summary shall say what failed and that the call can be resubmitted with `override`.
- [x] **TOOL-024**: While a game has raised notices, every text response about that game shall include them, whatever the response's status.
- [x] **TOOL-025**: A response to `play`, `effect`, `attack` or `advance` shall not list the full hand or the full battlefield.
- [x] **TOOL-026**: All response text shall be produced by one renderer from a use case's outcome, with one rendering per event type.

## MCP details

- [ ] **TOOL-027**: When a response's status is `ERROR`, the MCP result shall set its error flag; when the status is `OK`, `REJECTED` or `CHOICE`, it shall not.
- [ ] **TOOL-028**: If a tool call's arguments are missing, of the wrong type or otherwise malformed, then the MCP adapter shall respond in the text `ERROR` format rather than with a protocol-level fault, and a call record shall be stored for the call.

## Player brief

- [ ] **TOOL-029**: The repository shall carry a Claude Code subagent definition at `.claude/agents/goldfish-player.md` that restricts the subagent to the `goldfishing` server's tools.
- [ ] **TOOL-030**: The player brief shall instruct the subagent to play as a strong player aiming to win as fast as the deck can, make every decision itself, give a `reason` on non-obvious plays, pass `after` on every changing call, resolve or consciously pass reminders, end the game with `end_game` and a verdict, and return the game id, seed and verdict.
