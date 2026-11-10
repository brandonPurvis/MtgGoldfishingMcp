# Records — Specs

Design: `records-design.md`. Prefix: `REC`.

## Log

- [ ] **REC-001**: When a changing call is accepted, from `new_game` through `end_game`, the service shall append one log entry for the game whose `seq` equals the game's change number after the call.
- [ ] **REC-002**: The service shall append no log entry for a refused call, for `get_state` or `get_log`, or for a resent call that was recognised and not applied again.
- [ ] **REC-003**: A log entry shall record the turn and step the game was in when the call was made, the tool, and the call's arguments as received.
- [ ] **REC-004**: A log entry for `play` or `effect` shall record the card played or the effect's source, the zone a played card came from, the delta as applied including what the service added, the choices, and the payment made.
- [ ] **REC-005**: A log entry shall record the agent's `reason` verbatim.
- [ ] **REC-006**: A log entry shall record any `override` reason, the rule checks it overrode, any `expect` mismatches, any assumptions the service made, the cards drawn, the steps entered, the reminders issued and the notices first raised by the call.
- [ ] **REC-007**: A log entry's `outcome` shall record what the tool produced that no other field carries: for `new_game` the opening hand; for `mulligan` the new hand and cards bottomed; for `choose` where each revealed card went; for `attack` the attackers, blocked attackers and targets; for the call that enters `combat_damage` the damage per attacker; for `advance` the cards discarded; for `end_game` the result and notes.
- [ ] **REC-008**: The records domain shall build each log entry from the call's events and the game before and after the call, and not from response text.

## Reminders

- [ ] **REC-009**: When a reminder has been issued for a permanent, the reminder shall count as answered if an `effect` call whose `source` names that permanent is accepted later in the same turn, and as unanswered otherwise.
- [ ] **REC-010**: When deciding whether an `effect` call's `source` names a permanent, the records domain shall accept, ignoring case, the permanent's card name, the name of its face in play, or its instance id.

## Turn snapshots

- [ ] **REC-011**: When the game enters `cleanup`, after any discard, the service shall write a snapshot for the turn holding the hand, the battlefield with tapped state and counters, the graveyard, the number of lands, mana available, mana spent, whether a land drop was made, life, damage dealt, commander damage and unanswered reminders.
- [ ] **REC-012**: When `end_game` is called during a turn that has no snapshot, the service shall write a snapshot for that turn.
- [ ] **REC-013**: The service shall write at most one snapshot per turn of a game.
- [ ] **REC-014**: A snapshot shall mark each card in hand `payable` when the mana cost of the card's first face, with X as 0, could be paid if every mana source the auto payment system may use on its own were untapped, and shall mark every land `payable`.
- [ ] **REC-015**: A snapshot's `mana_available` shall be the most mana the mana sources the auto payment system may use on its own could make, counted when the game entered the turn's `main1`.
- [ ] **REC-016**: A snapshot's `mana_spent` shall be the number of mana symbols paid across the turn's payments, not counting life.

## Call records

- [ ] **REC-017**: When any tool call is received, whatever its outcome and whether or not it names an existing game, the service shall store one call record holding the time, the game id as supplied, the tool, the arguments as received, the status, the response exactly as returned, whether the call carried an override, and the game's change number after the call.
- [ ] **REC-018**: When a `get_log` call succeeds, its call record's response shall hold a one-line note of the export's size in place of the export.

## `get_log`

- [ ] **REC-019**: When `get_log` succeeds, the response shall be JSON holding the game's id, deck id, seed, turn limit, first-turn-draw setting, status, turn, change number and result, and the game's log entries.
- [ ] **REC-020**: When `get_log` is called with `include_snapshots` omitted or true, the response shall include the game's snapshots.
- [ ] **REC-021**: When `get_log` is called with `include_calls` true, the response shall include the game's call records, and shall omit them otherwise.
- [ ] **REC-022**: When `get_log` is called with `since`, the response shall include only log entries with a greater sequence number, call records with a greater change number, and snapshots written by those entries.
- [ ] **REC-023**: `get_log` shall be accepted in every game status and shall never change a game.
- [ ] **REC-024**: If `get_log` names no existing game or has a malformed argument, then `get_log` shall respond in the text `ERROR` format used by every other tool.
- [ ] **REC-025**: The service shall compute no statistics from records beyond the fields of the log entry, snapshot and call record.
