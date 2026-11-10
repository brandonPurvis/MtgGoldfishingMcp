# Records — Specs

Design: `records-design.md`. Prefix: `REC`.

## Log

- [x] **REC-001**: When a changing call is accepted in any game, from `new_game` through `end_game` and whichever seat made it, the service shall append one log entry for the game whose `seq` equals the game's change number after the call.
- [x] **REC-002**: In every game, the service shall append no log entry for a refused call, for `get_state` or `get_log`, or for a resent call that was recognised and not applied again.
- [x] **REC-003**: In every game, a log entry shall record the turn and step the game was in when the call was made (turn 0 and no step during mulligans), the tool, and the arguments as received, with object and list parameters given as JSON strings decoded, except that in a contested game an opposing seat's seat id given as `game_id` is replaced as REC-058 specifies.
- [x] **REC-004**: In every game, a log entry for `play` or `effect` shall record the card played or the effect's source, the zone a played card came from, the delta as applied including what the service added, the choices, and the payment made.
- [x] **REC-005**: In every game, a log entry shall record the agent's `reason` verbatim.
- [x] **REC-006**: In every game, a log entry shall record any `override` reason, the rule checks it overrode, any `expect` mismatches, any assumptions the service made, the cards drawn, the steps entered, the reminders issued and the notices first raised by the call.
- [x] **REC-007**: In every game, a log entry's `outcome` shall record what the tool produced that no other field carries: for `new_game` of a goldfish game the opening hand; for `mulligan` the new hand and cards bottomed; for `choose` where each revealed card went; for `attack` the attackers, blocked attackers and targets; for the call that enters `combat_damage` the damage per attacker; for `advance` the cards discarded; for `end_game` the result and notes.
- [x] **REC-008**: In every game, the records domain shall build each log entry from the call's events and the game before and after the call, and not from response text.
- [ ] **REC-026**: The service shall append no log entry for a `wait` call, in a goldfish game or a contested game.
- [ ] **REC-027**: In a contested game, the service shall keep one log for the whole game, holding the accepted changes of every seat in change-number order, including what each seat did in its hidden zones (hand and library).
- [ ] **REC-028**: In a contested game, a log entry of any tool other than `new_game` shall record as `seat` the seat number of the seat whose call it records.
- [ ] **REC-029**: In a contested game, a log entry shall record as `active` the active seat's seat number when the call was made, or null during mulligans.
- [ ] **REC-030**: In a contested game, a log entry's `turn` shall be the active seat's own turn number (the number of turns that seat has begun, as its status line shows it).
- [ ] **REC-031**: In a contested game, a log entry shall record as `table_turn` the game's table turn number (turns taken by all seats) and as `round` the game's round when the call was made.
- [ ] **REC-032**: In a contested game, when an accepted `play` or `effect` call puts an item on the stack, the call's log entry shall record that stack item in `stacked`.
- [ ] **REC-033**: In a contested game, when an accepted `play` or `effect` call puts an item on the stack, the call's log entry shall record in `delta` and `paid` what was stated and what was paid when the call was applied, not what the item later did on resolving.
- [ ] **REC-034**: In a contested game, when an accepted call causes one or more stack items to resolve, that call's log entry shall record each in `resolved`, in the order resolved, with the item, its controller's seat number, its source, the delta that was applied and where its card went.
- [ ] **REC-035**: In a contested game, when a stack item resolves, the service shall leave unchanged the earlier log entry of the call that put the item on the stack.
- [ ] **REC-036**: In a contested game, when an accepted call's delta removes stack items with `counter`, the call's log entry shall record those items in `countered`.
- [ ] **REC-037**: In a contested game, when an accepted call causes the service to pass automatically for a seat, the call's log entry shall record in `auto_passes` that seat's number and the stack item passed on, or null when the response window has no item.
- [ ] **REC-038**: In a contested game, when an accepted call causes the service to declare no blockers for an attacked seat, the call's log entry shall record that seat's number in `auto_passes`.
- [ ] **REC-039**: In a contested game, when an accepted call causes one or more seats to be eliminated, the call's log entry shall record in `eliminated` each such seat's number and the cause of its elimination.
- [ ] **REC-040**: In a contested game, every log entry shall store in `public` the public form of the call's events (what any seat may see of them: for example a card moved between or into hidden zones shown as a count, not by name), as produced by the domain when the entry is built.
- [ ] **REC-041**: In a contested game, each reminder recorded on a log entry shall name the seat number of the seat it was issued to.
- [ ] **REC-042**: In a goldfish game, log entries, snapshots, call records and the `game` object of `get_log` shall leave out every field that only a contested game has (`seat`, `active`, `table_turn`, `round`, `stacked`, `resolved`, `countered`, `auto_passes`, `eliminated`, `public`, `lives`, `seats`).

