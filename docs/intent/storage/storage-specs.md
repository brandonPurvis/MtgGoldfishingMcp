# Storage — Specs

Design: `storage-design.md`. Prefix: `STOR`.

## Adapter

- [ ] **STOR-001**: The SQLite adapter shall implement the `GameRepository`, `DeckRepository`, `RecordStore` and `UnitOfWork` ports and the card cache, and shall pass each port's contract tests.
- [ ] **STOR-002**: The SQLite adapter shall open its database in WAL mode.
- [ ] **STOR-003**: When the service starts and the configured database file or its directory does not exist, the SQLite adapter shall create them.
- [ ] **STOR-004**: The SQLite adapter shall store a game's current state as one JSON document and treat that document as authoritative over any other column of the game's row.
- [ ] **STOR-005**: The SQLite adapter shall return from `GameRepository` a game equal to the one last saved, including after the service has been restarted.

## Transactions

- [ ] **STOR-006**: When a unit of work is committed, the SQLite adapter shall save the game state, log entry, snapshots and call record written within it together, or none of them.
- [ ] **STOR-007**: When a unit of work is rolled back, the SQLite adapter shall leave the database as it was before the unit of work began.

## Concurrency

- [ ] **STOR-008**: When saving a game, the SQLite adapter shall compare the stored game's version counter with the version the game was loaded at, save and increment the counter when they match, and fail the save without writing when they do not.
- [ ] **STOR-009**: While a game is being written, the SQLite adapter shall allow other games to be read and written without waiting for it.

## Loaded decks and records

- [ ] **STOR-010**: When asked to add a loaded deck whose id already exists, the SQLite adapter shall leave the existing loaded deck in place.
- [ ] **STOR-011**: The SQLite adapter shall keep games, log entries, snapshots, call records and loaded decks indefinitely and delete none of them automatically.
- [ ] **STOR-012**: When asked for a game's records after a given change number, the SQLite adapter shall return only log entries with a greater sequence number, call records with a greater change number, and snapshots written by those entries.

## Schema

- [ ] **STOR-013**: When the service starts against a database with an older schema version, the SQLite adapter shall apply forward migrations to reach the current schema version before serving.
- [ ] **STOR-014**: If the service starts against a database with a newer schema version than it supports, then the service shall exit with a message naming both versions and change nothing.
