---
parent: high-level-design
prefix: STOR
---

# Storage

## Context and Design Philosophy

This component is the SQLite adapter. It implements the application's persistence ports — `GameRepository`, `DeckRepository`, `RecordStore`, `UnitOfWork` — and the cache used by the card catalog (see `application` and `card-data`). Nothing else in the service imports a database library or writes a file. That makes two things possible: a tool call's changes can be saved together or not at all, and the database can later be replaced by one suited to a hosted service without touching the domain or the use cases.

The adapter is deliberately plain. It turns domain objects into rows and back; it holds no game rules, and no SQL statement decides anything about play. It passes the same port contract tests as the in-memory adapters.

## What Is Stored

| Table | One row per | Key | Notes |
|---|---|---|---|
| `card_cache` | fetched card | lower-cased full name | Card model as JSON, fetch time. |
| `card_names` | face name | lower-cased face name | Points at a `card_cache` row. |
| `decks` | loaded deck | deck id | Commanders, entries, resolved card data, readings, overridden checks; JSON. |
| `games` | game | game id | The tested seat's deck id, seed, status, result, current state as one JSON document, a version counter, created and updated times. |
| `seats` | seat of a game | seat id | Game id, seat number, deck id, whether it is the tested seat. Written once when the game is created; the tested seat's row has the game id as its seat id. |
| `log_entries` | accepted state-changing call | game id + sequence | Entry as JSON. |
| `snapshots` | completed turn | game id + table turn | Snapshot as JSON. In a goldfish game the table turn is the turn. |
| `calls` | tool call | auto-increment | Game id the supplied id names, or the id as supplied when it names none (nullable); the calling seat's number (nullable); tool, arguments, status, response text, whether it carried an override, the game's change number after the call (nullable), time. |
| `schema_version` | — | — | Single row. |

A game's current state — its table, every seat, every card instance with owner and controller, the stack, any window and pending choices — is one JSON document rather than rows per seat or card instance. Every tool call reads the whole game and writes the whole game, nothing queries inside a game's state with SQL, and analysis reads logs and snapshots, not live state. The JSON document is authoritative; the other columns of a `games` row are copies kept for looking games up.

Loaded decks are never updated once written. Writing a deck whose id already exists leaves the existing row in place.

The `seats` table exists so that a call made with any seat id finds its game with one indexed lookup; it is a copy of what the game's document holds, written in the same transaction as the new game. A goldfish game has one row in it.

A seat's digest baseline (see `application`) is the change number on its most recent call record for a tool other than `get_log`, found from `calls` by game id and seat number; an index on those columns keeps that lookup cheap.

## Transactions

A tool call's writes — the game's new state, its log entry, any snapshots, and its call record — are committed in one transaction. If anything fails, none of them is saved, except the call record: a call that ends in an error or refusal still gets its call record, written in its own transaction.

## Concurrency

The database runs in WAL mode so readers do not block writers. A write to one game made while another game's unit of work is open waits for that unit to end, up to a busy timeout of 5 seconds, and is not refused before then. Calls for the same game are applied one at a time: each use case holds the game's lock for the duration of a call, through the `GameLocks` port, which is implemented in-process. In addition, each save checks the game's version counter and increments it; a save against a stale version fails rather than overwriting. Within one process the lock makes that failure unreachable; the counter exists so that correctness does not depend on there being one process. If it does occur, nothing is saved and the agent receives an `ERROR` saying the game changed underneath the call and to send it again.

Read-only calls (`get_state`, `get_log`) take the same per-game lock, so they never see a half-applied change. Their call records are written in their own transaction.

If a call fails for a reason inside the service — the disk, a defect — nothing of the call is saved except its call record, the agent receives an `ERROR` that says the failure was internal and not caused by the call, and the detail is written to the service's own log output.

## Location and Lifetime

The database is a single file whose path comes from configuration (see `tools`). The file and its directory are created on first start. Games, logs, snapshots, calls and loaded decks are kept indefinitely; nothing is deleted automatically.

## Schema Changes

The `schema_version` row records the layout. The migration that adds seats creates the `seats` table and a row for every existing game's tested seat, adds the seat number column to `calls`, and rewrites each stored game document into the seat-holding shape, keeping every goldfish game's behavior as it was. On start, the module applies any forward migrations needed to reach the current layout. Faced with a database newer than itself, the service exits at start with a message naming both versions rather than risk damage.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Database | SQLite in WAL mode | PostgreSQL; JSON files | No separate server to run locally; handles concurrent games; one file to back up. A hosted deployment can swap it behind this module. |
| Shape of game state | One JSON document per game | A row per card instance | Each call loads and saves the whole game; rows would add mapping code and multi-statement saves with no query that benefits. |
| Same-game ordering | Per-game lock plus version check | Lock only; version check only | The lock gives agents ordered results without retries; the version check keeps the guarantee if a second process ever shares the database. |
| Call records on failure | Saved even when the call's other writes are not | Lost with the rollback | Refused and errored calls are exactly what a later study of the tool surface needs. |
| Retention | Keep everything | Expire old games | Local volumes are small; analysis may want any past game. |
| Finding a game from a seat id | A `seats` table written with the game | Scanning game documents; encoding the game id in the seat id | A scan grows with the number of games; an encoded game id would let one seat's id reveal another's. |
| Key of a snapshot | Game id and table turn | Game id and the active seat's own turn number | In a contested game several seats each have a turn 3; the table turn is unique in a game and equals the turn in a goldfish game. |
| Shape of a contested game's state | The same one JSON document, grown to hold seats and the stack | A row per seat | The reasons for one document hold unchanged: every call loads and saves the whole game. |

## Open Questions & Future Decisions

### Deferred
1. A retention or export policy, when the database is shared by many users.

## References

- `docs/high-level-design.md` (tenet *Build for local, don't block hosted*)
- `docs/intent/records/records-design.md`
