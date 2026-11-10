---
parent: high-level-design
prefix: APP
---

# Application

## Context and Design Philosophy

The domain model knows the game and nothing else. The adapters know MCP, SQLite and Scryfall and nothing of the game. This component is the thin ring between them: one **use case** per tool, and the **ports** through which use cases reach the outside world.

A use case does three things and no more: gather what the domain needs, ask the domain to decide, and save what it decided. It contains no rule of play. If a use case needs an `if` about cards, zones or mana, that `if` belongs in the domain.

## The Dependency Rule

```
adapters  →  application  →  domain
```

- `domain` imports only the standard library and itself.
- `application` imports `domain`.
- `adapters` import `application` and `domain`.
- Nothing imports an adapter except the composition root, which builds the running service.

An automated architecture test enforces these four statements.

## Code Layout

```
src/mtg_goldfishing/
  domain/
    events.py     # event types, errors and rule checks: the facts every operation reports
    cards.py      # card model: Card, Face
    reading/      # card reader and reading types
    mana.py       # mana strings, costs, the mana pool
    deck/         # loaded deck, list parsing, deck checks, deck id
    game/         # Game aggregate, card instances, zones, shuffling, notices, change number
    turn.py       # steps and advancing
    play/         # deltas, choices, pending choices, checks, expect
    payment/      # auto payment system, agent-directed payment
    combat/       # attack and combat damage
    records/      # log entry, snapshot and call record shapes; building them from a call's events
  application/
    ports.py      # the port interfaces
    outcome.py    # Outcome: status, summary, events and game summary
    use_cases/    # one module per tool
  adapters/
    mcp/          # the tools: schemas, descriptions, rendering, HTTP app
    sqlite/       # persistence ports on SQLite
    scryfall/     # card catalog on the Scryfall API with a cache
    memory/       # in-memory implementations of every port
    system/       # the real id source, clock and game locks
  bootstrap.py    # composition root: wires adapters to use cases; entry point
tests/
  domain/         # pytest, no adapters
  application/    # pytest, in-memory adapters
  contract/       # pytest, one suite per port, run against each adapter
  architecture/   # the dependency rule
  adapters/       # pytest, adapter-specific behaviour (SQLite, Scryfall, rendering, MCP)
  e2e/            # the real process over HTTP; marked e2e, run by CI but not before commits
  support/        # builders and fakes shared by tests
features/         # behave feature files and steps
```

## Domain Model Shape

The component designs describe behavior; this is how that behavior is held in code.

- **Aggregates.** `Game` is the one aggregate that changes. Everything inside a game — card instances, zones, mana pool, declared attack, pending choice, notices — is reached and changed only through it. `LoadedDeck` is an aggregate that never changes after creation.
- **Value objects.** Immutable and compared by value: `ManaString`, `Cost`, `Mana`, `Step`, `Zone`, `Destination`, `Delta`, `Choices`, `TokenSpec`, `Payment`, `Card`, `Face`, every reading type, `GameId`, `DeckId`, `Seed`. A value object checks its own validity on construction, so an invalid mana string cannot exist past the edge of the domain.
- **Domain services.** Stateless operations that do not belong to one object: the card reader, the auto payment system, the deck checker, the shuffler.
- **Operations return results.** Every operation on a `Game` returns either an **applied** result — the changed game and the events that describe the change — or a **refusal** carrying errors or failed rule checks. Refusals are ordinary return values, not exceptions; exceptions are for defects. The game passed in is never altered by a refused operation.
- **Arguments are read by the domain.** A use case's request carries the call's structured arguments (`delta`, `choices`, `pay`, `expect`, `selections`, `definitions`) as received. The domain turns them into value objects and returns an error for a malformed one, because what counts as malformed — an unknown delta key, a destination that does not exist, a delta holding both `look` and `search` — is part of the model of play.
- **Names come from the glossary.** Types, functions and test names use the terms in `GLOSSARY.md` and the component designs. A concept that needs a new name gets it in the glossary first.

## Outcomes

Every use case returns an `Outcome`.

