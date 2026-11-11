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
| `pass` | `stack` | Decline to respond when your seat is asked (contested games). |
| `wait` | `application` | Wait until your seat has something to do, then say what it is (contested games). |
| `end_game` | `game` | End the game with a result and verdict. |
| `get_log` | `records` | Return the game's records as JSON for analysis. |

The purpose sentence of a tool that serves both kinds of game describes it for a goldfish game, so an agent playing one reads it unchanged; what the tool does in a contested game follows in the parts marked "Contested games:" (see Descriptions) — `new_game` starts a contested game when given `opponents`. `pass` and `wait` serve contested games and say so in their purpose sentence.

Every game-scoped tool takes `game_id` as its first parameter: the id `new_game` gave the calling seat, which for the tested seat, and so in every goldfish game, is the game id. Every tool that changes a game — `mulligan`, `play`, `effect`, `choose`, `attack`, `advance`, `pass`, `end_game` — also takes an optional `after`, the change number the calling seat last saw (see `game`).

A parameter that is an object or a list (`delta`, `choices`, `pay`, `expect`, `selections`, `definitions`) is also accepted as a JSON string holding that object or list, since some clients send it that way.

### Descriptions

Each tool description states, in this order: what the tool is for in one sentence; what the service does automatically as a result; each parameter's meaning with one example value; and what can be overridden. Descriptions use the terms in `GLOSSARY.md`. The shape of a delta is described once, in `play`, and `effect` refers to it. What a tool does only in a contested game is described in a final sentence or parameter marked "Contested games:", so an agent playing a goldfish game can pass over it.

Three things about combat in a contested game are easy to get wrong from the parameter list alone, and the descriptions say them outright (see `combat`):

- `effect`: an immediate `effect` that states the result of combat gives only what happens to the creatures. The service deals the declared attack's damage to seats on entering `combat_damage`, whatever an earlier `effect` said, so a `life` or `damage` entry for that damage would be applied on top of it.
- `attack`: a `damage` entry for a blocked attacker is dealt in full to the seat it attacks; the service subtracts nothing for blockers, so the entry is the damage that gets past them.
- `attack`: the call may stop before attackers are declared, at a step where another seat has a reminder. Nothing is declared or tapped, and the attacking seat sends `attack` again once it is the seat to act.

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

It continues with a short section on contested games:

1. `new_game` with `opponents` starts a contested game and returns one seat id per seat; each seat's agent passes its own seat id as `game_id`.
2. Seats act one at a time. When it is not your seat's turn to act, call `wait`; it returns when it is, with what you are being asked.
3. Spells and abilities go on the stack and resolve once every other seat has passed. When you are asked to respond, `play` or `effect` to respond, or `pass`.
4. Answer a `CHOICE` addressed to you with `choose`: blocks, a decision another seat's effect asks of you, or whether a spell still does what you said.
5. After blocks, the attacking seat states what happens to the creatures with `effect` and `immediate: true`; the service deals the damage to seats, so the `effect` does not repeat it.
6. Each response begins with what the other seats did since your last call.
7. Only the tested seat ends the game; an opposing seat's `end_game` concedes.

## Response Format

Every tool except `get_log` responds with plain text:

```
<digest lines, contested games only>
<STATUS> <one-line summary>
<zero or more event lines>
<status line>
```

### Digest

In a contested game a response begins with one line for each change other seats made since the calling seat's digest baseline — its previous response that carried a digest (see `application`) — oldest first, each as the calling seat may see it (see `game`): the public form, except that a card another seat's call moved into, between or out of the calling seat's own hand or library is named to it. A seat's first response covers the other seats' changes since the game began. For example, as seat 3 reads it:

```
S2 #53: cast Swords to Plowshares (s3), targeting Llanowar Elves; S3 passed automatically: no untapped permanents
S4 #54: passed
S1 #55: passed; s3 resolved: Llanowar Elves exiled; S1 life +1
S2 #56: cleanup → S3 T5 untap → upkeep → draw → main1; S3 drew Forest
```

