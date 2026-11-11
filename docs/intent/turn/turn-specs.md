# Turn — Specs

Design: `turn-design.md`. Prefix: `TURN`.

## Steps and automatic actions

- [x] **TURN-001**: In every game, goldfish or contested, the game shall move through the steps of a turn in the order `untap`, `upkeep`, `draw`, `main1`, `begin_combat`, `declare_attackers`, `declare_blockers`, `combat_damage`, `end_combat`, `main2`, `end`, `cleanup`, with `untap` of the next turn following `cleanup`.
- [x] **TURN-002**: When the game enters `untap`, in a goldfish game or a contested game, the game shall increase the table turn number (the count of turns begun by all seats of the game) and the active seat's own turn count by one, untap every permanent the active seat controls, set the active seat's land drops used to zero and reset the active seat's turn statistics.
- [x] **TURN-003**: When the game enters `draw`, in a goldfish game or a contested game, the active seat shall draw one card, except on the first turn of the game (table turn 1), whichever seat takes it, in a game whose `draw_first_turn` is false.
- [x] **TURN-004**: When the game enters `cleanup`, in a goldfish game or a contested game, the game shall make any discard given with the advance from the active seat's hand and then write the turn's snapshot.
- [x] **TURN-005**: When the game leaves any step, in a goldfish game or a contested game, the game shall empty every seat's mana pool.
- [x] **TURN-027**: When a contested game enters `untap`, the game shall leave unchanged the tapped state of permanents controlled by seats other than the active seat, and the land drops used and turn statistics of those seats.
- [x] **TURN-028**: When a seat enters the `draw` step of its own first turn on a table turn later than the first, in a contested game whose `draw_first_turn` is false, that seat shall draw one card.
- [ ] **TURN-029**: In every game, goldfish or contested, the game shall let the active seat stop in any step, including a step that has an automatic action, whose action has already been performed on entering it.
- [ ] **TURN-030**: When the active seat makes changes while the game is stopped in `cleanup`, in a goldfish game or a contested game, the game shall not add those changes to the turn snapshot already written on entering `cleanup`.

## Turns and rounds

- [x] **TURN-031**: When the active seat of a contested game leaves `cleanup`, its turn shall end and the next seat in turn order that is still in the game (not eliminated) shall become the active seat and begin its turn by entering `untap`.
- [x] **TURN-032**: In a goldfish game, the tested seat shall be the active seat of every turn, and the three imaginary opponents shall take no turns.
- [x] **TURN-033**: When the turn of a contested game passes to a seat that comes earlier in turn order than the seat whose turn just ended, or to the same seat when it is the only seat still in the game, the game shall increase its round number by one; the first turn of the game shall begin round 1.
- [x] **TURN-034**: In a goldfish game, the round number shall equal the turn number.
- [x] **TURN-036**: When the active seat of a contested game is eliminated during its turn, the game shall discard the declared attack and every waiting pending choice of kind `blocks`.
- [ ] **TURN-037**: When the active seat of a contested game is eliminated while other seats' items remain on the stack or a pending choice waits, the game shall go on asking the remaining seats about those items, resolving them and waiting for those pending choices, and shall begin the next seat's turn only once the stack is empty and no pending choice waits.
- [x] **TURN-038**: When the turn of an eliminated active seat ends in a contested game, the game shall empty every seat's mana pool and the next seat in turn order still in the game shall begin its turn as it would after a `cleanup`: through `untap`, `upkeep` and `draw` to `main1`, stopping where a reminder stops it.
- [ ] **TURN-061**: When the active seat of a contested game is eliminated while an `attack` or `end` response window is open, the game shall ask no further seat in that window and shall close it once the stack is empty, instead of beginning its asking again.
- [x] **TURN-062**: When a turn of a contested game ends and no seat is still in the game (every seat eliminated), the game shall begin no turn and shall have no active seat.

## Beginning another seat's turn

- [x] **TURN-039**: In a contested game, an `advance` shall never move the game past the end of the calling active seat's turn: when its `to` names a step whose next occurrence lies in a later turn, the advance shall end on leaving the active seat's `cleanup`.
- [x] **TURN-040**: When an `advance` leaves the active seat's `cleanup` in a contested game, the next seat's turn shall proceed within the same call through its `untap`, `upkeep` and `draw` steps to its `main1`, performing each step's automatic action exactly as an `advance` to `main1` would and stopping in the step where a reminder stops it.
- [x] **TURN-041**: When a call begins a new seat's turn in a contested game and no pending choice, reminder for another seat or response window waits, the new active seat shall be the seat to act.
- [x] **TURN-042**: When a call begins another seat's turn in a contested game, the outcome of that call shall show the turn passing to the new active seat, and shall name the card the new active seat drew only to that seat, showing it to every other seat as a count.

