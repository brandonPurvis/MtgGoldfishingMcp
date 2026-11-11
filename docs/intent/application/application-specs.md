# Application — Specs

Design: `application-design.md`. Prefix: `APP`.

## Dependency rule

- [x] **APP-001**: Modules under `mtg_goldfishing.domain` shall import only the Python standard library and other modules under `mtg_goldfishing.domain`.
- [x] **APP-002**: Modules under `mtg_goldfishing.application` shall import only the Python standard library, `mtg_goldfishing.domain` and `mtg_goldfishing.application`.
- [x] **APP-003**: No module other than the composition root `mtg_goldfishing.bootstrap` shall import a module under `mtg_goldfishing.adapters`, except adapter modules importing within their own adapter package.
- [x] **APP-004**: An automated architecture test shall fail when any of the import rules APP-001 to APP-003 is broken.

## Domain model shape

- [x] **APP-005**: Domain value objects shall be immutable, compare by value, and reject invalid values on construction.
- [x] **APP-006**: Every domain operation on a game, goldfish or contested, shall return either an applied result holding the changed game and its events, or a refusal holding errors or failed rule checks, and shall not raise an exception to signal a refusal.
- [x] **APP-007**: When a domain operation returns a refusal, in a goldfish game or a contested game, the game passed to the operation shall be unchanged.
- [x] **APP-008**: The domain shall perform no input or output, read no clock, and draw no randomness other than from a seed passed to it.
- [x] **APP-029**: `Game` shall be the one aggregate that changes: the seats of a game, their card instances, zones and mana pools, the stack, the response window, the declared attack, the pending choices and the notices shall be reached and changed only through the `Game` they belong to.
- [x] **APP-030**: A seat shall be an entity inside its `Game`, identified by its seat number, and no port shall save or load a seat on its own.
- [x] **APP-031**: Every domain operation on a `Game` that a tool causes, in a goldfish game or a contested game, shall take the acting seat's seat number as an argument.
- [x] **APP-032**: `SeatId`, `SeatNumber` and `StackItem` shall be domain value objects (immutable, compared by value, rejecting invalid values on construction).
- [x] **APP-033**: The filter that turns an event into its public form (what any seat may see of it) shall be a stateless domain service; no application or adapter code shall decide what is public.

## Outcomes