## Reminders

- [x] **REC-009**: In a goldfish game, when a reminder has been issued for a permanent, the reminder shall count as answered if an `effect` call whose `source` names that permanent is accepted later in the same turn, and as unanswered otherwise.
- [x] **REC-010**: In every game, when deciding whether an `effect` call's `source` names a permanent, the records domain shall accept, ignoring case, the permanent's card name, the name of its face in play, or its instance id.
- [ ] **REC-043**: In a contested game, when a reminder has been issued to a seat for a permanent, the reminder shall count as answered if an `effect` call from that same seat whose `source` names that permanent is accepted later in the same table turn, and as unanswered otherwise.
- [ ] **REC-044**: In a contested game, when a seat calls `pass` on a reminder issued to it, the reminder shall count as unanswered.

## Turn snapshots

- [x] **REC-011**: When a goldfish game enters `cleanup`, after any discard, the service shall write a snapshot for the turn holding the hand, the battlefield with tapped state and counters, the graveyard, the number of lands, mana available, mana spent, whether a land drop was made, life, damage dealt, commander damage to each of the three imaginary opponents and unanswered reminders.
- [x] **REC-012**: In every game, when `end_game` ends the game during a turn that has no snapshot, the service shall write a snapshot for that turn.
- [x] **REC-013**: The service shall write at most one snapshot per turn of a goldfish game.
- [x] **REC-014**: In every game, a snapshot shall mark each card in the described seat's hand `payable` when the mana cost of the card's first face, with X as 0 and each Phyrexian symbol paid with mana, could be paid if every mana source of that seat the auto payment system may use on its own were untapped, and shall mark every land `payable`.
- [x] **REC-015**: In every game, a snapshot's `mana_available` shall be the most mana the described seat's mana sources the auto payment system may use on its own could make, counted when the game entered the turn's `main1`, ignoring tapped state and summoning sickness.
- [x] **REC-016**: In every game, a snapshot's `mana_spent` shall be the amount of mana the described seat paid across the turn's payments, a generic symbol counting as its number and a generic hybrid paid as generic as two, not counting life.
- [ ] **REC-045**: When a contested game enters `cleanup` of any seat's turn, after any discard, the service shall write a snapshot describing the active seat: its hand, its battlefield with tapped state and counters, its graveyard, its number of lands, its mana available, its mana spent, whether it made a land drop, its life and its unanswered reminders.
- [ ] **REC-046**: A snapshot of a contested game shall record the active seat's number as `seat`, the table turn number as `table_turn`, the round as `round`, every seat's life by seat number as `lives`, and the seat numbers of the eliminated seats as `eliminated`.
- [ ] **REC-047**: A snapshot of a contested game shall record as `commander_damage` the combat damage each of the active seat's commanders has dealt to each other seat, by seat number, and shall leave out `damage_dealt` and the three-number commander damage of a goldfish game.
- [ ] **REC-048**: The service shall write at most one snapshot per table turn of a contested game.
- [ ] **REC-049**: A snapshot of a contested game shall record as `turn` the active seat's own turn number (the number of turns that seat has begun), the table turn number being held in `table_turn`.
- [ ] **REC-050**: In a contested game, when the tested seat's `end_game` ends the game during a table turn that has no snapshot, the snapshot written for that turn shall describe the seat that is active at that moment.