## `advance`

- [x] **TURN-006**: When `advance` is accepted without `to`, in a goldfish game or a contested game, the game shall move to the next step.
- [x] **TURN-007**: When `advance` is accepted with `to`, in a goldfish game or a contested game, the game shall move forward through every step up to and including the next occurrence of the named step within the limits of the stops these specs define, performing each entered step's automatic action.
- [x] **TURN-008**: When `advance` is called in a goldfish game with `to` naming the step the game is already in, the game shall move to that step in the following turn.
- [x] **TURN-009**: When `advance` is accepted, in a goldfish game or a contested game, the outcome shall list the steps entered, any card drawn, any reminders and any notices raised.
- [x] **TURN-010**: If `advance` is called with `to` naming an unknown step, in a goldfish game or a contested game, then `advance` shall return an error and the game shall not move.
- [x] **TURN-043**: If a seat of a contested game that is not the active seat calls `advance`, then `advance` shall return an error and the game shall not move.
- [x] **TURN-044**: If the active seat of a contested game calls `advance` while it is not the seat to act, because a pending choice or another seat's reminder is waiting on another seat, then `advance` shall return an error and the game shall not move.
- [x] **TURN-046**: When an `advance` stops short of its target, in a goldfish game or a contested game, the outcome shall be `OK`, say why it stopped, and say what to send next with the change number to pass as `after`.

## Stopping for reminders

- [x] **TURN-011**: When an advance enters a step in which a permanent on the battlefield controlled by the active seat has a step trigger for that step, read from its face in play as happening on its controller's turn or on each turn, in a goldfish game or a contested game, the game shall issue a reminder for that permanent and step to the active seat.
- [x] **TURN-012**: When an advance enters a step for which a reminder is issued and `to` names a later step, in a goldfish game or a contested game, the game shall stop in the step with the reminder, and the outcome shall be `OK`, say that the advance stopped for the reminder, and say what to send to continue.
- [x] **TURN-013**: The game, goldfish or contested, shall not stop an advance on account of step triggers in the step the advance starts from.
- [x] **TURN-014**: When several permanents with the same name and the same controller are reminded in the same step, in a goldfish game or a contested game, the outcome shall list that name once with a count.
- [x] **TURN-015**: The game, goldfish or contested, shall never refuse an advance because a reminder issued to the active seat has not been answered.
- [x] **TURN-016**: The game, goldfish or contested, shall not remember the target of an advance that stopped early.
- [ ] **TURN-047**: In every game, goldfish or contested, the game shall issue no reminder to the active seat for a step trigger read as happening only on opponents' turns.
- [ ] **TURN-048**: When a contested game enters a step in which a permanent on the battlefield controlled by a seat other than the active seat has a step trigger for that step, read from its face in play as happening on each turn or on each opponent's turn, the game shall issue a reminder for that permanent and step to the seat that controls it.
- [ ] **TURN-049**: When a contested game enters a step, the game shall issue no reminder for a permanent controlled by a seat other than the active seat whose step trigger for that step is read as happening on its controller's turn only.
- [ ] **TURN-050**: In a contested game, the game shall issue one reminder per reminded permanent, to the seat that controls that permanent at the moment the step is entered.
- [ ] **TURN-051**: When a reminder is issued to a seat other than the active seat in a contested game, the advance shall stop in that step even when `to` names a later one, and the reminded seat shall become the seat to act.
- [ ] **TURN-052**: When a seat other than the active seat is the seat to act because of a reminder in a contested game, the game shall go on waiting on that seat until each reminder issued to it in that step has been answered by an `effect` (TURN-063) or it calls `pass` (TURN-064).
- [ ] **TURN-063**: When a seat that a contested game waits on for a reminder calls `effect` without `immediate` true and with a `source` naming a permanent it was reminded of in that step (by card name, the name of its face in play, or instance id, ignoring case), the game shall put the ability on the stack and count as answered that step's reminders for every such permanent the `source` names.
- [ ] **TURN-064**: When a seat that a contested game waits on for a reminder calls `pass`, the game shall stop waiting on that seat for every reminder of that step still unanswered, however many there are.
- [ ] **TURN-065**: When a seat that a contested game waits on for a reminder calls `play`, an `effect` with `immediate` true, or an `effect` with a `source` that names no permanent it was reminded of in that step, the game shall apply the call as it would from a seat asked in a response window and shall leave that seat's reminders waiting.
- [ ] **TURN-066**: While a reminder waits for a seat other than the active seat in a contested game, the game shall ask no seat in a response window, make no automatic pass and resolve no stack item (STACK-070), so that every reminded seat can put its trigger on the stack before any of them resolves.
- [ ] **TURN-067**: In a contested game, a reminder issued to the active seat shall not make the game wait on it: the active seat shall stay the seat to act with the same calls accepted from it as when no reminder is issued (`pass` not among them, STACK-054).
- [ ] **TURN-053**: When reminders are issued to several seats other than the active seat in the same step of a contested game, the game shall wait on those seats one at a time, in turn order starting from the seat after the active seat.
- [ ] **TURN-054**: When every seat other than the active seat that was issued a reminder in a step of a contested game has answered each of its reminders or called `pass`, and the stack is empty, no pending choice waits and no response window is open, the active seat shall be the seat to act again and shall continue with `advance`; in `end`, where the end-step response window is open, that window's asking begins instead (STACK-083).
- [ ] **TURN-055**: When permanents with the same name but different controllers are reminded in the same step of a contested game, the game shall issue each controller its own reminder and shall not combine them into one count.

