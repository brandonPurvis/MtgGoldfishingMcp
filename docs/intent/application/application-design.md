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
    game/         # Game aggregate, seats, card instances, zones, shuffling, turn order,
                  # the seat to act, what a seat may see, elimination, notices, change number
    turn.py       # steps, advancing, turn rotation and rounds
    play/         # deltas, choices, pending choices, checks, expect
    stack/        # stack items, response windows, passing, resolution
    payment/      # auto payment system, agent-directed payment
    combat/       # attack and combat damage
    records/      # log entry, snapshot and call record shapes; building them from a call's events
  application/
    ports.py      # the ports: abstract base classes
    outcome.py    # Outcome: status, summary, events, digest and game summary
    use_cases/    # one module per tool
  adapters/
    mcp/          # the tools: schemas, descriptions, rendering, HTTP app
    sqlite/       # persistence ports on SQLite
    scryfall/     # card catalog on the Scryfall API with a cache
    memory/       # in-memory implementations of every port
    system/       # the real id source, clock, game locks and game change announcements
  bootstrap.py    # composition root: builds the service from the real adapters; entry point
tests/
  domain/         # pytest, no adapters
  application/    # pytest, in-memory adapters
  contract/       # pytest, one suite per port, run against each adapter
  architecture/   # the dependency rule
  adapters/       # pytest, adapter-specific behaviour (SQLite, Scryfall, rendering, MCP)
  e2e/            # the real process over HTTP; marked e2e, run by CI but not before commits
  support/        # builders shared by tests, and the test composition root
features/         # behave feature files and steps, in-process
  http/           # contested scenarios run against the real process, one client per seat