## Call records

- [x] **REC-017**: When any tool call is received, whatever its outcome and whether or not it names an existing game, the service shall store one call record holding the time, the game id (the id as supplied when it names no game), the tool, the arguments as received, with object and list parameters given as JSON strings decoded, the status, the response exactly as returned, whether the call carried an override, and the game's change number after the call, except that in a contested game an opposing seat's seat id is replaced as REC-058 and REC-059 specify.
- [x] **REC-018**: When a `get_log` call succeeds in any game, its call record's response shall hold a one-line note of the export's size in place of the export.
- [ ] **REC-051**: When a tool call is made with the seat id of an opposing seat of a contested game, the call record's `game_id` shall be the id of that seat's game, not the seat id supplied.
- [ ] **REC-052**: When a game-scoped tool call is made with a seat id of a contested game, the call record shall record the calling seat's seat number as `seat`.
- [ ] **REC-053**: When a `wait` call is received, in a goldfish game or a contested game, the service shall store one call record for it as for any other tool call.

## `get_log`

- [x] **REC-019**: When `get_log` succeeds in any game, the response shall be JSON holding the game's id, the tested seat's deck id, seed, turn limit, first-turn-draw setting, status, turn, change number and result, and the game's log entries.
- [x] **REC-020**: When `get_log` is called with `include_snapshots` omitted or true, in any game, the response shall include the game's snapshots.
- [x] **REC-021**: When `get_log` is called with `include_calls` true, in any game, the response shall include the game's call records, and shall omit them otherwise.
- [x] **REC-022**: When `get_log` is called with `since`, in any game, the response shall include only log entries with a greater sequence number, call records with a greater change number, and snapshots written by those entries.
- [x] **REC-023**: `get_log` shall be accepted in every game status of a goldfish game or a contested game and shall never change a game.
- [x] **REC-024**: If the id given to `get_log` names no existing game or the call has a malformed argument, then `get_log` shall respond in the text `ERROR` format used by every other tool.
- [x] **REC-025**: The service shall compute no statistics from the records of any game beyond the fields of the log entry, snapshot and call record.
- [ ] **REC-055**: When `get_log` succeeds in a contested game, the response shall hold the same whole record whichever seat called: every seat's log entries, snapshots and (when included) call records, with no hidden-zone content removed.
- [ ] **REC-056**: When `get_log` succeeds in a contested game, the response's `game` object shall also hold the table turn number, the round, and one object per seat in turn order giving its seat number, deck id, whether it is the tested seat, its starting life, its current life and whether it is eliminated.
- [ ] **REC-057**: No log entry, snapshot, call record or `get_log` `game` object of a contested game shall contain an opposing seat's seat id in any field, arguments and stored response text included; each names seats by seat number.
- [ ] **REC-058**: When a tool call is made with the seat id of an opposing seat of a contested game, the stored `arguments` of its call record, and of its log entry when the call is accepted, shall hold the game id in place of the seat id given as `game_id`.
- [ ] **REC-059**: When `new_game` creates a contested game, its call record's stored `response` shall be the returned response with each opposing seat's seat id replaced by the redaction mark `[redacted]`, the response returned to the caller being unchanged.
- [ ] **REC-060**: When `new_game` creates a contested game, its log entry and its call record shall each record a null `seat`.
- [ ] **REC-061**: When `new_game` creates a contested game, its log entry's `outcome` shall hold every seat's opening hand by seat number.
- [ ] **REC-062**: When `new_game` creates a contested game, its log entry shall store no public events in `public`.
- [ ] **REC-063**: When `get_log` succeeds in a contested game, the `turn` of the response's `game` object shall be the tested seat's own turn count (the number of turns the tested seat has begun), with the table turn number beside it as `table_turn`.
- [ ] **REC-064**: When the turn of an eliminated active seat ends in a contested game without entering `cleanup` and that table turn has no snapshot, the service shall write a snapshot for that table turn when the turn ends, describing the eliminated seat as its elimination left it.
