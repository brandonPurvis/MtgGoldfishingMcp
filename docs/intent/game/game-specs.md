# Game — Specs

Design: `game-design.md`. Prefix: `GAME`.

## Creating a game

- [x] **GAME-001**: When `new_game` is called with a known deck id, the game shall be created with its commanders in the command zone, every other card in the library, life 40, status `mulligan`, turn 0 and no step.
- [x] **GAME-002**: When a game is created, the game shall assign instance ids `c1`, `c2`, … to commanders first and then to the remaining cards, each group ordered by lower-cased card name with copies of one card adjacent.
- [x] **GAME-003**: When a game is created, the game shall shuffle the library and deal seven cards to the hand.
- [x] **GAME-004**: When `new_game` is called without a seed, the use case shall obtain a seed from the id source, and the outcome shall state the seed used.
- [x] **GAME-005**: When `new_game` succeeds, the outcome shall state the game id, the seed and the cards in the opening hand.
- [x] **GAME-006**: The game id shall be `g` followed by ten random characters obtained from the id source.
- [x] **GAME-007**: If `new_game` is called with an unknown deck id, then `new_game` shall return an error and create nothing.
- [x] **GAME-008**: If `new_game` is called with a `turn_limit` that is not a positive integer, then `new_game` shall return an error and create nothing.
- [x] **GAME-009**: When `new_game` is called without `draw_first_turn`, the game shall be created with `draw_first_turn` true.

## Shuffling and hidden information

- [x] **GAME-010**: When the library is shuffled, the game shall order it by a Fisher–Yates shuffle driven only by the basic uniform float of a generator seeded with the integer value of the SHA-256 hash of the text `<seed>:<n>`, where `n` is the number of shuffles the game has already performed, using Python's `random.Random` seeded with that integer, iterating i from the last index down to 1 and swapping index i with index ⌊random()·(i+1)⌋.
- [x] **GAME-011**: When two games are created from the same loaded deck with the same seed and receive the same sequence of calls, the games shall hold identical state after every call.
- [x] **GAME-012**: The service shall never include the order of a game's library, or the identity of a library card that has not been drawn, fetched or revealed, in any tool response or record.

## Naming cards

- [x] **GAME-013**: When a tool argument names a card, the game shall accept the card's full name, the name of one of its faces, or an instance id, ignoring letter case.
- [x] **GAME-014**: When a card name matches several instances in the zone an operation expects, the game shall choose an untapped instance for tapping or paying and a tapped instance for untapping, and otherwise the instance with the lowest instance id.
- [x] **GAME-015**: When the instances matching a card name differ in tapped state, counters or face, the outcome shall identify the chosen instance by its instance id.
- [x] **GAME-016**: If a card name matches nothing in the zone an operation expects, then the operation shall return an error, which names the zone holding that card when the card exists in a different zone.
- [x] **GAME-017**: When a card name appears more than once in one list argument, or alongside instance ids of matching cards, the game shall resolve instance ids first and then each appearance of a name to a different instance not already named.
- [x] **GAME-018**: If a card name appears in one list argument more times than there are matching instances, or an instance id appears twice in one list argument, then the operation shall return an error.
- [x] **GAME-019**: When a tool argument is a map keyed by card, the game shall accept an instance id as a key in the same way as a card name.
- [x] **GAME-020**: When a card leaves the battlefield, the game shall set that card to its first face.

## Mulligan

- [x] **GAME-021**: When `mulligan` is called with `keep` false, the game shall return the hand to the library, shuffle the library, deal seven cards, and increase its mulligan count by one.
- [x] **GAME-022**: When `mulligan` is called with `keep` true after `k` mulligans, the game shall require `bottom` to name exactly `max(0, k − 1)` cards, capped at seven.
- [x] **GAME-023**: When `mulligan` is called with `keep` true and a valid `bottom`, the game shall put the named cards from the hand on the bottom of the library in the order given.
- [x] **GAME-024**: If `mulligan` is called with `keep` true and `bottom` names a different number of cards than required and no `override` is given, then `mulligan` shall fail a rule check and change nothing.
- [x] **GAME-025**: When `mulligan` is called with `keep` true, a `bottom` of the wrong size and an `override` reason, the game shall bottom the cards named and keep.
- [x] **GAME-026**: If `mulligan` is called with `bottom` naming a card not in hand, or with `bottom` given while `keep` is false, then `mulligan` shall return an error and change nothing.
- [x] **GAME-027**: When the agent keeps, the game shall set its status to `active` and proceed through the untap, upkeep and draw steps of turn 1 to `main1`, performing each step's automatic action.
- [x] **GAME-028**: When the agent keeps, the outcome shall show any card drawn in the turn 1 draw step.