```
Outcome {
  status: OK | REJECTED | ERROR | CHOICE
  summary: Event               // the headline: what the call did, or why it was refused
  events: [Event]              // everything else worth telling, in the order it happened
  game: GameSummary | None     // the facts behind the status line; None when no game is involved
  payload: object | None       // get_log's records; get_state's listing
}
```

Events are typed values, one type per kind of fact: steps entered, cost paid, card moved, tokens created, cards drawn, cards revealed, combat damage dealt, assumption made, reminder issued, advance stopped, expectation mismatched, notice raised, check failed, error found, call already applied. They are domain types, in `domain/events.py`, because the domain produces them. Errors and failed rule checks are each a kind from a closed list together with the facts that kind needs (the card, the zone, the cost); the renderer holds one wording per kind. Nothing in the domain or application formats text.

Two consumers read a call's events. The MCP adapter renders the outcome as response text (see `tools`). The `records` domain builds the log entry from the events and the game before and after the call. Neither is derived from the other.

## Ports

Interfaces owned by the application and implemented by adapters.

| Port | Purpose | Operations |
|---|---|---|
| `GameRepository` | Load and save games | get a game by id; save a game, failing if the stored game has changed since it was loaded |
| `DeckRepository` | Keep loaded decks | get a loaded deck by id; add a loaded deck, leaving an existing one with the same id in place |
| `RecordStore` | Keep and return records | append a log entry; add a snapshot; add a call record; read a game's entries, snapshots and call records, optionally after a change number |
| `CardCatalog` | Supply card data by exact name | look up a set of names, returning for each: a card, not found, or unavailable; optionally refreshing |
| `UnitOfWork` | Make one call's saves atomic | begin; commit; roll back — spanning `GameRepository`, `DeckRepository` and `RecordStore` |
| `GameLocks` | Apply one game's calls one at a time | hold a game's lock for the length of a call |
| `IdSource` | Supply what must be random | a new game id; a new seed |
| `Clock` | Supply the time | now |
| `Renderer` | Turn an outcome into response text | render an outcome as the response, and as the text to keep in its call record |

Ports speak in domain types: a `GameRepository` returns a `Game`, not a row or a dictionary. How a game is laid out on disk is the adapter's business.

`IdSource` and `Clock` are ports because random ids and the current time are the two things that would otherwise make the domain and application unrepeatable in tests.

`Renderer` is a port because a call record holds the response exactly as returned and is saved in the same unit of work as the change it records, so the use case needs the text before it commits. The text itself is written by the MCP adapter, which implements the port; the application only carries it. The text kept in the call record equals the response for every tool except a successful `get_log`, whose record keeps a one-line note of the export's size.

## What a Use Case Does

For a tool that changes a game:

1. Hold the game's lock.
2. Load the game. If there is none, return an error outcome.
3. Ask the game whether the call is a resend of its most recent change (see `game`). If it is, answer it as already applied, whatever the game's status.
4. Ask the game whether its status accepts the tool. If not, return an error outcome.
5. Ask the game whether the call follows its change number: apply, or refuse as stale.
6. Resolve any card data the call needs through `CardCatalog` (only `play` from outside the game needs this).
7. Call the domain operation.
8. If applied: build the log entry and any snapshot, and save game, entry and snapshot in one unit of work.
9. Whatever happened: render the outcome through `Renderer` and add the call record with that text, in the unit of work of step 8 or in its own if step 8 saved nothing.
10. Return the outcome and its rendered text.

Read-only use cases (`get_state`, `get_log`) do steps 1, 2, 4, 9 and 10. `load_deck` involves no game: it looks up cards, asks the domain to build and check the deck, and adds it to the `DeckRepository`.

A call whose arguments the MCP adapter cannot shape at all (a missing parameter, a number where a list belongs) is still handed to the application, which answers it with an `ERROR` outcome — carrying the game summary when the call names an existing game — and adds its call record.

If anything fails unexpectedly, the unit of work is rolled back, a call record is still added, and the outcome is an error that says the failure was inside the service.

## In-Memory Adapters

