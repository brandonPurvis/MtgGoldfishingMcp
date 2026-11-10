---
parent: high-level-design
prefix: TOOL
---

# Tools

## Context and Design Philosophy

This component is the service's face: the MCP tools an agent sees, the words that describe them, the text every response is written in, and the process that serves them. An agent learns the service from nothing but this. If a description must be guessed at or a response leaves the agent unsure where the game stands, the design has failed regardless of how correct the logic behind it is.

Following the tenet *Clear before cheap*, text is kept short but never at the cost of the agent having to ask again.

The component is the MCP adapter: the driving adapter of the service (see `application`). It holds no game logic and no orchestration. For each call it checks that the arguments have the right shape, builds the use case's request in domain types, calls the use case, and renders the outcome it gets back as response text. Loading, deciding and saving all happen behind the use case.

## Serving

One process: a FastAPI application with the MCP server mounted at `/mcp`, speaking MCP's streamable HTTP transport in stateless mode, so that no call depends on an earlier connection. `GET /health` returns a small success response for checking that the service is up.

Started with `uv run mtg-goldfishing`.

| Setting | Environment variable | Default |
|---|---|---|
| Address to listen on | `MTG_GOLDFISHING_HOST` | `127.0.0.1` |
| Port | `MTG_GOLDFISHING_PORT` | `8000` |
| Database file | `MTG_GOLDFISHING_DB` | `data/mtg-goldfishing.sqlite3` |

The MCP server is named `goldfishing`. The repository carries a `.mcp.json` that connects Claude Code to `http://127.0.0.1:8000/mcp` under that name.

## The Tools

| Tool | Owned by | Purpose in the description's first sentence |
|---|---|---|
| `load_deck` | `deck` | Load a Commander deck list once and get a deck id to start games with. |
| `new_game` | `game` | Start a goldfish game on a loaded deck: shuffles and deals seven. |
| `mulligan` | `game` | Keep the opening hand or take a mulligan. |
| `get_state` | `game` | List the hand, battlefield and other zones when the status line is not enough. |
| `play` | `play` | Play a land or cast a spell, stating what it does. |
| `effect` | `play` | Record anything that happens without playing a card. |
| `choose` | `play` | Finish a look or search by saying where the revealed cards go. |
| `attack` | `combat` | Declare attackers and which are blocked. |
| `advance` | `turn` | Move to the next step, or forward to a named step. |
| `end_game` | `game` | End the game with a result and verdict. |
| `get_log` | `records` | Return the game's records as JSON for analysis. |

Every game-scoped tool takes `game_id` as its first parameter. Every tool that changes a game — `mulligan`, `play`, `effect`, `choose`, `attack`, `advance`, `end_game` — also takes an optional `after`, the change number the agent last saw (see `game`).

A parameter that is an object or a list (`delta`, `choices`, `pay`, `expect`, `selections`, `definitions`) is also accepted as a JSON string holding that object or list, since some clients send it that way.

### Descriptions

Each tool description states, in this order: what the tool is for in one sentence; what the service does automatically as a result; each parameter's meaning with one example value; and what can be overridden. Descriptions use the terms in `GLOSSARY.md`. The shape of a delta is described once, in `play`, and `effect` refers to it.

### Server instructions

The MCP server's instructions field carries a short guide to playing a game, so an agent connecting cold knows the order of things:

1. `load_deck` once, then `new_game` for each game.
2. `mulligan` until you keep.
3. Each turn: play a land, cast spells with `play`, record abilities and triggers with `effect`, `attack`, then `advance` to the next turn's main step.
4. State what each card does in `delta`; the service pays costs, moves the card and shuffles when needed.
5. A `REJECTED` response can be resubmitted with `override` and a reason; an `ERROR` cannot.
6. A `CHOICE` response shows cards revealed by a look or search; call `choose` to say where they go before doing anything else.
7. `advance` may stop early: at a step where one of your permanents has a trigger, so you can resolve it with `effect`, or before cleanup when you must discard. The response says why; send `advance` again to continue.
8. Every response ends with a status line; use `get_state` only when that is not enough.
9. The status line ends with the game's change number (`#41`). Pass it as `after` on your next changing call so that a call sent twice is applied once.
10. When a notice says an end condition is reached, or you judge the game decided, call `end_game`.

## Response Format

Every tool except `get_log` responds with plain text:

```
<STATUS> <one-line summary>
<zero or more event lines>
<status line>
```

**Status** is one of:

| Status | Meaning |
|---|---|
| `OK` | Applied. |
| `REJECTED` | A rule check failed; nothing was applied; may be resubmitted with `override`. |
| `ERROR` | Structurally impossible or malformed; nothing was applied; cannot be overridden. |
| `CHOICE` | Applied, and a choice is now pending; call `choose`. |

