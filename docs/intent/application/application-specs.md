# Application — Specs

Design: `application-design.md`. Prefix: `APP`.

## Dependency rule

- [ ] **APP-001**: Modules under `mtg_goldfishing.domain` shall import only the Python standard library and other modules under `mtg_goldfishing.domain`.
- [ ] **APP-002**: Modules under `mtg_goldfishing.application` shall import only the Python standard library, `mtg_goldfishing.domain` and `mtg_goldfishing.application`.
- [ ] **APP-003**: No module other than the composition root `mtg_goldfishing.bootstrap` shall import a module under `mtg_goldfishing.adapters`, except adapter modules importing within their own adapter package.
- [ ] **APP-004**: An automated architecture test shall fail when any of the import rules APP-001 to APP-003 is broken.

## Domain model shape

- [ ] **APP-005**: Domain value objects shall be immutable, compare by value, and reject invalid values on construction.
- [ ] **APP-006**: Every domain operation on a game shall return either an applied result holding the changed game and its events, or a refusal holding errors or failed rule checks, and shall not raise an exception to signal a refusal.
- [ ] **APP-007**: When a domain operation returns a refusal, the game passed to the operation shall be unchanged.
- [ ] **APP-008**: The domain shall perform no input or output, read no clock, and draw no randomness other than from a seed passed to it.

## Outcomes

- [ ] **APP-009**: Every use case shall return an outcome holding a status of `OK`, `REJECTED`, `ERROR` or `CHOICE`, a summary event, a list of typed events in the order they happened, and a game summary when the call concerns an existing game.
- [ ] **APP-010**: The domain and application shall produce no response text; events shall be typed values carrying facts.

## Ports

- [ ] **APP-011**: The application shall define the ports `GameRepository`, `DeckRepository`, `RecordStore`, `CardCatalog`, `UnitOfWork`, `GameLocks`, `IdSource`, `Clock` and `Renderer`, each expressed in domain types.
- [ ] **APP-012**: Every adapter implementing a port shall pass that port's contract test suite, including the in-memory adapters.
- [ ] **APP-013**: The in-memory adapters shall be working implementations that keep their data in memory, with a card catalog loaded from recorded card data, an id source that yields a fixed sequence, and a clock set by the test.

## Use cases

- [ ] **APP-014**: When a use case handles a call about a game, the use case shall hold that game's lock from before loading the game until after its records are saved.
- [ ] **APP-015**: When two calls for the same game arrive at once, the application shall apply them one after the other, the second seeing the first's result.
- [ ] **APP-016**: When calls for different games arrive at once, the application shall not make one wait for another's lock.
- [ ] **APP-017**: When a domain operation returns an applied result, the use case shall save the game, the log entry and any snapshot in one unit of work.
- [ ] **APP-018**: When a domain operation returns a refusal, the use case shall save nothing about the game.
- [ ] **APP-019**: When a use case finishes, whatever the outcome, the use case shall have added a call record for the call.
- [ ] **APP-026**: When a use case adds a call record, the record's response shall be the text `Renderer` produced for the call's outcome.
- [ ] **APP-027**: When the MCP adapter cannot shape a call's arguments, the application shall return an `ERROR` outcome, carrying the game summary when the call names an existing game, and add a call record for the call.
- [ ] **APP-028**: When the domain reads a structured argument (`delta`, `choices`, `pay`, `expect`, `selections`, `definitions`) that is malformed, the domain shall return an error rather than raise an exception.
- [ ] **APP-020**: If a use case fails unexpectedly, then the use case shall roll back its unit of work, add a call record, and return an `ERROR` outcome stating that the failure was inside the service and not caused by the call.
- [ ] **APP-021**: If saving a game fails because the stored game changed since it was loaded, then the use case shall save nothing and return an `ERROR` outcome asking for the call to be sent again.
- [ ] **APP-022**: When a `play` call brings a card from outside the game, the use case shall resolve that card's data through `CardCatalog` before calling the domain.
- [ ] **APP-023**: Use cases shall contain no rule of play: every decision about cards, zones, mana, steps or costs shall be made by the domain.

## Testing

- [ ] **APP-024**: The domain tests and the behave feature tests shall run without a database file, a network connection or a running server.
- [ ] **APP-025**: The behave feature tests shall drive the MCP adapter's tool functions in-process over the in-memory adapters.
