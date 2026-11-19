# Storage — Specs

Design: `storage-design.md`. Prefix: `STOR`.

## Adapter

- [x] **STOR-001**: The SQLite adapter shall implement the `GameRepository`, `DeckRepository`, `RecordStore` and `UnitOfWork` ports and the card cache, and shall pass each port's contract tests.
- [x] **STOR-002**: The SQLite adapter shall open its database in WAL mode.
- [x] **STOR-003**: When the service starts and the configured database file or its directory does not exist, the SQLite adapter shall create them.
- [x] **STOR-004**: The SQLite adapter shall store the current state of a game, goldfish or contested, as one JSON document and treat that document as authoritative over any other column of the game's row.
- [x] **STOR-005**: The SQLite adapter shall return from `GameRepository` a game, goldfish or contested, equal to the one last saved, including after the service has been restarted.
- [x] **STOR-015**: When a contested game is saved and loaded again, the SQLite adapter shall return every seat's state, every card instance's owner and controller, the stack, any open response window and every pending choice equal to what was saved.

## Seats

- [x] **STOR-016**: When a new game, goldfish or contested, is first saved, the SQLite adapter shall write one `seats` row per seat of the game, holding the seat id, game id, seat number, deck id and whether it is the tested seat, in the same transaction as the game.
- [x] **STOR-017**: The `seats` row of a game's tested seat shall have the game id as its seat id, so that a goldfish game has exactly one `seats` row, keyed by its game id.
- [x] **STOR-018**: When asked through `GameRepository` for the game and seat number a seat id names, the SQLite adapter shall answer from the `seats` table by its key, without reading any game's JSON document to search for the seat.
- [x] **STOR-019**: If the id given to `GameRepository` names no seat of any stored game, then the SQLite adapter shall report that it names none.
- [x] **STOR-020**: The SQLite adapter shall not change or delete a `seats` row after writing it.

## Transactions

- [x] **STOR-006**: When a unit of work is committed, the SQLite adapter shall save the game state, log entry, snapshots and call record written within it together, or none of them.
- [x] **STOR-007**: When a unit of work is rolled back, the SQLite adapter shall leave the database as it was before the unit of work began.

## Concurrency

- [x] **STOR-008**: When saving a game, the SQLite adapter shall compare the stored game's version counter with the version the game was loaded at, save and increment the counter when they match, and fail the save without writing when they do not.
- [x] **STOR-009**: While a game is being written, the SQLite adapter shall let other games be read without waiting, and shall apply a write to another game once the open write's transaction ends, waiting up to the busy timeout, and shall not refuse it before then.

## Loaded decks and records

- [x] **STOR-010**: When asked to add a loaded deck whose id already exists, the SQLite adapter shall leave the existing loaded deck in place.
- [x] **STOR-011**: The SQLite adapter shall keep games, log entries, snapshots, call records and loaded decks indefinitely and delete none of them automatically.
- [x] **STOR-012**: When asked for a game's records after a given change number, the SQLite adapter shall return only log entries with a greater sequence number, call records with a greater change number, and snapshots written by those entries.
- [x] **STOR-021**: The SQLite adapter shall store with each call record the seat number the call record carries, or null when it carries none: every call record of a goldfish game (whose records name no seat, although its `seats` row has seat number 1), a contested game's `new_game`, and a call whose id names no seat.
- [x] **STOR-022**: When asked through `RecordStore` for a seat's digest baseline, the SQLite adapter shall return the change number of the latest-stored call record with that game id and seat number whose tool is not `get_log`, or report that the seat has none.
- [x] **STOR-023**: The SQLite adapter shall keep an index on the game id and seat number columns of `calls`.
- [x] **STOR-028**: The SQLite adapter shall key each stored turn snapshot by game id and table turn number, which in a goldfish game is the turn number, so that the snapshots of different seats' turns in a contested game never replace one another.
- [x] **STOR-029**: If the SQLite adapter is asked to add a snapshot whose game id and table turn number already have a stored snapshot, then it shall raise an exception and write nothing, neither replacing the stored snapshot nor ignoring the new one silently.