## State on request

- [x] **GAME-029**: When `get_state` is called with `detail` omitted or `summary`, the outcome shall list the hand, the battlefield, the graveyard, the command zone and current notices.
- [x] **GAME-030**: When `get_state` lists the battlefield, the outcome shall show for each permanent its instance id, tapped state, counters, the mana the service has read it as making, haste or vigilance it has or is granted, and the steps it has a trigger in.
- [x] **GAME-031**: When `get_state` is called with `detail` `full`, the outcome shall additionally list exile, the number of cards in the library, each commander's cast count and damage, and the payments made this turn.
- [x] **GAME-032**: `get_state` shall never change a game or its change number.

## The change number

- [x] **GAME-033**: When a changing call is accepted, the game shall increase its change number by one and remember that call's tool, arguments, summary and events as its most recent change.
- [x] **GAME-034**: When a call is refused, the game shall leave its change number unchanged.
- [x] **GAME-035**: When a changing call gives `after` equal to the game's change number, or gives no `after`, the game shall apply the call.
- [x] **GAME-036**: When a changing call gives `after` one less than the game's change number and its tool and arguments other than `after` equal those of the game's most recent change, the game shall not apply the call and the outcome shall carry the most recent change's summary and events with an added statement that the call was already applied.
- [x] **GAME-037**: If a changing call gives an `after` that neither equals the game's change number nor identifies a resend of the most recent change, then the call shall return an error stating the game's current change number and change nothing.

## Notices

- [x] **GAME-038**: When `damage_dealt` first reaches 120 or more, the game shall raise the damage notice.
- [x] **GAME-039**: When, for each of the three opponents, some single commander has dealt 21 or more damage to that opponent, the game shall raise the commander damage notice.
- [x] **GAME-040**: When the game enters the turn whose number equals `turn_limit`, the game shall raise the turn limit notice.
- [x] **GAME-041**: When the agent's life first reaches 0 or less, the game shall raise the life notice.
- [x] **GAME-042**: When a draw is attempted with fewer cards in the library than the draw calls for, the game shall draw the cards that are there and raise the empty library notice.
- [x] **GAME-043**: While a game has a raised notice, every outcome about that game shall include the notice, including after the notice's condition stops holding.
- [x] **GAME-044**: The game shall never change its status or refuse a call because a notice has been raised.

## Ending

- [x] **GAME-045**: When `end_game` is called with a `result` of `win`, `loss` or `stalled`, the game shall set its status to `ended` and record the result and the agent's notes, without requiring any end condition.
- [x] **GAME-046**: When `end_game` is called, the game shall discard any pending choice and any declared attack.
- [x] **GAME-047**: If `end_game` is called with a `result` other than `win`, `loss` or `stalled`, then `end_game` shall return an error and change nothing.

## Status

- [x] **GAME-048**: While a game's status is `mulligan`, the game shall accept only `mulligan`, `get_state`, `get_log` and `end_game`.
- [x] **GAME-049**: While a game's status is `active`, the game shall accept every game tool except `mulligan` and `choose`.
- [x] **GAME-050**: While a game's status is `pending_choice`, the game shall accept only `choose`, `get_state`, `get_log` and `end_game`.
- [x] **GAME-051**: While a game's status is `ended`, the game shall accept only `get_state` and `get_log`.
- [x] **GAME-052**: If a tool is called while the game's status does not accept it, and the call is not a resend of the game's most recent change, then the call shall return an error naming the status and the tools that are accepted.
- [x] **GAME-053**: If a game tool is called with a game id that names no game, then the call shall return an error and change nothing.
- [x] **GAME-054**: When a changing call is a resend of the game's most recent change, the game shall answer it as a resend even when the game's status no longer accepts that tool.
