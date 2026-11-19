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

A seat's digest baseline (see `application`) is the change number on its most recent call record for a tool other than `get_log`, found from `calls` by game id and seat number; an index on those columns keeps that lookup cheap. The seat number column of `calls` holds what the call record carries (see `records`): it is null for every call of a goldfish game, whose records name no seat even though the game's `seats` row has seat number 1, for a contested game's `new_game`, and for a call whose id names no seat.

A table turn has one snapshot. The domain writes at most one, so a second for the same game and table turn is a defect: the adapter raises rather than replace the first or drop the second, and the call's unit of work is rolled back.

## Stored Documents

Every stored domain value — a game, a loaded deck, a log entry, a turn snapshot, a call record, a cached card — is written as one JSON document by a single codec, driven by the type the value is declared as. The same codec turns values into JSON-ready data and back for the migrations, which work on that data rather than on document text.

The format:

- A dataclass becomes an object whose first key is `__type__`, holding the bare name of the value's own class, which may be a subclass of the declared type. Every field follows in declaration order, including fields equal to their default and fields not set by the constructor; values cached on an instance after construction are not fields and are not written.
- An enum becomes its value, a time its ISO text, and a mana string its text.
- Tuples and lists become arrays. Frozensets and sets become arrays sorted by each item's text as the standard library's `json.dumps` writes it with sorted keys and otherwise its default settings (a space after each separator, non-ASCII characters escaped), so that equal sets are written alike. Dicts with string keys become objects.
- `bool` is never accepted where `int` or `float` is declared. An `int` where `float` is declared is written, and read back, as an int.
- A value of a union type is written as the first member, in declared order, that it is an instance of.
- Where a value is declared only as `object` (a call's arguments as received), it is written so that it describes itself: tuples, enums, times, and dicts that would be mistaken for one of these are wrapped in a tagged object, and a dataclass or enum in it must have a class name no other storable domain class has.
- The text is compact, with no spaces after separators, and non-ASCII characters are written as themselves.

Reading follows the same rules backwards. A tag names the class to build: one of the declared classes by that name, else the one domain class of that name that is a subclass of the declared type. In a union, data that is null reads as None when None is a member; tagged data reads as the dataclass member its tag names; anything else reads as the first member, in declared order, that accepts it. Keys that name no field are ignored, so a document still reads after a field is removed, and a document that lacks a field with a default reads with the default. A field added to a domain dataclass is therefore stored without changing the codec. Renaming a stored class, adding a second storable class of the same name, or reordering a union's members changes the format.

A value that does not match its declared type, data that cannot be read as the type asked for (a missing field with no default, a tag that names no single class, a value of the wrong kind), and a dataclass whose own validation rejects the data read all raise. That is a defect, not a refusal: the call that meets it fails as an internal failure, and a migration that meets it is rolled back and stops start-up (see Schema Changes).

The documents already in databases fix the format. For a given value the codec writes exactly the text and the data it has always written, and it reads every document a database at the current schema version holds, including documents a migration wrote without the codec. Changing the format would be a schema migration (STOR-047 to STOR-050, STOR-062, STOR-063).

Every call about a game reads the game and every seat's loaded deck, and every changing call writes the game back, so the codec's speed is part of every call's latency. The codec therefore works out how to write and read each declared type once per process, the first time it meets that type, and reuses that for every later value of it, rather than inspecting type hints value by value, so that writing or reading a document costs a small multiple of what the standard library's JSON module takes for it (STOR-051, STOR-052). Types that refer to themselves, directly or through a union, are supported. What still depends on each value is decided per value: which member of a union a value is, the class a tag names, and how a value declared as `object` describes itself. Two threads that meet a new type at once may both work it out; the results are equal. The first call that meets a type, or that resolves a tag against the domain's classes, pays for working them out once.

## Loaded Decks in Memory

A loaded deck's document is the largest the service stores, since it holds the card data and readings of every card in the deck, and a call about a contested game reads up to four of them. Once start-up migrations have run, a loaded deck is never changed and never deleted, so a copy read after that stays correct for the life of the process. The SQLite deck repository therefore keeps in memory the loaded decks it has most recently found, keyed by deck id, and answers a request for one of them without reading the database. It keeps at most 64 decks, whatever their size; at about 0.3 MB each that is about 20 MB, enough for every seat of 16 four-seat games at once. A deck just kept, and a request answered from memory, make that deck the most recently asked for, and when memory is full the deck least recently asked for is forgotten. A deck not in memory is read and decoded from the database, and a request that finds no deck always reaches the database: a miss is not remembered, so a deck added later, by this process or another, is found (STOR-053 to STOR-056, STOR-061).

Memory belongs to the repository instance and starts empty (STOR-064); the database is migrated before any repository reads from it, so no deck read before a migration is kept. A newer service that migrates the database while an older one is running would make the older one's documents of every kind stale; running two service versions on one database at once is not supported, and memory adds no new case to that.

A deck enters memory only from a read that can see nothing uncommitted: a read made while no transaction is open on the reading connection. Adding a deck neither consults nor fills memory; it writes the deck and returns what it reads back from the database, as before (STOR-057, STOR-065). So a deck written inside a unit of work that is later rolled back, or read back inside that unit of work, is never kept, and a request for it after the rollback finds no deck, exactly as the database does (STOR-058). A request made inside an open transaction may still be answered from memory, since everything there was committed. Once the database is closed, which is for good, the repository raises as the database does rather than answer from memory (STOR-059).

One copy of a deck in memory is shared by every game and every thread that uses it, which is safe because nothing under a loaded deck can be changed: every dataclass in it is frozen and none of its fields is a list, dict or set (STOR-060). The one thing filled in after construction is the deck's index of its cards by name, computed from those immutable fields; two threads that fill it at once store equal indexes. Two threads that ask for the same deck while it is not in memory may both read it; the copies are equal, and one of them is kept.

## Transactions

A tool call's writes — the game's new state, its log entry, any snapshots, and its call record — are committed in one transaction. If anything fails, none of them is saved, except the call record: a call that ends in an error or refusal still gets its call record, written in its own transaction.

## Concurrency

The database runs in WAL mode so readers do not block writers. A write to one game made while another game's unit of work is open waits for that unit to end, up to a busy timeout of 5 seconds, and is not refused before then. Calls for the same game are applied one at a time: each use case holds the game's lock for the duration of a call, through the `GameLocks` port, which is implemented in-process. In addition, each save checks the game's version counter and increments it; a save against a stale version fails rather than overwriting. Within one process the lock makes that failure unreachable; the counter exists so that correctness does not depend on there being one process. If it does occur, nothing is saved and the agent receives an `ERROR` saying the game changed underneath the call and to send it again.

Read-only calls (`get_state`, `get_log`) take the same per-game lock, so they never see a half-applied change. Their call records are written in their own transaction.

If a call fails for a reason inside the service — the disk, a defect — nothing of the call is saved except its call record, the agent receives an `ERROR` that says the failure was internal and not caused by the call, and the detail is written to the service's own log output.

## Location and Lifetime

The database is a single file whose path comes from configuration (see `tools`). The file and its directory are created on first start. Games, logs, snapshots, calls and loaded decks are kept indefinitely; nothing is deleted automatically.

## Schema Changes

The `schema_version` row records the layout. On start, the adapter applies, in order, any forward migrations needed to reach the current layout. Each migration runs in one transaction together with the update of `schema_version` to the version it reaches, so a migration that fails leaves the database at its previous version. No backup copy of the database is written before a migration, and no migration can be reversed: once migrated, a database can be opened only by a service that knows its version. Faced with a database newer than itself, the service exits at start with a message naming both versions rather than risk damage.

The migrations, by the version they reach:

- **2, seats.** Creates the `seats` table and a row for every existing game's tested seat, adds the seat number column to `calls`, and rewrites each stored game document into the seat-holding shape, so that every goldfish game answers the calls it would have answered before, with the same responses. Its records are another matter: a log export reads entries as they are now shaped, and so carries fields that records have gained since, such as each entry's `cast_triggers`.
- **3, whose turns a step trigger happens on.** Rewrites every step trigger reading held in a stored loaded deck or game document that names a step alone as a trigger in that step on its controller's turn, the only turns such a reading was ever reminded on; a reading that already says whose turns it happens on is left as it is. Because a loaded deck never changes once written, a deck stored before this migration keeps these readings when its list is loaded again with the same card data, and so do the games played on it: a trigger in it on each turn, or on opponents' turns, is reminded on its controller's turns only. A deck loaded afresh, under a new id, is read as usual.

- **4, evasion and reach readings.** Adds to every card reading held in a stored loaded deck or game document the flying, horsemanship, reach and "can't be blocked" readings (see `card-reading`), made from the card data stored with that reading, card definition applied, exactly as `load_deck` would make them now. Every other part of each reading is left as it is. Without it, a deck loaded before these readings existed would never have them: a loaded deck never changes once written, and loading its list again returns the stored deck under the same id, so no block against its creatures would ever be checked for evasion. A declared attack stored before this version holds no evasion statements and no trample damage, and is read as having none; it needs no rewriting.
- **5, station readings.** Adds to every face reading held in a stored loaded deck or game document the station reading (see `card-reading`), made from the card data stored with that reading, card definition applied, exactly as `load_deck` would make it now. On a face with a line beginning with a station symbol it also replaces the keyword readings (haste, vigilance, flash, flying, horsemanship, reach and "can't be blocked") with those made now, since keywords after a station symbol were misread before this version. A game card instance that holds no reading of its own is left as it is, and a face reading stored without a station reading is read as never becoming a creature. Every other part of each reading is left as it is, and so is every pending choice, window, declared attack and record: the new readings apply from the next rule check. Mana abilities after a station symbol need no rewriting, since no reader before this version read them. Without it, a Spacecraft in a deck loaded before this version would never be judged a creature, for the reason given for version 4.

No migration changes a game's version counter: a migrated game is the same game.

Every seat's state at the end of a contested game (see `records`) needs no migration. It is part of a log entry's `outcome`, which is stored as JSON as built: an `end_game` entry stored before it holds none and is not rewritten, and the ended game's stored document still holds the state it ended in.

Cast triggers (see `stack` and `records`) need no migration. A stack item stored before them holds no `cast_with` and is read as no cast trigger, and a log entry stored before them holds no `cast_triggers` and is read as stating none; neither is rewritten, and the schema version does not change.

The change number since which a contested game's seats to act have been asked (see `game`) needs no migration either. A game document stored before it holds none and is read as holding none, which shows no time beside the seat to act until the game's next change sets one.

The time a game's change was made (see `application`) is read from `calls`: the earliest-stored row with that game id and that change number, which is the call record of the call that made the change. The existing index on the game id and seat number columns of `calls` narrows the search to that game's rows, so the lookup needs no new index and no schema change.

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
| How a migration is applied | In one transaction with the version it reaches; no backup copy; not reversible | **Open, for the owner to choose:** write a backup copy of the database file before migrating | A failed migration already leaves the database as it was. A backup copy would also let an older service be run again after a migration that succeeded, at the cost of a second file per migration to keep or delete. |
| Stored step trigger readings without whose turns | Rewritten as triggers on their controller's turn | Read the decks' card text again during the migration | A migration works on stored JSON alone so that it does not change as the reader does, and controller's turns are where every such reading was reminded. |
| A second snapshot for a table turn | Raise | Replace the first; keep the first and ignore the second | It can only come from a defect, and either quiet behavior would hide it and leave a record nobody chose. |
| How the codec follows declared types | Work out each type's writing and reading once, then reuse it | Inspect type hints for every value; a serialization library such as msgspec, cattrs or pydantic; pickle | Inspecting hints value by value made writing or reading a document cost more than ten times the JSON parsing itself, on every call. A library would add a dependency and could not write the stored format, with its tags and self-describing free-form values, without hooks for nearly every type, so in practice it would mean a migration of every document. Pickle is unreadable outside Python, ties stored data to the classes' layout, and runs code on load. |
| Reading loaded decks | Keep the 64 most recently read in memory | Read and decode them on every call; keep every deck read, without a limit; keep them in the application layer; store decks in a slimmer document | Decoding every seat's deck was most of the time a call about a contested game took. A deck never changes, so a copy cannot go stale. A limit keeps memory bounded when many decks are played (tenet *Build for local, don't block hosted*). The application layer would then hold state between calls that only one adapter needs. A slimmer document would need a migration and still be decoded on every call. |
| Reading games | Read and decode the game on every call | Keep each game in memory, keyed by game id and version | A game changes on most calls and is mutable, so each call would need its own deep copy of a kept game, which costs about what decoding it does. |
| Which reads put a deck in memory | Only a read made while no transaction is open on the reading connection | Every read and every write | A write, or a read inside a unit of work, can see a deck that a rollback then removes; keeping it would let a game be started on a deck the database does not hold. |

## Open Questions & Future Decisions

### Deferred
1. A retention or export policy, when the database is shared by many users.
2. Re-reading the step triggers of loaded decks stored before version 3, which keep controller's-turn readings because a loaded deck never changes once written.

### Open
1. Whether a migration writes a backup copy of the database first (see Decisions & Alternatives).

## References

- `docs/high-level-design.md` (tenet *Build for local, don't block hosted*)
- `docs/intent/records/records-design.md`
