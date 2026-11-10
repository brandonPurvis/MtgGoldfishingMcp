# Storage — Specs

Design: `storage-design.md`. Prefix: `STOR`.

## Adapter

- [x] **STOR-001**: The SQLite adapter shall implement the `GameRepository`, `DeckRepository`, `RecordStore` and `UnitOfWork` ports and the card cache, and shall pass each port's contract tests.
- [x] **STOR-002**: The SQLite adapter shall open its database in WAL mode.
- [x] **STOR-003**: When the service starts and the configured database file or its directory does not exist, the SQLite adapter shall create them.
- [x] **STOR-004**: The SQLite adapter shall store the current state of a game, goldfish or contested, as one JSON document and treat that document as authoritative over any other column of the game's row.
- [x] **STOR-005**: The SQLite adapter shall return from `GameRepository` a game, goldfish or contested, equal to the one last saved, including after the service has been restarted.
- [ ] **STOR-015**: When a contested game is saved and loaded again, the SQLite adapter shall return every seat's state, every card instance's owner and controller, the stack, any open response window and every pending choice equal to what was saved.

## Seats

- [ ] **STOR-016**: When a new game, goldfish or contested, is first saved, the SQLite adapter shall write one `seats` row per seat of the game, holding the seat id, game id, seat number, deck id and whether it is the tested seat, in the same transaction as the game.
- [ ] **STOR-017**: The `seats` row of a game's tested seat shall have the game id as its seat id, so that a goldfish game has exactly one `seats` row, keyed by its game id.
- [ ] **STOR-018**: When asked through `GameRepository` for the game and seat number a seat id names, the SQLite adapter shall answer from the `seats` table by its key, without reading any game's JSON document to search for the seat.
- [ ] **STOR-019**: If the id given to `GameRepository` names no seat of any stored game, then the SQLite adapter shall report that it names none.
- [ ] **STOR-020**: The SQLite adapter shall not change or delete a `seats` row after writing it.

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
- [ ] **STOR-021**: The SQLite adapter shall store with each call record the seat number the call record carries, or null when it carries none: every call record of a goldfish game (whose records name no seat, although its `seats` row has seat number 1), a contested game's `new_game`, and a call whose id names no seat.
- [ ] **STOR-022**: When asked through `RecordStore` for a seat's digest baseline, the SQLite adapter shall return the change number of the latest-stored call record with that game id and seat number whose tool is not `get_log`, or report that the seat has none.
- [ ] **STOR-023**: The SQLite adapter shall keep an index on the game id and seat number columns of `calls`.
- [ ] **STOR-028**: The SQLite adapter shall key each stored turn snapshot by game id and table turn number, which in a goldfish game is the turn number, so that the snapshots of different seats' turns in a contested game never replace one another.
- [ ] **STOR-029**: If the SQLite adapter is asked to add a snapshot whose game id and table turn number already have a stored snapshot, then it shall raise an exception and write nothing, neither replacing the stored snapshot nor ignoring the new one silently.

## Schema

- [x] **STOR-013**: When the service starts against a database with an older schema version, the SQLite adapter shall apply forward migrations to reach the current schema version before serving.
- [x] **STOR-014**: If the service starts against a database with a newer schema version than it supports, then the service shall exit with a message naming both versions and change nothing.
- [ ] **STOR-024**: When the service starts against a database whose schema predates seats, the migration shall create the `seats` table with one row for the tested seat of every existing game, keyed by that game's id.
- [ ] **STOR-025**: When the service starts against a database whose schema predates seats, the migration shall add the nullable seat number column to `calls`, leaving it null on every existing call record.
- [ ] **STOR-026**: When the service starts against a database whose schema predates seats, the migration shall rewrite each stored game document into the seat-holding shape (one tested seat holding the zones, life, mana pool and other per-seat state, with pooled damage and commander damage kept as the goldfish game's imaginary-opponent tallies).
- [ ] **STOR-027**: When a goldfish game stored before the seats migration is loaded after it, the game shall accept the same calls with the same results, status line and change number as before the migration.