A line belongs to the seat whose call made the change, and a change has one line. Everything the change caused is listed on it, separated by `;`, including what it caused for other seats: an automatic pass, the resolution of another seat's item, the start of the next seat's turn. Seats are always named `S<n>` in a digest, the reader's own seat included; every line has at least one event, because every accepted change has a public form. A mulligan taken reads `S2 took a mulligan (2 taken)` and a kept hand `S2 kept 6, bottomed 1`; a look at a hand names the looking seat and whose hand, never the cards: `S3 looks at S1's hand (CHOICE hand)`. A response with nothing new has no digest lines. A `get_log` response is JSON and carries no digest; what happened before it is shown by the seat's next text response. A goldfish game's responses never have them.

**Status** is one of:

| Status | Meaning |
|---|---|
| `OK` | Applied. |
| `REJECTED` | A rule check failed; nothing was applied; may be resubmitted with `override`. |
| `ERROR` | Structurally impossible or malformed; nothing was applied; cannot be overridden. |
| `CHOICE` | Applied, and a choice is now pending; call `choose`. |

**Event lines** appear in a fixed order when present: in a contested game, what the calling seat is now asked to do, when it is a seat to act (`You are asked to respond to s4: Counterspell from S3.`); a statement that the call was already applied (`Already applied as change #41; nothing was applied again.`); overridden rule checks (`Overridden (<reason>): ...`); steps entered (`end → cleanup → T7 untap → upkeep`); payment; moves, tokens created, and cards drawn; cards revealed for a pending choice, with the choice id; combat damage per attacker; what the service assumed (`Assumed: X = 0`); reminders (`Reminder (upkeep): Phyrexian Arena`); why an advance stopped; expectation warnings (`Warning: untapped_lands is 1, expected 2`); in a contested game, items put on the stack, automatic passes, resolutions and counters, and eliminations; notices (`Notice: 120 damage reached`). `get_state` puts its listing in the event lines.

Current notices appear on every response about a game, whatever its status: `OK`, `REJECTED`, `ERROR`, `CHOICE`, and `get_state`.

**Status line** of a goldfish game, for any response about a game that has started:

```
T<turn> <step> · Hand <n> · Lands <n> (<n> untapped) · Pool <mana> · Life <n> · Dmg <n>/120 · Cmdr <a>/<b>/<c> · Tax <n> · #<change>
```

With two commanders, `Cmdr` and `Tax` show a group per commander separated by `|`, in the commanders' name order; `get_state` names them. While a choice is pending the line ends with ` · CHOICE pending`. For an ended game the line begins `Ended (<result>) · `. `Cmdr` shows that commander's damage to each opponent, and an empty pool reads `{}`. While a game has no step — during mulligans, or once it has ended before the hand was kept — the status line is `Mulligan <k> · Hand <n> · #<change>`, where *k* is the number of mulligans taken, so a game ended during mulligans reads `Ended (loss) · Mulligan 0 · Hand 7 · #2`. For responses not about an existing game (`load_deck`, an unknown game id) there is no status line.

**Status line** of a contested game, as the calling seat sees it:

```
T<turn> <step> (S<active>) · You S<n> · Hand <n> · Lands <n> (<n> untapped) · Pool <mana> · Life <n> · S<n> <life> ... · Cmdr <dmg>/... · Tax <n> · Stack <n> · Act <who> <what> · #<change>
```

- `T<turn>` is the number of turns the calling seat has begun; `(S<active>)` names the active seat.
- `You S<n>` is the calling seat's number; `Hand` to `Life` are its own.
- One `S<n> <life>` per other seat in ascending seat number, `out` for an eliminated seat. Seat 3 of four reads `S1`, `S2`, `S4`.
- `Cmdr` shows the calling seat's commander damage to each other seat, one number per life group and in the same order; an eliminated seat keeps its number, so positions always match. With two commanders, `Cmdr` and `Tax` each show a group per commander separated by `|`, in the commanders' name order, as in a goldfish game.
- `Stack <n>` appears only when the stack is not empty.
- `Act` names the seat to act and, in one word, what it is asked: `Act you respond`, `Act S3 blocks`, `Act S2 turn`. The calling seat is `you`.
- The line never ends with ` · CHOICE pending`: `Act` already says which seat a pending choice waits on and its kind.
- During mulligans the line is `Mulligan <k> · Hand <n> · Act <seats> · #<change>`, where `<seats>` lists every seat still to keep in ascending seat number, separated by spaces, with no word after them: `Mulligan 1 · Hand 7 · Act you S3 · #4`.
- For an eliminated calling seat the line begins `Out · `.
- For an ended game the line begins `Ended (<result>) · `, ahead of any `Out · `, and has no `Act` and no `Stack`: no seat is asked and the stack was discarded. A game ended during mulligans reads `Ended (stalled) · Mulligan 0 · Hand 7 · #3`.

```
T7 main1 (S2) · You S1 · Hand 4 · Lands 6 (6 untapped) · Pool {} · Life 33 · S2 40 · S3 out · S4 12 · Cmdr 7/0/14 · Tax 2 · Stack 1 · Act you respond · #57
```