`adapters/memory` holds a working implementation of every port that keeps its data in ordinary Python objects: repositories backed by dictionaries, a card catalog loaded from a recorded card data file, an id source that hands out a fixed sequence, a clock that is set by the test. They are real implementations, not mocks: they pass the same contract tests as the SQLite and Scryfall adapters. Game locks have one implementation, the in-process locks in `adapters/system`, which tests and the running service share.

## Testing

| Level | What it proves | How |
|---|---|---|
| Domain | A rule of play behaves as designed | Call the domain directly. Build game states with builders (`a_game().with_battlefield("Forest", "Forest").with_hand("Cultivate")`). No adapters. |
| Application | A use case gathers, decides and saves correctly | Call the use case with in-memory adapters; assert on the outcome and on what the repositories hold. |
| Contract | An adapter keeps its port's promises | One test suite per port, run once per adapter implementing it. |
| Feature | A scenario of play works end to end as an agent sees it | behave, driving the MCP adapter's tool functions in-process over in-memory adapters; assertions read the response text and the game. |
| End to end | The wiring is right | Start the real process, play a short game over HTTP against SQLite. |
| Architecture | The dependency rule holds | Inspect imports. |

Conventions that keep tests readable:

- A test's name states the behavior, not the function (`test_auto_payment_keeps_a_card_in_hand_castable`).
- Arrange with builders, never by hand-assembling state dictionaries.
- Fakes for ports; no mocking library applied to domain objects.
- One reason to fail per test.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Where use cases live | Their own ring between adapters and domain | In the MCP tool handlers; in the domain | Handlers would mix transport with orchestration and make the use cases untestable without MCP; the domain would have to know about saving. |
| Who owns the ports | The application | The adapters; the domain | The application is what needs them; adapters depend on the interface, not the reverse. The domain needs none because it performs no I/O. |
| How refusals travel | Return values | Exceptions | Refusals are the normal, expected result of a rule check; modelling them as values makes "refused, nothing changed" visible in every signature. |
| How a refused operation leaves the game untouched | Operations work on a copy and return it only when applied | Mutate and undo; validate fully before mutating | Guaranteed by construction, with no undo logic to get wrong. |
| Response text and log entry | Both built from one typed outcome | Log the response text; build each separately | Text is for agents and changes with wording; the log is data. Deriving both from typed events keeps them consistent without tying one to the other's format. |
| Test doubles | Working in-memory adapters verified by contract tests | Mocks per test | A fake that passes the port's contract can be trusted everywhere; mocks restate the implementation in each test and hide mismatches with the real adapter. |
| Feature tests' entry point | The MCP adapter's tool functions, in-process | The use cases; a real HTTP client | Scenarios assert on what the agent actually reads, so the rendering is covered; in-process keeps them fast. |
| Randomness and time | Ports | Called directly where needed | They are the only sources of nondeterminism outside the seeded shuffle; behind ports, every test is repeatable. |
| Where event types live | The domain | The application, beside `Outcome` | The domain produces events and cannot import the application. |
| How errors and rule checks are typed | A closed list of kinds, each with its facts | One class per refusal; a message string | A message string would put wording in the domain. A kind with facts keeps the domain text-free and gives the renderer one wording per kind, without a class for each of some fifty refusals. |
| How the call record gets the response text | A `Renderer` port the use case calls before committing | The adapter saves the call record after rendering | The call record must be saved in the same unit of work as the change it records; saving it afterwards could keep a change without its record. |
| Who reads structured arguments | The domain, from the arguments as received | The MCP adapter, into value objects | Malformed arguments are errors the play design defines; reading them in the domain keeps those rules in one place, and the log needs the arguments as received anyway. |

## Open Questions & Future Decisions

### Deferred
1. A second driving adapter (a command-line tool, a plain HTTP API) would call the same use cases.

## References

- `docs/high-level-design.md` (tenet *The domain stays pure*; goal 10)
- `GLOSSARY.md`
- `docs/intent/tools/tools-design.md`, `docs/intent/storage/storage-design.md`, `docs/intent/card-data/card-data-design.md` (the adapters)