## Stored documents

- [x] **STOR-047**: The SQLite adapter shall write each stored game, loaded deck, log entry, turn snapshot, call record and cached card as exactly the JSON text, character for character, that the storage design's stored document format defines for that value: the same keys in the same order, the same separators and the same escaping.
- [x] **STOR-048**: When a migration turns a value into JSON-ready data, the SQLite adapter shall produce exactly the data whose JSON text STOR-047 defines for that value.
- [x] **STOR-062**: When a migration turns JSON-ready data into a value, the SQLite adapter shall produce the value that a stored document holding that data reads as.
- [x] **STOR-049**: The SQLite adapter shall read every game, loaded deck, log entry, turn snapshot, call record and cached card document that a database at the current schema version holds as the value the stored document format says it stands for, including a document a migration wrote without the codec that lacks a field with a default (read as the default), holds keys that name no field (ignored), holds its keys in another order, or holds an int where a float is declared (read as that int).
- [x] **STOR-050**: If a value to be stored, or any value inside it at any depth, does not match the type declared for it, then the SQLite adapter shall raise a codec error.
- [x] **STOR-063**: If JSON-ready data being read lacks a field that has no default, holds a tag that names no single storable class, holds a value of a kind its declared type does not accept, or is rejected with a `TypeError` or `ValueError` by a dataclass's own validation, then the SQLite adapter shall raise a codec error.
- [x] **STOR-051**: The SQLite adapter shall turn the stored text of the reference loaded deck (100 cards, with recorded card data and every card's readings) and of the reference contested game (four seats partway through a game, with cards on the battlefield, in hands and on the stack) into the value it stands for, decoding afresh on every run, with a median time over repeated runs no more than five times the median time `json.loads` takes to parse the same text, excluding the database read.
- [x] **STOR-052**: The SQLite adapter shall turn the reference loaded deck and the reference contested game into their stored text, encoding afresh on every run, with a median time over repeated runs no more than four times the median time `json.dumps` takes to write each value's JSON-ready data with the format's separators and escaping, excluding the database write.

## Loaded decks in memory

- [x] **STOR-064**: Each SQLite deck repository shall keep its own loaded decks in memory, starting with none, and share them with no other repository.
- [x] **STOR-053**: When the SQLite deck repository finds a loaded deck by a read made while no transaction is open on the reading connection, it shall keep that deck in memory, keyed by its deck id, as the deck most recently asked for.
- [x] **STOR-054**: While its database is open, when asked for a loaded deck it keeps in memory, the SQLite deck repository shall return the kept deck without reading the database, whether or not a transaction is open on the reading connection.
- [x] **STOR-061**: When the SQLite deck repository returns a loaded deck it keeps in memory, it shall make that deck the most recently asked for.
- [x] **STOR-055**: When keeping one more loaded deck in memory would make the SQLite deck repository keep more than 64, it shall first forget the deck it keeps that was least recently asked for.
- [x] **STOR-056**: When asked for a deck id that names no loaded deck it keeps in memory, the SQLite deck repository shall read the database, and shall not remember a deck id that named no stored loaded deck.
- [x] **STOR-057**: When adding a loaded deck, the SQLite deck repository shall return the deck it reads back from the database after writing, not a deck it keeps in memory.
- [x] **STOR-065**: When adding a loaded deck, the SQLite deck repository shall not keep the added or read-back deck in memory.
- [x] **STOR-058**: When a unit of work in which a loaded deck was added, and read back, is rolled back, the SQLite deck repository shall return no deck when next asked for that deck's id.
- [x] **STOR-059**: If its database has been closed, then the SQLite deck repository shall raise the error the database raises when asked for any loaded deck, including one it keeps in memory.
- [x] **STOR-060**: Every dataclass that a loaded deck can hold at any depth — reached through any field type, union member or tuple item, and including every subclass of a dataclass so reached — shall be frozen, and none of its fields shall be declared with a type that admits a list, a dict, a set, or a value of any type (`object` or `Any`).

## Live games in memory

- [x] **STOR-066**: Each SQLite game repository shall keep its own games in memory, starting with none, and share them with no other repository.
- [x] **STOR-067**: When a transaction in which the SQLite game repository added or saved a game commits, the repository shall keep the game object given to that transaction's last successful `add` or `save` of that game, at the version that write wrote, as the game most recently asked for.
- [x] **STOR-069**: When a save fails because the game's stored version counter differs from the version given, the SQLite game repository shall keep nothing from that save.
- [x] **STOR-070**: When a transaction in which the SQLite game repository added or saved a game ends in any way other than a successful commit — rolled back, a commit that fails, or ended by SQLite after an error — the repository shall keep nothing from that transaction's writes and shall leave the game object and version it kept for each such game id, if any, as they were.
- [x] **STOR-071**: When a transaction begins on a connection, the SQLite database shall discard any work that an earlier transaction on that connection left for its commit and that has not run.
- [x] **STOR-072**: When a transaction in which the SQLite game repository added or saved a game commits, the repository shall keep the written game after SQLite reports that the commit succeeded and before the commit returns to its caller.
- [x] **STOR-073**: When asked for a game it keeps, whether or not a transaction is open on the reading connection, the SQLite game repository shall read that game's stored version counter and, when it equals the version kept, return the kept game object itself at that version without reading the game's stored document.
- [x] **STOR-074**: When asked for a game it does not keep, or one whose stored version counter differs from the version kept, the SQLite game repository shall read the game's stored document and version counter in one statement and return the game that document stands for at that version.
- [x] **STOR-075**: When the SQLite game repository reads a game's stored document while no transaction is open on the reading connection, it shall keep the game read, at the version read, as the game most recently asked for, unless it keeps that game at the same or a later version.
- [x] **STOR-076**: When the SQLite game repository reads a game's stored document while a transaction is open on the reading connection, it shall not keep the game read.
- [x] **STOR-077**: When the SQLite game repository returns a game it keeps, it shall make that game the most recently asked for.
- [x] **STOR-078**: When keeping a game id it does not already keep would make the SQLite game repository keep more than 64 games, it shall first forget the game it keeps that was least recently asked for.
- [x] **STOR-079**: If asked for a game id it keeps whose stored row no longer exists, then the SQLite game repository shall report that it has no such game.
- [x] **STOR-081**: If asked for a game id it keeps whose stored row no longer exists, then the SQLite game repository shall forget that game.
- [x] **STOR-080**: If its database has been closed, then the SQLite game repository shall raise the error the database raises when asked for any game, including one it keeps.
- [x] **STOR-082**: When the SQLite game repository adds or saves a game while no unit of work is open on the writing connection, it shall treat that write as a transaction of its own, which commits when the write ends.
- [x] **STOR-083**: The SQLite game repository shall not replace a game it keeps with an earlier version of that game, whether the earlier version comes from a read or from a commit.
- [x] **STOR-084**: The SQLite game repository shall keep, forget and look up a kept game each as one step that no other thread's keeping, forgetting or looking up interleaves with.

## Schema

- [x] **STOR-013**: When the service starts against a database with an older schema version, the SQLite adapter shall apply forward migrations to reach the current schema version before serving.
- [x] **STOR-014**: If the service starts against a database with a newer schema version than it supports, then the service shall exit with a message naming both versions and change nothing.
- [x] **STOR-024**: When the service starts against a database whose schema predates seats, the migration shall create the `seats` table with one row for the tested seat of every existing game, keyed by that game's id.
- [x] **STOR-025**: When the service starts against a database whose schema predates seats, the migration shall add the nullable seat number column to `calls`, leaving it null on every existing call record.
- [x] **STOR-026**: When the service starts against a database whose schema predates seats, the migration shall rewrite each stored game document into the seat-holding shape (one tested seat holding the zones, life, mana pool and other per-seat state, with pooled damage and commander damage kept as the goldfish game's imaginary-opponent tallies).
- [x] **STOR-027**: When a goldfish game stored before the seats migration is loaded after it, the game shall accept the same calls and answer each with the same status, response text and change number as before the migration, except that a `get_log` export may hold fields that records have gained since that game was stored.
- [x] **STOR-030**: When the service starts against a database whose schema predates step trigger readings that record whose turns they happen on (schema version 2 or older), the migration shall rewrite every step trigger reading in each stored loaded deck that names a step alone as a trigger in that step whose `whose` is `controller`.
- [x] **STOR-031**: When the service starts against a database whose schema predates step trigger readings that record whose turns they happen on, the migration shall rewrite every step trigger reading in each stored game document that names a step alone as a trigger in that step whose `whose` is `controller`.
- [x] **STOR-032**: When the migration to step trigger readings that record whose turns they happen on meets a stored step trigger reading that already records its `whose`, it shall leave that reading unchanged.
- [x] **STOR-033**: When the migration to step trigger readings that record whose turns they happen on rewrites a stored game, it shall leave that game's version counter unchanged.
- [x] **STOR-036**: When the service starts against a database whose schema predates evasion and reach readings (schema version 3 or older), the migration shall add to every card reading held in each stored loaded deck the flying, horsemanship, reach and "can't be blocked" readings made from the card data stored with that deck, card definitions applied, as `load_deck` would make them.
- [x] **STOR-037**: When the service starts against a database whose schema predates evasion and reach readings, the migration shall add to every card reading held in each stored game document (the readings of card instances that carry card data of their own) the flying, horsemanship, reach and "can't be blocked" readings made from the card data the game document holds for that card instance, and shall add no reading to a card instance that holds none.
- [x] **STOR-038**: When the migration to evasion and reach readings rewrites a stored card reading, it shall leave every other part of that reading unchanged, and shall leave every loaded deck's id unchanged.
- [x] **STOR-039**: When the migration to evasion and reach readings rewrites a stored game, it shall leave that game's version counter unchanged.
- [x] **STOR-043**: When the service starts against a database whose schema predates station readings (schema version 4 or older), the migration shall add to every face reading held in each stored loaded deck the station reading made from the card data stored with that deck, card definitions applied, as `load_deck` would make it.
- [x] **STOR-044**: When the service starts against a database whose schema predates station readings, the migration shall add to every face reading held in each stored game document (the readings of card instances that carry card data of their own) the station reading made from the card data the game document holds for that card instance (data that already carries any card definition), and shall leave unchanged a card instance that holds no reading of its own.
- [x] **STOR-045**: When the migration to station readings rewrites a face reading whose face has a line beginning with a station symbol, it shall replace that face's haste, vigilance, flash, flying, horsemanship, reach and "can't be blocked" readings, own and granted, with those made from the same card data.
- [x] **STOR-046**: When the migration to station readings rewrites a stored card reading or game, it shall leave every part of the reading that STOR-043, STOR-044 and STOR-045 do not name unchanged, every loaded deck's id unchanged, every game's version counter unchanged, and every pending choice, window, declared attack and record unchanged.
- [x] **STOR-034**: The SQLite adapter shall apply each migration and record the schema version it reaches in one transaction, so that a migration that fails leaves the database at its previous schema version with nothing of that migration applied.
- [x] **STOR-035**: The SQLite adapter shall write no copy of the database before applying a migration.
- [x] **STOR-041**: When the SQLite adapter reads a game document that holds no change number since which its seats to act have been asked (GAME-180), it shall read the game as holding none, with no migration and no change to the schema version.
- [x] **STOR-042**: When asked through `RecordStore` for the time a game's change was made (APP-093), the SQLite adapter shall return the time held by the earliest-stored row of `calls` (lowest key) with that game id and that change number, or report that there is none, without a schema change.
- [x] **STOR-040**: When the SQLite adapter reads a game document whose stack items hold no `cast_with`, or a log entry that holds no `cast_triggers`, it shall read each such stack item as no cast trigger and each such log entry as stating no cast triggers, with no migration and no change to the schema version.
