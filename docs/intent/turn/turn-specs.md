# Turn — Specs

Design: `turn-design.md`. Prefix: `TURN`.

## Steps and automatic actions

- [x] **TURN-001**: The game shall move through the steps of a turn in the order `untap`, `upkeep`, `draw`, `main1`, `begin_combat`, `declare_attackers`, `declare_blockers`, `combat_damage`, `end_combat`, `main2`, `end`, `cleanup`, with `untap` of the next turn following `cleanup`.
- [x] **TURN-002**: When the game enters `untap`, the game shall increase the turn number by one, untap every permanent, set land drops used to zero and reset the turn's statistics.
- [x] **TURN-003**: When the game enters `draw`, the game shall draw one card, except on turn 1 of a game whose `draw_first_turn` is false.
- [x] **TURN-004**: When the game enters `cleanup`, the game shall make any discard given with the advance and then write the turn's snapshot.
- [x] **TURN-005**: When the game leaves any step, the game shall empty the mana pool.

## `advance`

- [x] **TURN-006**: When `advance` is called without `to`, the game shall move to the next step.
- [x] **TURN-007**: When `advance` is called with `to`, the game shall move forward through every step up to and including the next occurrence of the named step, performing each entered step's automatic action.
- [x] **TURN-008**: When `advance` is called with `to` naming the step the game is already in, the game shall move to that step in the following turn.
- [x] **TURN-009**: When `advance` is accepted, the outcome shall list the steps entered, any card drawn, any reminders and any notices raised.
- [x] **TURN-010**: If `advance` is called with `to` naming an unknown step, then `advance` shall return an error and the game shall not move.

## Stopping for reminders

- [x] **TURN-011**: When an advance enters a step in which a permanent on the battlefield has a step trigger read from its face in play, the game shall issue a reminder for that permanent and step.
- [x] **TURN-012**: When an advance enters a step for which a reminder is issued and `to` names a later step, the game shall stop in the step with the reminder, and the outcome shall be `OK`, say that the advance stopped for the reminder, and say what to send to continue.
- [x] **TURN-013**: The game shall not stop an advance on account of step triggers in the step the advance starts from.
- [x] **TURN-014**: When several permanents with the same name are reminded in the same step, the outcome shall list that name once with a count.
- [x] **TURN-015**: The game shall never refuse an advance because a reminder has not been answered.
- [x] **TURN-016**: The game shall not remember the target of an advance that stopped early.

## Hand size at cleanup

- [x] **TURN-017**: When an advance is about to enter `cleanup` with more than seven cards in hand and the call gives neither `discard` nor `override`, the game shall stop in `end`, and the outcome shall be `OK` and state how many cards must be discarded.
- [x] **TURN-018**: When an advance enters `cleanup` with `discard` naming exactly as many cards in hand as the hand exceeds seven, the game shall move those cards from the hand to the graveyard on entering `cleanup`.
- [x] **TURN-019**: When an advance enters `cleanup` with more than seven cards in hand, an `override` reason and no `discard`, the game shall enter `cleanup` without discarding.
- [x] **TURN-020**: When an advance enters `cleanup` with an `override` reason and `discard` naming any number of cards in hand, the game shall discard the cards named.
- [x] **TURN-021**: If an advance starts in `end` with more than seven cards in hand and gives neither `discard` nor `override`, then `advance` shall fail a rule check and the game shall not move.
- [x] **TURN-022**: If an advance that enters `cleanup` gives `discard` naming a number of cards different from the number by which the hand exceeds seven and gives no `override`, then `advance` shall fail a rule check and the game shall not move.
- [x] **TURN-023**: If `discard` names a card that is not in hand, then `advance` shall return an error and the game shall not move.
- [x] **TURN-024**: If `discard` is given on an advance that does not enter `cleanup`, whether because its target is earlier or because it stops for a reminder first, then `advance` shall return an error and the game shall not move.

## Other

- [x] **TURN-025**: The game shall not stop or refuse an advance because the turn number has reached or passed `turn_limit`.
- [x] **TURN-026**: When an additional combat returns the game to `declare_attackers` within the same turn, the game shall empty the mana pool and leave the turn number unchanged.