- [x] **APP-009**: Every use case, in a goldfish game or a contested game, shall return an outcome holding a status of `OK`, `REJECTED`, `ERROR` or `CHOICE`, a summary event, a list of typed events in the order they happened, and a game summary when the call concerns an existing game.
- [x] **APP-010**: The domain and application shall produce no response text; events shall be typed values carrying facts.
- [x] **APP-034**: When a use case handles a call made with a seat id of a contested game, its outcome shall hold the calling seat's seat number.
- [x] **APP-035**: When a use case handles a call made with a seat id of a contested game, the outcome's game summary shall be the calling seat's view of the game (its own hidden zones and every seat's public information), not another seat's.
- [x] **APP-036**: When a use case handles a call other than `get_log` made with a seat id of a contested game, its outcome shall hold a digest: one element for each log entry of that game made by another seat with a change number greater than the calling seat's digest baseline (the change number on that seat's most recent call record for a tool other than `get_log`), oldest first, each holding that entry's seat number, change number and events as the calling seat may see them (APP-081).
- [x] **APP-081**: When a digest element is built from a log entry, its events shall be the list stored for the calling seat's number in that entry's `private` (the call's events as that seat may see them, such as a card it drew named) when the entry has one, and the entry's stored `public` events otherwise.
- [x] **APP-037**: When a use case handles a call other than `get_log` from a seat of a contested game that has no digest baseline (no earlier call record for a tool other than `get_log`), the outcome's digest shall hold every log entry of that game made by another seat since the game began.
- [x] **APP-038**: A digest shall hold no event of the calling seat's own call, no log entry the calling seat made, and never the log entry of `new_game`, which no seat makes.
- [x] **APP-039**: When assembling a digest, the use case shall take each log entry's stored `public` or `private` event list as it is, and shall neither compute the public or private form of any event nor merge the two lists.
- [x] **APP-040**: When a use case handles a call in a goldfish game, its outcome shall hold no digest and no calling seat number.
- [ ] **APP-094**: When a use case builds the game summary for a call made with a seat id of a contested game whose calling seat is not among the seats to act, and the game holds the change number since which its seats to act have been asked (GAME-180) and `RecordStore` gives a time for that change (APP-093), the game summary shall hold how long the seats to act have been asked: the whole seconds, rounded down, from that time to the `Clock`'s now, or 0 when that time is later than now.
- [ ] **APP-095**: When a use case builds a game summary for a goldfish game, for a calling seat that is among the seats to act, for a game with no seat to act, for a game that holds no change number since which its seats to act have been asked, or for a change of which `RecordStore` gives no time, the game summary shall hold no time asked.

## Ports

- [x] **APP-011**: The application shall define the ports `GameRepository`, `DeckRepository`, `RecordStore`, `CardCatalog`, `UnitOfWork`, `GameLocks`, `IdSource`, `Clock` and `Renderer`, each expressed in domain types.
- [x] **APP-012**: Every adapter implementing a port shall pass that port's contract test suite, including the in-memory adapters.
- [x] **APP-013**: The in-memory adapters shall be working implementations that keep their data in memory, with a card catalog loaded from recorded card data, an id source that yields a fixed sequence, and a clock set by the test.
- [x] **APP-041**: The application shall define the port `GameChanges`, with one operation that announces that a game has changed and one that waits until a game changes after a given change number or a timeout passes.
- [x] **APP-042**: Each port shall be an abstract base class defined in `application/ports.py`.
- [x] **APP-043**: Every implementation of a port, in-memory adapters included, shall be a concrete class that inherits from the port it implements.
- [x] **APP-044**: If a class inheriting from a port does not implement every operation of that port, then constructing an object of that class shall fail.
- [x] **APP-045**: `GameRepository` shall offer an operation that finds the game and seat number a seat id names, answering for a game id with that game and its tested seat's number, and reporting when the id names none.
- [x] **APP-046**: `RecordStore` shall offer an operation that gives a seat's digest baseline for a game: the change number on that seat's most recent call record for a tool other than `get_log`, reporting when the seat has no such call record.
- [ ] **APP-093**: `RecordStore` shall offer an operation that gives the time a game's change was made: the time held by the call record of the call that made that change (the time that call was received), which is the earliest-stored call record of that game whose change number is that change, reporting when the game has no such call record.
- [x] **APP-092**: If `RecordStore` is asked to add a snapshot for a game and table turn that already has one, then it shall raise an exception and leave the stored snapshot as it was, a second snapshot for a table turn being a defect and never a replacement.
- [x] **APP-047**: `IdSource` shall supply seat ids as well as game ids and seeds.
- [x] **APP-048**: `GameLocks` and `GameChanges` shall each have exactly one implementation, in-process in `adapters/system`, used by both the running service and the tests.

## Dependency injection

- [x] **APP-049**: `Service` shall receive every port as a keyword argument of its constructor and hand each use case the ports it needs.
- [x] **APP-050**: No module under `mtg_goldfishing.application` shall construct or look up an implementation of a port.
- [x] **APP-051**: Port implementations shall be chosen in exactly two hand-written composition roots: `bootstrap.py`, which builds the running service from the SQLite stores, the Scryfall catalog, the system id source, clock, game locks and game changes, and the text renderer; and the test composition root in `tests/support`, which builds the same service from the in-memory adapters, the recorded card catalog and a set clock and id source.
- [x] **APP-052**: The service shall use no dependency-injection container library.

## Use cases

- [x] **APP-014**: When a use case handles a call about a game, other than the time a `wait` call spends waiting, the use case shall hold that game's lock from before loading the game until after its records are saved.
- [x] **APP-015**: When two calls for the same game arrive at once, whichever seats make them, the application shall apply them one after the other, the second seeing the first's result.
- [x] **APP-016**: When calls for different games arrive at once, the application shall not make one wait for another's lock.
- [x] **APP-017**: When a domain operation returns an applied result, in a goldfish game or a contested game, the use case shall save the game, the log entry, any snapshot and the call record in one unit of work.
- [x] **APP-018**: When a domain operation returns a refusal, in a goldfish game or a contested game, the use case shall save nothing but the call record.
- [x] **APP-019**: When a use case finishes, whatever the outcome, the use case shall have added a call record for the call, read-only calls included, in its own unit of work when nothing else is saved.
- [x] **APP-026**: When a use case adds a call record, the record's response shall be the text `Renderer` produced for the call's outcome, except that for a successful `get_log` the record holds the renderer's one-line note of the export's size.
- [x] **APP-027**: When the MCP adapter cannot shape a call's arguments, the application shall return an `ERROR` outcome, carrying the game summary when the call names an existing game, and add a call record for the call.
- [x] **APP-028**: When the domain reads a structured argument (`delta`, `choices`, `pay`, `expect`, `selections`, `definitions`) that is malformed, the domain shall return an error rather than raise an exception.
- [x] **APP-020**: If a use case fails unexpectedly, then the use case shall roll back its unit of work, add a call record, and return an `ERROR` outcome stating that the failure was inside the service and not caused by the call; if the call record cannot be added either, the use case shall still return that `ERROR` outcome.
- [x] **APP-021**: If saving a game fails because the stored game changed since it was loaded, then the use case shall save nothing but the call record and return an `ERROR` outcome asking for the call to be sent again.
- [x] **APP-022**: When a `play` call brings a card from outside the game, the use case shall resolve that card's data through `CardCatalog` before calling the domain, also when the call gives a card definition, which then replaces the fetched fields it names.
- [x] **APP-023**: Use cases shall contain no rule of play: every decision about cards, zones, mana, steps or costs shall be made by the domain.
- [x] **APP-053**: When a use case handles a game-scoped call, it shall first find, through `GameRepository`, the game and seat number that the id given as `game_id` names, and act as that seat.
- [x] **APP-054**: If the id given as `game_id` to a game-scoped call names no seat of any game, then the use case shall return an `ERROR` outcome with no game summary and change no game.
- [x] **APP-055**: When a changing call is a resend of the calling seat's most recent accepted change, the use case shall answer it as already applied before asking whether the calling seat may make the call now, so that a resend is answered even when the calling seat is no longer a seat to act.
- [x] **APP-056**: If, in a contested game, the domain answers that the calling seat may not make the call now (it is not a seat to act for that tool), then the use case shall return an `ERROR` outcome without calling the domain operation, saving nothing but the call record.
- [x] **APP-057**: When a use case calls a domain operation for a changing call, it shall pass the calling seat's seat number as the acting seat.
- [x] **APP-058**: When a call other than `get_log` made with an id that names a seat of a contested game is answered, whether applied, answered as a resend, refused by the domain, refused because its arguments could not be shaped (APP-027), refused because the save lost a race (APP-021) or read-only, the use case shall assemble the calling seat's digest before rendering the outcome, so that every call record that moves a digest baseline holds a response that carried a digest.
- [x] **APP-082**: When a resend is answered in a contested game, the outcome shall hold the original change's summary and events with the already-applied statement, and a digest assembled at the time of the resend from the calling seat's digest baseline, not the digest of the original response.
- [x] **APP-083**: When a resend is answered, in a goldfish game or a contested game, the outcome's game summary shall describe the game as it stands when the resend is answered, not as it stood after the original change.
- [x] **APP-084**: If a use case handling a call other than `get_log` made with an id that names a seat of a contested game fails unexpectedly (APP-020), then its `ERROR` outcome shall hold the calling seat's digest, assembled after the rollback.
- [x] **APP-085**: If a changing call that is not a resend both may not be made by the calling seat now (APP-056) and gives an `after` that is not the game's change number, then the use case shall return the `ERROR` that the seat may not make the call, not the stale-change-number error.
- [x] **APP-086**: If a changing call that is not a resend may be made by the calling seat now and gives an `after` that is not the game's change number, then the use case shall return the stale-change-number error, also when the call's structured arguments (APP-028) are malformed, the error for a malformed one being returned only for a call that follows the game's change number.
- [x] **APP-059**: When a unit of work that saved an applied change has committed, the use case shall announce through `GameChanges` that the game changed, and shall not announce it before the commit.
- [x] **APP-060**: When a call is refused or read-only, the use case shall make no announcement through `GameChanges`.
- [x] **APP-061**: When `new_game` starts a contested game, the use case shall take the game id and one seat id for each opposing seat from `IdSource`, the tested seat's seat id being the game id.
- [x] **APP-087**: When `new_game` takes values from `IdSource`, it shall take the game id first, then a seed when the call gave none, then, for a contested game, one seat id per opposing seat in `opponents` order, the *k*th seat id taken going to the seat of the *k*th entry of `opponents` whatever its place in turn order.

## `wait`

- [x] **APP-063**: When `wait` is called by a seat of a contested game that is a seat to act, the use case shall return at once with an `OK` outcome whose summary says what that seat is asked to do.
- [x] **APP-064**: When `wait` is called by a seat of a contested game that is not a seat to act, the use case shall hold the call open until the game changes so that the seat is a seat to act, and then return an `OK` outcome whose summary says what that seat is asked to do.
- [x] **APP-065**: When a contested game changes while a `wait` call is open and the calling seat is still not a seat to act, not eliminated and the game not ended, the use case shall go on waiting for what remains of the timeout, also when the change raised a notice.
- [x] **APP-066**: When the timeout of a `wait` call passes before the calling seat becomes a seat to act, the use case shall return an `OK` outcome whose summary is a timed-out event naming each seat to act (during mulligans, every seat still to keep) and what it is asked to do.
- [ ] **APP-096**: When the timeout of a `wait` call in a contested game passes before the calling seat becomes a seat to act, the timed-out event of APP-066 shall hold how long the seats to act have been asked, computed as APP-094 says, or no time when APP-095 gives none.
- [x] **APP-067**: When `wait` is called by an eliminated seat, or on a game that has ended, or the seat is eliminated or the game ends while the call is open, the use case shall return without waiting further.
- [x] **APP-088**: When `wait` returns because the game has ended, in a goldfish game or a contested game, its outcome shall be `OK` with a summary saying the game has ended, also when the calling seat is eliminated.
- [x] **APP-089**: When `wait` returns because the calling seat of a contested game that has not ended is eliminated, its outcome shall be `OK` with a summary saying the seat is eliminated.
- [x] **APP-068**: While a `wait` call is waiting for a game to change, the use case shall hold no lock on that game, so that calls from other seats are applied meanwhile.
- [x] **APP-069**: The use case shall load the game for `wait`, assemble its digest and add its call record only while holding the game's lock.
- [x] **APP-070**: `wait` shall change no game, increase no change number and make no announcement through `GameChanges`.
- [x] **APP-071**: When `wait` returns in a contested game, with or without a timeout, its outcome shall hold the calling seat's digest and game summary.
- [x] **APP-072**: `wait` shall take an optional `timeout` in seconds, defaulting to 30 when omitted.
- [x] **APP-090**: `wait` shall accept as `timeout` any JSON number from 1 to 60 inclusive, a fraction such as `1.5` included, and wait for that many seconds; a `timeout` that is not a number is a malformed argument (APP-027).
- [x] **APP-091**: When `wait` is called with an id that names a seat and a `timeout` outside 1 to 60, the use case shall find the game before checking `timeout`, so that the `ERROR` outcome of APP-073 or APP-078 holds the game summary, the digest in a contested game, and a call record with the calling seat's number.
- [x] **APP-073**: If `wait` is called with a `timeout` greater than 60, in a goldfish game or a contested game, then the use case shall return an `ERROR` outcome without waiting.
- [x] **APP-074**: When `wait` is called in a goldfish game that has not ended, the use case shall return at once with an `OK` outcome whose summary says what the seat is asked to do (keep or mulligan, answer its pending choice, or take its turn), because the only seat is always the seat to act.
- [x] **APP-075**: If the id given to `wait` names no seat of any game, then the use case shall return an `ERROR` outcome without waiting.
- [x] **APP-078**: If `wait` is called with a `timeout` below 1, in a goldfish game or a contested game, then the use case shall return an `ERROR` outcome without waiting.
- [x] **APP-079**: When `get_log` is called with a seat id of a contested game, its outcome shall hold no digest, and its call record shall not move the calling seat's digest baseline.

## Testing

- [x] **APP-024**: The domain tests and the in-process behave feature tests (those outside `features/http`) shall run without a database file, a network connection or a running server.
- [x] **APP-025**: The in-process behave feature tests (those outside `features/http`) shall drive the MCP adapter's tool functions in-process over the in-memory adapters.
- [x] **APP-076**: The in-process behave scenarios of contested games shall drive each seat through the MCP adapter's tool functions with that seat's own seat id.
- [x] **APP-077**: The behave scenarios under `features/http` shall start the real service process with a SQLite database and drive each seat of a contested game through its own MCP client over HTTP.
- [x] **APP-080**: The behave scenarios under `features/http` shall be run by CI and shall not be among the checks run before a commit, as the end-to-end tests under `tests/e2e` are.