## Stopping at the end step

- [ ] **TURN-056**: When an advance enters `end` in a contested game and the end-step response window (other seats asked in turn order whether they respond) is left waiting on a seat, the advance shall stop in `end`, even when `to` names a later step.
- [ ] **TURN-057**: When an advance stops in `end` of a contested game for the end-step response window, the outcome shall say that the other seats are being asked and name the seat being asked by seat number.
- [ ] **TURN-068**: When an advance enters `end` in a contested game and every other seat still in the game is passed automatically, or no other seat is still in the game, the end-step response window shall close within the advance and the advance shall go on toward its `to` without stopping on account of the window.
- [ ] **TURN-069**: When an advance of a contested game passes through `end` without stopping because every other seat was passed automatically, the outcome shall report each automatic pass, naming the seat.
- [ ] **TURN-059**: When an advance enters `end` in a goldfish game, the advance shall not stop on account of any response window.

## Hand size at cleanup

- [x] **TURN-017**: When an advance is about to enter `cleanup` with more than seven cards in the active seat's hand and the call gives neither `discard` nor `override`, in a goldfish game or a contested game, the game shall stop in `end`, and the outcome shall be `OK` and state how many cards must be discarded.
- [x] **TURN-018**: When an advance enters `cleanup` with `discard` naming exactly as many cards in the active seat's hand as that hand exceeds seven, in a goldfish game or a contested game, the game shall move those cards from the active seat's hand to its graveyard on entering `cleanup`.
- [x] **TURN-019**: When an advance enters `cleanup` with more than seven cards in the active seat's hand, an `override` reason and no `discard`, in a goldfish game or a contested game, the game shall enter `cleanup` without discarding.
- [x] **TURN-020**: When an advance enters `cleanup` with an `override` reason and `discard` naming any number of cards in the active seat's hand, in a goldfish game or a contested game, the game shall discard the cards named.
- [x] **TURN-021**: If an advance starts in `end` with more than seven cards in the active seat's hand and gives neither `discard` nor `override`, in a goldfish game or a contested game, then `advance` shall fail a rule check and the game shall not move.
- [x] **TURN-022**: If an advance that enters `cleanup` gives `discard` naming a number of cards different from the number by which the active seat's hand exceeds seven on entering `cleanup` and gives no `override`, in a goldfish game or a contested game, then `advance` shall fail a rule check and the game shall not move.
- [x] **TURN-023**: If `discard` names a card that is not in the active seat's hand, in a goldfish game or a contested game, then `advance` shall return an error and the game shall not move.
- [x] **TURN-024**: If `discard` is given on an advance that does not enter `cleanup`, whether because its target is earlier or because it stops first for a reminder or, in a contested game, for the end-step response window, then `advance` shall return an error and the game shall not move.
- [x] **TURN-060**: In a contested game, the game shall apply the seven-card hand limit at `cleanup` to the active seat's hand only, and shall require no discard of any other seat.

## Other

- [x] **TURN-025**: The game, goldfish or contested, shall not stop or refuse an advance because the turn number or the round number has reached or passed `turn_limit`.
- [x] **TURN-026**: When an additional combat returns the game to `declare_attackers` within the same turn, in a goldfish game or a contested game, the game shall empty every seat's mana pool and leave the table turn number, the active seat's turn count and the round number unchanged.