What a seat is asked has one vocabulary, used by `Act`, by the first event line of a response to a seat to act, by the `ERROR` to a seat that is not, and by a `wait` that times out:

| The seat is to act because | `Act` word | Sentence (`You are asked to ...` / `S3 is asked to ...`) |
|---|---|---|
| A response window is asking it | `respond` | `respond to s4` (the event line adds `: Counterspell from S3`); `respond to the attack`; `respond in the end step` |
| A reminder waits for it and it is not the active seat | `trigger` | `record or pass the upkeep trigger of Rhystic Study` |
| A pending choice is addressed to it | the choice's kind: `look`, `search`, `hand`, `ask`, `resolve`, `blocks` | `answer the blocks choice` |
| It is the active seat and nothing else waits | `turn` | `take its turn` (`take your turn`) |
| It has not kept (mulligans) | none; see the mulligan line | `keep or mulligan` |

A `wait` that times out answers `OK Still waiting: S3 is asked to respond to s4.`

A call from a seat that is not a seat to act is answered as an `ERROR` that names the seat to act and what it is asked, and suggests `wait`:

```
ERROR Not your seat's call: S3 is asked to respond to s4. Call wait to be told when it is yours.
```

A `REJECTED` or `ERROR` summary says what was wrong and what to do about it:

```
REJECTED Cost {6}{R} not payable: 5 mana available. Resubmit with override to cast anyway.
T6 main1 · Hand 4 · Lands 6 (5 untapped) · Pool {} · Life 40 · Dmg 22/120 · Cmdr 7/0/0 · Tax 2 · #41
```

An error about a card in another seat's hand or library says no more than `game` allows. An instance id is answered with `ERROR c212 is in a hidden zone of S2.`, naming neither the card nor the zone; a name that matches nothing the calling seat may see gets the same not-found text whether or not another seat holds such a card.

Responses to routine plays do not list the battlefield or the hand; `get_state` does that. In a contested game its listing puts a permanent on the battlefield of the seat that controls it, and marks one its controller does not own with its owner: `Llanowar Elves (owner S2)`. It ends, before the payments of `detail: "full"`, with the pending choices addressed to the calling seat, when there are any, one line each in the order they will be answered:

```
Your pending choices (2):
  x7 (search): revealed Forest (c41), Command Tower (c12)
  x8 (ask) from S2: Sacrifice a creature.
```

A `blocks` choice reads `x9 (blocks): attacked by Grizzly Bears (c61), Llanowar Elves (c62)`, and a `resolve` choice `x10 (resolve): s2 Rancor holds delta {"move": ...} and goes to battlefield`, followed by the error that kept it from resolving as held, if any. A goldfish game's listing has no such lines.

### In MCP terms

A response is a single text content item. `ERROR` responses set the MCP result's error flag; `OK`, `REJECTED` and `CHOICE` do not, because a rejection is an ordinary, expected outcome the agent acts on. Arguments that fail the tool's schema are answered in the same text format as an `ERROR`, not as a protocol-level fault, so the agent always reads one format. Such a response sets the error flag, carries the status line when the call named an existing game, and is saved as a call record like any other call. To make this possible the tools are served by the SDK's low-level server, which validates nothing: the schemas the tools declare describe each parameter's JSON type and which are required, to guide the agent, and the adapter shapes the arguments itself. Every object or list parameter is also accepted as a JSON string. A parameter name the tool does not have is a malformed argument. A call naming a tool that does not exist is answered as a protocol error, since there is no tool to record it under.

## Player Brief

A Claude Code subagent definition at `.claude/agents/goldfish-player.md`, one brief for every seat of every game. It restricts the subagent to the service's tools and tells it how to conduct a game for a deck-testing workflow:

- play each game as a strong player would, aiming to win as fast as the deck can;
- make every decision itself, and give a `reason` on plays where the choice was not obvious;
- use `expect` on plays where it is tracking a number closely;
- pass `after` on every changing call;
- resolve reminders with `effect` or consciously pass them;
- end the game with `end_game` and a verdict naming what the deck did well and badly;
- return the game id, the seed and the verdict as its final message.

It is given a deck id (or a deck list to load), and optionally a seed and turn limit. Its section on contested games tells it that it may instead be given a seat id and told which seat it plays, and then to:

- play its seat to win, unless its instructions give it another goal;
- call `wait` whenever its seat is not the seat to act, and act on what `wait` returns;
- read the digest at the top of each response to follow what other seats did;
- respond with `play` or `effect` when asked and it has something worth doing, and `pass` otherwise;
- answer pending choices addressed to it, including blocks and decisions other seats' effects ask of it;
- when attacking, state what happens to the creatures with `effect` and `immediate: true` after blocks, leaving out the damage to seats, which the service deals; give `damage` for a blocked attacker only for what gets past its blockers;
- when an `attack` response says the attack was not declared, call `wait` and send the same `attack` again;
- as the tested seat, end the game with `end_game` and a verdict that names what the opposition did to the deck; as an opposing seat, concede with `end_game` when it is beaten, and otherwise play until the game ends;
- return its seat number, the id it was given (the game id for the tested seat, its own seat id for an opposing seat) and its verdict as its final message; a subagent given a seat rather than a deck is never shown the seed, so it returns none.

## Rendering

Response text is produced in one place, by a renderer that turns an outcome's status, summary, events and game summary into the format above. Each event type, and each kind of error and rule check, has one rendering. No other code in the service builds response text, so a change of wording is a change to the renderer alone. The renderer implements the application's `Renderer` port, so a use case can store the exact response in the call record before it commits (see `application`).

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
| MCP server class | The SDK's low-level server with schemas the adapter declares | The SDK's high-level server built from function signatures | The high-level server rejects calls that fail a signature before the adapter sees them, so they could not be answered as `ERROR` text or recorded. |
| Unknown parameter names | Malformed argument | Ignored | A misspelled `override` or `after` silently ignored would change what the call does without the agent knowing. |
| DNS-rebinding protection | On when bound to a loopback address, off otherwise | Always off; always on | It protects a local service from web pages in the user's browser without blocking deliberate remote binding. |
| The parameter carrying a seat id | `game_id`, holding the calling seat's id | A new `seat_id` parameter; both, exactly one required | Every goldfish call keeps its shape, and the tested seat's id is the game id; a second name for the same argument would give each call two ways to be malformed. |
| Where the digest goes | Before the status word, one line per change | After the event lines; on request only | What happened before the call is context for reading its result; on request only would cost a `get_state` after every `wait`. |
| Contested status line | The calling seat's own figures, then every other seat's life, then who is to act | The goldfish line unchanged; every seat's full figures | An agent needs its own resources and every opponent's life on every call; other seats' hands and lands are in `get_state`. Who is to act tells it whether to `wait`. |
| Player briefs | One brief with a contested section | A separate brief for opposing seats | The tools and rules are the same for every seat; a seat's goal comes from its caller. |
| Whose line a digest event is on | The seat whose call made the change, one line per change | A line per seat the change affected | A change number then appears once, and the line reads as cause and consequences in order. |
| Order of the other seats on the status line | Ascending seat number | Turn order starting after the calling seat | Every seat reads the same seats in the same places, and the labels are seat numbers already. |
| An eliminated seat's `Cmdr` number | Kept | Replaced by `out`; dropped | The `Cmdr` numbers stay aligned with the life groups, which already say `out`. |
| A pending choice on the contested status line | Shown by `Act` and the choice's kind | The goldfish ` · CHOICE pending` suffix | The suffix cannot say which seat the choice waits on; `Act` can, and two signs for one fact invite disagreement. |
| The word for what a seat is asked | The pending choice's own kind, or `respond`, `trigger`, `turn` | `choose` for every pending choice; free text | The kind is the word the `CHOICE` response and `choose` already use, and tells a seat which answer is wanted without a `get_state`. |
| `Ended` and `Out` together | `Ended (<result>) · Out · ...` | `Out` first; `Ended` alone | That the game is over matters more than how the seat left it, and an ended game's line begins the same way for every seat. |
| An opposing seat's aim in the player brief | Play to win, as a real player would | Archenemy: stop the tested deck at all costs | Realism is the goal; a caller who wants a harsher test still briefs an opposing agent as an archenemy. |
| Where a seat finds the pending choices it owes | In its `get_state` listing, with what each asks | Only in the response or digest line that created it; in every `wait` response | A seat that missed that line, or whose agent was restarted, must not be stuck; repeating every choice on every `wait` would lengthen the most frequent response. |
| What a seat-given subagent returns | Seat number, the id it was given, verdict | Game id, seed and verdict as in a goldfish game | It is shown neither the seed nor, as an opposing seat, the game id; its caller holds both. |

## Open Questions & Future Decisions

### Deferred
1. Authentication and per-caller isolation, when the service is offered to others.
2. Refinement of tool names, descriptions and response wording by measured trial with agents.
3. A limit on digest length for a seat that has not called for many changes.

## References

- `docs/high-level-design.md` (tenet *Clear before cheap*; goal 9)
- `GLOSSARY.md`
- Model Context Protocol Python SDK: `https://github.com/modelcontextprotocol/python-sdk`