```

## Domain Model Shape

The component designs describe behavior; this is how that behavior is held in code.

- **Aggregates.** `Game` is the one aggregate that changes. Everything inside a game — its seats, card instances, zones, mana pools, stack, window, declared attack, pending choices, notices — is reached and changed only through it. A `Seat` is an entity inside the game, identified by its seat number; it is never saved or loaded on its own. `LoadedDeck` is an aggregate that never changes after creation.
- **Value objects.** Immutable and compared by value: `ManaString`, `Cost`, `Mana`, `Step`, `Zone`, `Destination`, `Delta`, `Choices`, `TokenSpec`, `Payment`, `Card`, `Face`, every reading type, `GameId`, `SeatId`, `SeatNumber`, `DeckId`, `Seed`, `StackItem`. A value object checks its own validity on construction, so an invalid mana string cannot exist past the edge of the domain.
- **Domain services.** Stateless operations that do not belong to one object: the card reader, the auto payment system, the deck checker, the shuffler, and the public filter that turns an event into its public form (see `game`).
- **Operations are made by a seat.** Every operation on a `Game` that a tool causes is given the acting seat's number, and rules are written against the acting seat.
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

Two consumers read a call's events. The MCP adapter renders the outcome as response text (see `tools`). The `records` domain builds the log entry from the events and the game before and after the call, including the public form of each event. Neither is derived from the other.

In a contested game an outcome also carries a **digest** and is rendered for the calling seat: its game summary is that seat's view (see `game`).

```
Outcome {
  ...
  seat: int | None             // the calling seat, in a contested game
  digest: [{ seat, change, events: [Event] }]   // other seats' public events since this seat's previous call
}
```

The digest is assembled by the use case from records: the log entries with a change number greater than the one on the calling seat's previous call record, made by other seats, each with its public events. Events of the calling seat's own call are its outcome, not its digest. The public events themselves were chosen by the domain when the entries were written; the application only selects entries.

## Ports

Interfaces owned by the application and implemented by adapters. Each port is an abstract base class in `application/ports.py`; each implementation is a concrete class that inherits from the port it implements.

| Port | Purpose | Operations |
|---|---|---|
| `GameRepository` | Load and save games | get a game by id; find the game and seat number a seat id names; save a game, failing if the stored game has changed since it was loaded |
| `DeckRepository` | Keep loaded decks | get a loaded deck by id; add a loaded deck, leaving an existing one with the same id in place |
| `RecordStore` | Keep and return records | append a log entry; add a snapshot; add a call record; read a game's entries, snapshots and call records, optionally after a change number; give the change number on a seat's most recent call record |
| `CardCatalog` | Supply card data by exact name | look up a set of names, returning for each: a card, not found, or unavailable; optionally refreshing |
| `UnitOfWork` | Make one call's saves atomic | begin; commit; roll back — spanning `GameRepository`, `DeckRepository` and `RecordStore` |
| `GameLocks` | Apply one game's calls one at a time | hold a game's lock for the length of a call |
| `GameChanges` | Wake seats waiting on a game | announce that a game has changed; wait until a game changes after a given change number, or a timeout passes |
| `IdSource` | Supply what must be random | a new game id; a new seed |
| `Clock` | Supply the time | now |
| `Renderer` | Turn an outcome into response text | render an outcome as the response, and as the text to keep in its call record |

Ports speak in domain types: a `GameRepository` returns a `Game`, not a row or a dictionary. How a game is laid out on disk is the adapter's business.

`IdSource` and `Clock` are ports because random ids and the current time are the two things that would otherwise make the domain and application unrepeatable in tests. `IdSource` also supplies seat ids.

`GameChanges` is a port because waiting is the one thing in the service that depends on another call arriving. In one process it is a condition variable per game; a service of several processes would back it with the database or a message broker without any use case changing.

## Dependency Injection

The application never constructs or looks up an implementation of a port. `Service` receives every port as a keyword argument of its constructor and hands each use case the ports it needs. Implementations are chosen in exactly two places, each a composition root written by hand:

- `bootstrap.py`, which builds the running service from the SQLite stores, the Scryfall catalog, the system id source, clock, game locks and game changes, and the text renderer;
- the test composition root in `tests/support`, which builds the same service from the in-memory adapters, the recorded card catalog and a set clock and id source.

Because every implementation inherits from its port, a class that does not implement every operation of its port fails when it is built, and a reader sees on the class line which port it serves.

`Renderer` is a port because a call record holds the response exactly as returned and is saved in the same unit of work as the change it records, so the use case needs the text before it commits. The text itself is written by the MCP adapter, which implements the port; the application only carries it. The text kept in the call record equals the response for every tool except a successful `get_log`, whose record keeps a one-line note of the export's size.

## What a Use Case Does

For a tool that changes a game:

1. Find the game and seat number the id names. If it names none, return an error outcome.
2. Hold the game's lock.
3. Load the game.
4. Ask the game whether the call is a resend of the calling seat's most recent change (see `game`). If it is, answer it as already applied, whatever the game's state.
5. Ask the game whether the calling seat may make this call now (see `game`: the seat to act). If not, return an error outcome.
6. Ask the game whether the call follows its change number: apply, or refuse as stale.
7. Resolve any card data the call needs through `CardCatalog` (only `play` from outside the game needs this). A card definition given with the call does not skip the lookup: its fields replace the fetched ones it names.
8. Call the domain operation, as the calling seat.
9. If applied: build the log entry and any snapshots, and save game, entry and snapshots in one unit of work.
10. In a contested game: assemble the calling seat's digest.
11. Whatever happened: render the outcome through `Renderer` and add the call record with that text, in the unit of work of step 9 or in its own if step 9 saved nothing.
12. If applied: announce through `GameChanges` that the game changed, after the unit of work has committed.
13. Return the outcome and its rendered text.

Read-only use cases (`get_state`, `get_log`) do steps 1–3, 5, 10, 11 and 13. `load_deck` involves no game: it looks up cards, asks the domain to build and check the deck, and adds it to the `DeckRepository`. `new_game` asks `IdSource` for the game id and one seat id for each opposing seat.

### `wait`

```
wait(game_id, timeout?)
```

`wait` is read-only and holds no lock while it waits, so the seats it waits on can act.

1. Find the game and seat the id names; if none, return an error outcome.
2. Under the game's lock, load the game. If the calling seat is a seat to act, or is eliminated, or the game has ended, go to step 4.
3. Release the lock and wait through `GameChanges` for a change after the loaded change number, up to what remains of the timeout. On a change, go back to step 2. On timeout, go to step 4.
4. Under the game's lock: assemble the digest, render an outcome saying what the calling seat is asked to do — or, on timeout, which seat the game is waiting on and for what — and add the call record. Return.

`timeout` is in seconds, default 30, at most 60; a larger value is an error. In a goldfish game the only seat is always the seat to act, so `wait` returns at once.

A call whose arguments the MCP adapter cannot shape at all (a missing parameter, a number where a list belongs) is still handed to the application, which answers it with an `ERROR` outcome — carrying the game summary when the call names an existing game — and adds its call record.

If anything fails unexpectedly, the unit of work is rolled back, a call record is still added, and the outcome is an error that says the failure was inside the service. If even the call record cannot be added, that error is still returned with its rendered text.

## In-Memory Adapters

`adapters/memory` holds a working implementation of every port that keeps its data in ordinary Python objects: repositories backed by dictionaries, a card catalog loaded from a recorded card data file, an id source that hands out a fixed sequence, a clock that is set by the test. They are real implementations, not mocks: they pass the same contract tests as the SQLite and Scryfall adapters. Game locks and game change announcements each have one implementation, in-process in `adapters/system`, which tests and the running service share.

## Testing

| Level | What it proves | How |
|---|---|---|
| Domain | A rule of play behaves as designed | Call the domain directly. Build game states with builders (`a_game().with_battlefield("Forest", "Forest").with_hand("Cultivate")`). No adapters. |
| Application | A use case gathers, decides and saves correctly | Call the use case with in-memory adapters; assert on the outcome and on what the repositories hold. |
| Contract | An adapter keeps its port's promises | One test suite per port, run once per adapter implementing it. |
| Feature | A scenario of play works end to end as an agent sees it | behave, driving the MCP adapter's tool functions in-process over in-memory adapters; assertions read the response text and the game. Contested scenarios drive each seat by its own seat id. |
| End to end | The wiring is right | Start the real process, play a short goldfish game over HTTP against SQLite. |
| Contested end to end | Seats played by separate clients work over the network | behave scenarios in `features/http` start the real process with SQLite and drive each seat through its own MCP client over HTTP, so `wait` and seats acting at once are exercised for real. |
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
| How ports are declared | Abstract base classes that implementations inherit from | Structural protocols | The ports a class implements are stated on the class, and a missing operation fails when the object is built, not only under the type checker. |
| How implementations are plugged in | Constructor injection from a hand-written composition root | A dependency-injection container library | The whole object graph stays in plain code a reader can follow, with no extra dependency and no wiring resolved at runtime. |
| How `wait` learns of changes | A `GameChanges` port, announced after commit | Polling the repository; a stream per seat | Polling wastes calls and adds latency; announcing after commit means a woken seat always reads the change. |
| Holding the lock while waiting | Never | Hold it and release on change | A waiting seat holding the game's lock would stop the seat it waits on from acting. |
| Where the digest is assembled | The use case, from log entries after the seat's previous call record | Kept on the game per seat | The records already hold every change in order; keeping a digest on the game would grow its state and change it on read-only calls. |
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
2. `GameChanges` across several service processes sharing one database.

## References

- `docs/high-level-design.md` (tenet *The domain stays pure*; goal 10)
- `GLOSSARY.md`
- `docs/intent/tools/tools-design.md`, `docs/intent/storage/storage-design.md`, `docs/intent/card-data/card-data-design.md` (the adapters)
