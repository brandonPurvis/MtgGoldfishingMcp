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
| `games` | game | game id | Deck id, seed, status, result, current state as one JSON document, a version counter, created and updated times. |
| `log_entries` | accepted state-changing call | game id + sequence | Entry as JSON. |
| `snapshots` | completed turn | game id + turn | Snapshot as JSON. |
| `calls` | tool call | auto-increment | Game id as supplied (nullable), tool, arguments, status, response text, whether it carried an override, the game's change number after the call (nullable), time. |
| `schema_version` | — | — | Single row. |

A game's current state is one JSON document rather than rows per card instance. Every tool call reads the whole game and writes the whole game, nothing queries inside a game's state with SQL, and analysis reads logs and snapshots, not live state. The JSON document is authoritative; the other columns of a `games` row are copies kept for looking games up.

Loaded decks are never updated once written. Writing a deck whose id already exists leaves the existing row in place.

## Transactions

A tool call's writes — the game's new state, its log entry, any snapshots, and its call record — are committed in one transaction. If anything fails, none of them is saved, except the call record: a call that ends in an error or refusal still gets its call record, written in its own transaction.

## Concurrency

The database runs in WAL mode so readers do not block writers. Calls for the same game are applied one at a time: each use case holds the game's lock for the duration of a call, through the `GameLocks` port, which is implemented in-process. In addition, each save checks the game's version counter and increments it; a save against a stale version fails rather than overwriting. Within one process the lock makes that failure unreachable; the counter exists so that correctness does not depend on there being one process. If it does occur, nothing is saved and the agent receives an `ERROR` saying the game changed underneath the call and to send it again.

Read-only calls (`get_state`, `get_log`) take the same per-game lock, so they never see a half-applied change. Their call records are written in their own transaction.

If a call fails for a reason inside the service — the disk, a defect — nothing of the call is saved except its call record, the agent receives an `ERROR` that says the failure was internal and not caused by the call, and the detail is written to the service's own log output.

## Location and Lifetime

The database is a single file whose path comes from configuration (see `tools`). The file and its directory are created on first start. Games, logs, snapshots, calls and loaded decks are kept indefinitely; nothing is deleted automatically.

## Schema Changes

The `schema_version` row records the layout. On start, the module applies any forward migrations needed to reach the current layout. Faced with a database newer than itself, the service exits at start with a message naming both versions rather than risk damage.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Database | SQLite in WAL mode | PostgreSQL; JSON files | No separate server to run locally; handles concurrent games; one file to back up. A hosted deployment can swap it behind this module. |
| Shape of game state | One JSON document per game | A row per card instance | Each call loads and saves the whole game; rows would add mapping code and multi-statement saves with no query that benefits. |
| Same-game ordering | Per-game lock plus version check | Lock only; version check only | The lock gives agents ordered results without retries; the version check keeps the guarantee if a second process ever shares the database. |
| Call records on failure | Saved even when the call's other writes are not | Lost with the rollback | Refused and errored calls are exactly what a later study of the tool surface needs. |
| Retention | Keep everything | Expire old games | Local volumes are small; analysis may want any past game. |

## Open Questions & Future Decisions

### Deferred
1. A retention or export policy, when the database is shared by many users.

## References

- `docs/high-level-design.md` (tenet *Build for local, don't block hosted*)
- `docs/intent/records/records-design.md`