**Event lines** appear in a fixed order when present: steps entered (`end → cleanup → T7 untap → upkeep`); payment; moves, tokens created, and cards drawn; cards revealed for a pending choice, with the choice id; combat damage per attacker; what the service assumed (`Assumed: X = 0`); reminders (`Reminder (upkeep): Phyrexian Arena`); why an advance stopped; expectation warnings (`Warning: untapped_lands is 1, expected 2`); notices (`Notice: 120 damage reached`). `get_state` puts its listing in the event lines.

Current notices appear on every response about a game, whatever its status: `OK`, `REJECTED`, `ERROR`, `CHOICE`, and `get_state`.

**Status line**, for any response about a game that has started:

```
T<turn> <step> · Hand <n> · Lands <n> (<n> untapped) · Pool <mana> · Life <n> · Dmg <n>/120 · Cmdr <a>/<b>/<c> · Tax <n> · #<change>
```

With two commanders, `Cmdr` and `Tax` show a group per commander separated by `|`, in the commanders' name order; `get_state` names them. While a choice is pending the line ends with ` · CHOICE pending`. For an ended game the line begins `Ended (<result>) · `. During mulligans the status line is `Mulligan <k> · Hand <n> · #<change>`. For responses not about an existing game (`load_deck`, an unknown game id) there is no status line.

A `REJECTED` or `ERROR` summary says what was wrong and what to do about it:

```
REJECTED Cost {6}{R} not payable: 5 mana available. Resubmit with override to cast anyway.
T6 main1 · Hand 4 · Lands 6 (5 untapped) · Pool {} · Life 40 · Dmg 22/120 · Cmdr 7/0/0 · Tax 2 · #41
```

Responses to routine plays do not list the battlefield or the hand; `get_state` does that.

### In MCP terms

A response is a single text content item. `ERROR` responses set the MCP result's error flag; `OK`, `REJECTED` and `CHOICE` do not, because a rejection is an ordinary, expected outcome the agent acts on. Arguments that fail the tool's schema are answered in the same text format as an `ERROR`, not as a protocol-level fault, so the agent always reads one format. Such a response sets the error flag, carries the status line when the call named an existing game, and is saved as a call record like any other call. To make this possible the tools declare permissive schemas to the MCP layer and validate arguments themselves.

## Player Brief

A Claude Code subagent definition at `.claude/agents/goldfish-player.md`. It restricts the subagent to the service's tools and tells it how to conduct a game for a deck-testing workflow:

- play each game as a strong player would, aiming to win as fast as the deck can;
- make every decision itself, and give a `reason` on plays where the choice was not obvious;
- use `expect` on plays where it is tracking a number closely;
- pass `after` on every changing call;
- resolve reminders with `effect` or consciously pass them;
- end the game with `end_game` and a verdict naming what the deck did well and badly;
- return the game id, the seed and the verdict as its final message.

It is given a deck id (or a deck list to load), and optionally a seed and turn limit.

## Rendering

Response text is produced in one place, by a renderer that turns an outcome's status, summary, events and game summary into the format above. Each event type has one rendering. No other code in the service builds response text, so a change of wording is a change to the renderer alone.

## Code Layout

The adapter lives in `src/mtg_goldfishing/adapters/mcp/`: tool definitions and descriptions, argument shaping, the renderer, and the FastAPI application. The overall layout and the rule that adapters depend inward are in `application`.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Response format | Compact plain text with a fixed shape | JSON | Text costs fewer tokens and an agent reads it directly; the fixed shape keeps it parseable by eye. |
| Status line on every game response | Always present | Only on request | The agent's picture of the game is re-anchored on every call, which is what prevents drift and makes `get_state` rare. |
| Rejections and the MCP error flag | Not flagged as errors | Flagged | A rejection is a normal turn of the conversation; flagging it invites clients to treat it as a fault. |
| Transport | Streamable HTTP, stateless | stdio; stateful sessions | One process for all agents; stateless calls suit game ids that already carry all context, and suit hosting later. |
| Where playing instructions live | Server instructions and tool descriptions, plus a subagent definition | Only a subagent definition | Instructions that travel with the server work for any client; the subagent definition is the convenience for Claude Code. |
| Schema failures | Answered as `ERROR` text | Protocol error | One format for the agent to read. |

## Open Questions & Future Decisions

### Deferred
1. Authentication and per-caller isolation, when the service is offered to others.
2. Refinement of tool names, descriptions and response wording by measured trial with agents.

## References

- `docs/high-level-design.md` (tenet *Clear before cheap*; goal 9)
- `GLOSSARY.md`
- Model Context Protocol Python SDK: `https://github.com/modelcontextprotocol/python-sdk`
