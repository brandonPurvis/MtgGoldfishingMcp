# Game — Specs

Design: `game-design.md`. Prefix: `GAME`.

## Creating a game

- [x] **GAME-001**: When `new_game` is called with a known deck id, no `opponents` and no `starting_life`, a goldfish game shall be created with one seat, the tested seat, holding its commanders in the command zone, every other card in its library, life 40, and with status `mulligan`, turn 0 and no step.
- [x] **GAME-002**: When a goldfish game is created, the game shall assign instance ids `c1`, `c2`, … to the tested seat's commanders first and then to its remaining cards, each group ordered by lower-cased card name compared character by character, with copies of one card adjacent.
- [x] **GAME-003**: When a goldfish game is created, the game shall shuffle the tested seat's library and deal seven cards to its hand.
- [x] **GAME-004**: When `new_game` is called without a seed, for a goldfish game or a contested game, the use case shall obtain a seed from the id source, and the outcome shall state the seed used.
- [x] **GAME-005**: When `new_game` creates a goldfish game, the outcome shall state the game id, the seed and the cards in the opening hand.
- [x] **GAME-006**: In every game, goldfish or contested, the game id shall be `g` followed by ten random characters obtained from the id source.
- [x] **GAME-007**: If `new_game` is called with a `deck_id` that names no loaded deck, then `new_game` shall return an error and create nothing, whether or not `opponents` is given.
- [x] **GAME-008**: If `new_game` is called with a `turn_limit` that is not a positive integer, then `new_game` shall return an error and create nothing, whether or not `opponents` is given.
- [x] **GAME-009**: When `new_game` is called without `draw_first_turn`, the game, goldfish or contested, shall be created with `draw_first_turn` true.
- [x] **GAME-055**: When `new_game` is called with `opponents` omitted or empty, the game created shall be a goldfish game: one seat, the tested seat, with seat number 1, against three imaginary opponents.
- [x] **GAME-056**: When `new_game` is called with `opponents` naming one, two or three loaded deck ids, the game created shall be a contested game with the tested seat on `deck_id`, one opposing seat for each entry of `opponents`, and no imaginary opponents.
- [x] **GAME-057**: When `new_game` is called with `opponents`, the game shall accept the same loaded deck id for more than one opposing seat and shall accept the tested seat's own `deck_id` as an opposing seat's deck.
- [x] **GAME-058**: If `new_game` is called with more than three entries in `opponents`, then `new_game` shall return an error and create nothing.
- [x] **GAME-059**: If `new_game` is called with an entry of `opponents` that names no loaded deck, then `new_game` shall return an error and create nothing.
- [x] **GAME-060**: When a contested game is created, each seat shall hold its own commanders in the command zone and every other card of its deck in its own library, and the game shall have status `mulligan`, table turn 0, round 0, no step and no active seat.
- [x] **GAME-061**: In every game, each seat shall have its own hand, library, graveyard, exile, command zone, life total, mana pool, land drops used, commander cast counts and mulligan count, none of them shared with another seat.
- [x] **GAME-062**: When a contested game is created, the game shall assign instance ids `c1`, `c2`, … seat by seat, the tested seat first and then the opposing seats in the order `opponents` lists their decks, and within each seat to commanders first and then to the remaining cards, each group ordered by lower-cased card name compared character by character, with copies of one card adjacent.
- [x] **GAME-063**: When a goldfish game and a contested game are created with the same `deck_id`, the tested seat's cards shall have the same instance ids in both games.
- [x] **GAME-064**: When a token or a card from outside the game is created during a goldfish game or a contested game, the game shall give it the instance number one higher than the highest instance number ever issued in that game, counted across every seat, never reusing the number of a card that has left the game.
- [x] **GAME-065**: When a contested game is created, the game shall shuffle each seat's library and deal seven cards from it to that seat's hand.
- [x] **GAME-066**: When `new_game` is called with `starting_life` as a single number, for a goldfish game or a contested game, every seat shall start with that life total.
- [x] **GAME-067**: When `new_game` for a contested game is called with `starting_life` as a list, the tested seat shall start with the first value and each opposing seat with the following values in `opponents` order.
- [x] **GAME-068**: When `new_game` for a contested game is called without `starting_life`, every seat shall start with life 40.
- [x] **GAME-069**: If `new_game` for a contested game is called with a `starting_life` list whose length is not the number of seats, then `new_game` shall return an error and create nothing.
- [x] **GAME-070**: If `new_game` is called with a `starting_life` value below 1, as a single number or as an entry of a list, then `new_game` shall return an error and create nothing.
- [x] **GAME-071**: If `new_game` for a goldfish game (no opposing seats) is called with `starting_life` as a list, then `new_game` shall return an error and create nothing.
- [x] **GAME-072**: If `new_game` for a goldfish game (no opposing seats) is called with `position`, then `new_game` shall return an error and create nothing.
- [x] **GAME-073**: If `new_game` for a contested game is called with a `position` outside 1 to the number of seats, then `new_game` shall return an error and create nothing.
- [x] **GAME-074**: When `new_game` creates a contested game, the outcome shall state the seed and list, in turn order, each seat's seat number, seat id, deck id, starting life and whether it is the tested seat.
- [x] **GAME-075**: When `new_game` creates a contested game, the outcome shall show no seat's hand.

## Seat ids, seat numbers and turn order

- [x] **GAME-076**: In every game, goldfish or contested, the tested seat's seat id shall be the game id.
- [x] **GAME-077**: When a contested game is created, each opposing seat shall receive its own random, unguessable seat id of the same format as a game id (`g` followed by ten random characters), obtained from the same id source as the game id and different from the game id and from every other seat's seat id.
- [x] **GAME-078**: When a game tool is called with a seat id, the game shall apply the call as that seat and show only what that seat may see.
- [x] **GAME-079**: In every game, a seat's seat number shall be its place in turn order counted from 1, and outcomes shall name seats to one another by seat number (`S2`), never by seat id.
- [x] **GAME-080**: When a contested game is created without `position`, the game shall set turn order by a Fisher–Yates shuffle (the same walk as a library shuffle: i from the last index down to 1, swapping index i with index ⌊random()·(i+1)⌋) of the list holding the tested seat followed by the opposing seats in `opponents` order, driven by a `random.Random` generator seeded with the integer value of the SHA-256 hash of the text `<seed>:order`.
- [x] **GAME-081**: When a contested game is created with `position`, the game shall shuffle only the opposing seats, in `opponents` order, with the generator seeded from `<seed>:order`, and place the tested seat at seat number `position` with the opposing seats filling the remaining places in their shuffled order.
- [x] **GAME-082**: When two contested games are created with the same `deck_id`, the same `opponents`, the same `position` and the same seed, the two games shall have the same turn order and the same opening hand for every seat.

## Shuffling and hidden information

- [x] **GAME-010**: When the tested seat's library is shuffled, in a goldfish game or a contested game, the game shall order it by a Fisher–Yates shuffle driven only by the basic uniform float of a generator seeded with the integer value of the SHA-256 hash of the text `<seed>:<n>`, where `n` is the number of shuffles of the tested seat's library already performed, using Python's `random.Random` seeded with that integer, iterating i from the last index down to 1 and swapping index i with index ⌊random()·(i+1)⌋.
- [x] **GAME-011**: When two goldfish games are created from the same loaded deck with the same seed and receive the same sequence of calls, the games shall hold identical state after every call.
- [x] **GAME-012**: In every game, the service shall never include the order of any seat's library, or the identity of a library card that has not been drawn, fetched or revealed, in any tool response or record.
- [x] **GAME-083**: When an opposing seat's library is shuffled in a contested game, the game shall order it by the same Fisher–Yates shuffle as the tested seat's, with the generator seeded with the integer value of the SHA-256 hash of the text `<seed>:<shuffle_key>:<n>`, where `shuffle_key` is `o1`, `o2` or `o3` for the first, second or third entry of `opponents` and `n` is the number of shuffles of that seat's own library already performed.
- [x] **GAME-084**: In every game, a seat's library shall be in ascending order of instance number (`c2` before `c10`) before that seat's first shuffle.
- [x] **GAME-085**: In a contested game, a shuffle of one seat's library shall not change the result of any other seat's shuffles: each seat counts its own shuffles and no other seat's.
- [x] **GAME-086**: When a goldfish game and a contested game are created with the same `deck_id` and the same seed, the tested seat's opening hand and the order of its library shall be the same in both games.
- [x] **GAME-087**: When two contested games are created with the same `deck_id`, `opponents`, `position` and seed and receive the same sequence of calls from the same seats, the games shall hold identical state after every call.

## What a seat may see

- [x] **GAME-088**: In a contested game, every outcome to a seat other than a `get_log` response, and its `get_state`, shall show the cards in that seat's own hand and shall never show the cards in another seat's hand.
- [x] **GAME-089**: In a contested game, every outcome to a seat and its `get_state` may show any seat's battlefield, graveyard, exile and command zone, the stack, each seat's life, hand size and library size, commander damage, and which seats are eliminated.
- [x] **GAME-090**: In a contested game, cards revealed by a pending choice (a look, a search or a look at a hand) shall be shown only to the seat the pending choice is addressed to.
- [x] **GAME-091**: In a contested game, the public form of an event that moves a card from one hidden zone (hand or library) to a hidden zone, without the card being revealed, shall give the seat and a count and not the card's name (`S2 drew 2 cards`, `S3 put a card into its hand`).
- [x] **GAME-168**: In a contested game, the public form of an event that moves a card from a public zone or the stack into a hidden zone (a permanent returned to its owner's hand, a graveyard card shuffled into a library) shall name the card, every seat having been able to see it before the move.
- [x] **GAME-092**: In a contested game, the public form of an event that moves a card from a hidden zone (hand or library) into a public zone or onto the stack shall name the card.
- [x] **GAME-093**: In a contested game, the public form of a `mulligan` with `keep` true shall give the number of cards the seat kept and the number it put on the bottom, and not their names.
- [x] **GAME-094**: In a contested game, the public form of a pending choice shall give its kind, the seat it is addressed to and, for a `hand` pending choice, the seat whose hand is shown, and not the cards it revealed.
- [x] **GAME-095**: In a contested game, an outcome to a seat other than a `get_log` response shall show an event that moves a card into, between or out of another seat's hidden zones (hand or library) only in its public form, whichever seat's call caused the event.
- [x] **GAME-152**: In a contested game, the limits on what a seat may see shall not apply to `get_log`, whose response holds every seat's hidden-zone content for any seat that calls it, while the game is running and after it has ended.
- [x] **GAME-153**: In a contested game, the public form of a `mulligan` with `keep` false shall give the seat and the number of mulligans it has now taken, and not the cards of either hand.
- [x] **GAME-154**: In a contested game, an event that moves a card into, between or out of a seat's own hidden zones (hand or library) shall be shown to that seat with the card's name, whichever seat's call caused the event.

## Naming cards

- [x] **GAME-013**: When a tool argument names a card, in a goldfish game or a contested game, the game shall accept the card's full name, the name of one of its faces, or an instance id, ignoring letter case.
- [x] **GAME-014**: When a card name matches several instances in the zone an operation expects, in a goldfish game or among one seat's cards in a contested game, the game shall choose an untapped instance for tapping or paying and a tapped instance for untapping, and otherwise the instance with the lowest instance id.
- [x] **GAME-015**: When the instances matching a card name differ in tapped state, counters or face, in a goldfish game or a contested game, the outcome shall identify the chosen instance by its instance id.
- [x] **GAME-016**: If a card name matches nothing in the zone an operation expects, in a goldfish game or a contested game, then the operation shall return an error, which names the zone holding that card when the card exists in a different zone that the acting seat may see (a public zone, the stack, or the acting seat's own hand or library).
- [x] **GAME-017**: When a card name appears more than once in one list argument, or alongside instance ids of matching cards, in a goldfish game or a contested game, the game shall resolve instance ids first and then each appearance of a name to a different instance not already named.
- [x] **GAME-018**: If a card name appears in one list argument more times than there are matching instances, or an instance id appears twice in one list argument, in a goldfish game or a contested game, then the operation shall return an error.
- [x] **GAME-019**: When a tool argument is a map keyed by card, in a goldfish game or a contested game, the game shall accept an instance id as a key in the same way as a card name.
- [x] **GAME-020**: When a card leaves the battlefield, in a goldfish game or a contested game, the game shall set that card to its first face.
- [x] **GAME-096**: In a contested game, when a card name is given for a card in a hidden zone (hand or library) anywhere but in the `selections` of a pending choice, the game shall resolve it only among the acting seat's own cards.
- [x] **GAME-155**: In a contested game, when the `selections` of a `look`, `search` or `hand` pending choice give a card name, the game shall resolve it among the cards that pending choice revealed, whichever seat owns them.
- [x] **GAME-156**: If a card name given in a contested game matches no card in the zones the acting seat may see (every public zone, the stack, and its own hand and library), then the error shall be the same whether or not a card of that name is in another seat's hand or library.
- [x] **GAME-157**: If an instance id given in a contested game names a card in another seat's hand or library, outside the `selections` of a pending choice that revealed that card, then the call shall return an error that says the card is in a hidden zone of that seat, by seat number, and does not say whether that zone is its hand or its library.
- [x] **GAME-097**: In a contested game, when a card name is given for a card in a public zone or on the stack, the game shall resolve it, within the one zone the operation is looking in, among the cards the acting seat controls before any other seat's, and then among the other seats' cards seat by seat in turn order starting from the seat after the acting seat (an operation that looks in several zones takes them in its own order first, PLAY-087), applying the choice among several matching instances (untapped for tapping or paying, tapped for untapping, then lowest instance id) only within the first seat that has a match.
- [x] **GAME-098**: In a contested game, an instance id given in a tool argument shall name that card instance whichever seat owns or controls it, subject to the zone the operation expects.
- [x] **GAME-099**: In a contested game, when the instances matching a card name differ in controller, the outcome shall identify the chosen instance by its instance id.
- [x] **GAME-100**: In every game, the game shall record each card instance's owner and controller separately, the controller being the owner unless a delta has changed control.
- [x] **GAME-101**: When a card leaves the battlefield in a contested game, the game shall set that card's controller to its owner.
- [x] **GAME-171**: In every game, goldfish or contested, the game shall read each card instance that is not a token and carries no card data of its own — its names, type line, mana cost, power and readings (mana abilities, haste, vigilance, flash, step triggers, entering tapped) — from the loaded deck of its owner, whichever seat controls it.

## Mulligan

- [x] **GAME-021**: When a seat calls `mulligan` with `keep` false, in a goldfish game or a contested game, the game shall return that seat's hand to its library, shuffle that library, deal that seat seven cards, and increase that seat's mulligan count by one.
- [x] **GAME-151**: When a seat calls `mulligan` with `keep` false, in a goldfish game or a contested game, the game shall put the cards of that seat's hand on the bottom of its library in ascending order of instance number, leaving the cards already in the library in the order they hold, before it shuffles that library.
- [x] **GAME-022**: When a seat calls `mulligan` with `keep` true after `k` mulligans of its own, in a goldfish game or a contested game, the game shall require `bottom` to name exactly `max(0, k − 1)` cards, capped at seven.
- [x] **GAME-023**: When a seat calls `mulligan` with `keep` true and a valid `bottom`, in a goldfish game or a contested game, the game shall put the named cards from that seat's hand on the bottom of that seat's library in the order given.
- [x] **GAME-024**: If a seat calls `mulligan` with `keep` true and `bottom` names a different number of cards than required and no `override` is given, in a goldfish game or a contested game, then `mulligan` shall fail a rule check and change nothing.
- [x] **GAME-025**: When a seat calls `mulligan` with `keep` true, a `bottom` of the wrong size and an `override` reason, in a goldfish game or a contested game, the game shall bottom the cards named and that seat shall keep.
- [x] **GAME-026**: If a seat calls `mulligan` with `bottom` naming a card not in that seat's hand, or with `bottom` given while `keep` is false, in a goldfish game or a contested game, then `mulligan` shall return an error and change nothing.
- [x] **GAME-027**: When the tested seat keeps in a goldfish game, the game shall set its status to `active` and proceed through the untap, upkeep and draw steps of turn 1 to `main1`, performing each step's automatic action.
- [x] **GAME-028**: When the tested seat keeps in a goldfish game, the outcome shall show any card drawn in the turn 1 draw step.
- [x] **GAME-102**: While a contested game's status is `mulligan`, the game shall accept `mulligan` from every seat that has not kept, in any order among the seats.
- [x] **GAME-103**: When a seat calls `mulligan` in a contested game, the game shall change only that seat's hand, library, mulligan count and kept state.
- [x] **GAME-104**: If a seat that has already kept calls `mulligan` in a contested game, then `mulligan` shall return an error and change nothing.
- [x] **GAME-105**: When a seat keeps in a contested game while another seat has not kept, the game shall stay in status `mulligan` with no active seat and no step.
- [x] **GAME-106**: When the last seat still in the game that had not kept keeps in a contested game, the game shall set its status to `active`, make the first seat in turn order that is still in the game the active seat, and proceed through that seat's untap, upkeep and draw steps to its `main1` exactly as an `advance` to `main1` would, stopping where a reminder stops it.
- [x] **GAME-107**: When the last seat to keep keeps in a contested game, the outcome shall show what the start of the first turn did, and shall name the card the first seat drew only when the calling seat is the seat that drew it.
- [x] **GAME-158**: While a contested game's status is `mulligan`, the game shall accept `end_game` from an opposing seat as its concession and eliminate that seat, whether or not it has kept.
- [x] **GAME-159**: When a concession during status `mulligan` leaves no seat still in the game that has not kept, the game shall start within the conceding call exactly as it does when the last seat keeps (GAME-106).

## The seat to act

- [x] **GAME-108**: While a contested game's status is `mulligan`, the seats to act shall be every seat still in the game (not eliminated) that has not kept.
- [x] **GAME-109**: While a pending choice waits in a contested game that has left status `mulligan`, the seat to act shall be the seat that the oldest waiting pending choice is addressed to, ahead of any waiting reminder, open response window or the active seat.
- [x] **GAME-111**: While no pending choice waits and a reminder waits for a seat other than the active seat in a contested game, the seat to act shall be that reminded seat, ahead of any open response window and the active seat.
- [x] **GAME-112**: While no pending choice and no reminder for a seat other than the active seat waits and a response window is open in a contested game, the seat to act shall be the seat the window is asking.
- [x] **GAME-113**: While a started contested game has no waiting pending choice, no waiting reminder for a seat other than the active seat and no open response window, the seat to act shall be the active seat.
- [x] **GAME-114**: In a contested game, the game shall accept `get_state`, `get_log` and `wait` from any seat in any status, including an eliminated seat and a seat that is not the seat to act.
- [x] **GAME-115**: In a contested game, the game shall accept `choose` only from the seat that the oldest waiting pending choice is addressed to.
- [x] **GAME-116**: In a contested game, the game shall accept `play`, `effect` and `pass` from a seat other than the active seat only while that seat is the seat to act because a response window is asking it or a reminder waits for it.
- [x] **GAME-117**: In a contested game, the game shall accept `play` and `effect` from the active seat only while the active seat is the seat to act, and `attack` and `advance` from it only while it is the seat to act, no response window is open and the stack is empty.
- [x] **GAME-118**: If a seat of a contested game makes a call the game does not accept from it at that moment, and the call is not a resend of that seat's most recent accepted change, then the call shall return an error that names the seat to act by seat number and says what that seat is being asked, and shall change nothing.
- [x] **GAME-119**: If an eliminated seat of a contested game calls any game tool other than `get_state`, `get_log`, `wait` or, for the tested seat, `end_game`, then the call shall return an error and change nothing.
- [x] **GAME-120**: While any pending choice waits in a contested game, the game's status shall be `pending_choice`.

## State on request

- [x] **GAME-029**: When `get_state` is called in a goldfish game with `detail` omitted or `summary`, the outcome shall list the hand, the battlefield, the graveyard, the command zone and current notices.
- [x] **GAME-030**: When `get_state` lists the battlefield in a goldfish game, the outcome shall show for each permanent its instance id, tapped state, counters, the mana the service has read it as making, haste or vigilance it has or is granted, and the steps it has a trigger in, leaving out triggers read as happening only on opponents' turns.
- [x] **GAME-031**: When `get_state` is called in a goldfish game with `detail` `full`, the outcome shall additionally list exile, the number of cards in the library, each commander's cast count and damage, and the payments made this turn.
- [x] **GAME-032**: `get_state` shall never change a game or its change number, in a goldfish game or a contested game, whichever seat calls it.
- [x] **GAME-121**: When a seat calls `get_state` in a contested game with `detail` omitted or `summary`, the outcome shall list the calling seat's hand, then for each seat in turn order that seat's battlefield (the permanents it controls, whichever seat owns them), graveyard and command zone, and current notices.
- [x] **GAME-122**: When a seat calls `get_state` in a contested game, the outcome shall show the stack, the open response window with the seat being asked, each seat's life, hand size and library size, and which seats are eliminated.
- [x] **GAME-123**: When `get_state` lists a battlefield in a contested game, the outcome shall show for each permanent its instance id, tapped state, counters, the mana the service has read it as making, haste or vigilance it has or is granted, and the steps it has a trigger in, with a trigger read as happening only on opponents' turns marked `(opp)` and a trigger read as happening on its controller's turn or on each turn left unmarked.
- [x] **GAME-124**: When `get_state` lists a permanent in a contested game whose controller is not its owner, the outcome shall name its owner by seat number beside it, on the battlefield of the seat that controls it.
- [x] **GAME-125**: When a seat calls `get_state` in a contested game with `detail` `full`, the outcome shall additionally list every seat's exile, per-commander cast counts and per-commander damage to each seat, and the calling seat's payments this turn.
- [x] **GAME-172**: When a seat calls `get_state` in a contested game, the outcome shall list each pending choice addressed to that seat, in the order the pending choices will be answered, with its choice id and kind.
- [x] **GAME-173**: When `get_state` in a contested game lists a pending choice of kind `look`, `search` or `hand`, the outcome shall show each card that choice revealed by name and instance id.
- [x] **GAME-174**: When `get_state` in a contested game lists a pending choice of kind `ask`, the outcome shall show the text it asks and the seat whose effect asked it.
- [x] **GAME-175**: When `get_state` in a contested game lists a pending choice of kind `blocks`, the outcome shall show each attacker it may block by name and instance id.
- [x] **GAME-176**: When `get_state` in a contested game lists a pending choice of kind `resolve`, the outcome shall show the stack item's id and source, its held delta and destination, and the error that kept it from resolving as held, if any.
- [x] **GAME-177**: When a seat calls `get_state` in a contested game, the outcome shall list no pending choice addressed to another seat.
- [x] **GAME-178**: When `get_state` is called in a goldfish game, the outcome shall list no pending choice.

## The change number

- [x] **GAME-033**: When a changing call is accepted, in a goldfish game or a contested game, the game shall increase its one change number by one, whichever seat made the call, and remember that call's tool, arguments, summary and events as the calling seat's most recent change.
- [x] **GAME-034**: When a call is refused, in a goldfish game or a contested game, the game shall leave its change number unchanged.
- [x] **GAME-035**: When a changing call gives `after` equal to the game's change number, or gives no `after`, in a goldfish game or a contested game, the game shall apply the call.
- [x] **GAME-036**: When a changing call's tool and arguments other than `after` equal those of the calling seat's most recent accepted change and its `after` is one less than that change's number, in a goldfish game or a contested game, the game shall not apply the call and the outcome shall carry that change's summary and events with an added statement that the call was already applied.
- [x] **GAME-037**: If a changing call gives an `after` that neither equals the game's change number nor identifies a resend of the calling seat's most recent accepted change, in a goldfish game or a contested game, then the call shall return an error stating the game's current change number and change nothing.
- [x] **GAME-126**: When a seat of a contested game repeats its most recent accepted change with `after` one less than that change's number after other seats have made accepted changes, the game shall answer the call as a resend of that seat's change and not apply it again.
- [x] **GAME-127**: If a seat of a contested game makes a changing call whose tool and arguments equal another seat's most recent accepted change but not its own, with an `after` that is not the game's change number, then the call shall return an error stating the game's current change number.

## Life, elimination and conceding

- [x] **GAME-128**: In a contested game, the game shall check every seat still in the game for elimination each time one delta has been applied in full (a delta applied at once, the delta of each stack item as it resolves, the delta of each `choose` answer), each time the damage of one combat has been applied in full, and when a seat concedes, so that a call that resolves several stack items checks after each of them.
- [x] **GAME-160**: In a contested game, the game shall not check for elimination between the keys of one delta or between the attackers of one combat's damage: a seat whose life is 0 or less partway through a delta and above 0 once the whole delta is applied is not eliminated.
- [x] **GAME-129**: When a seat's life is 0 or less in a contested game, the game shall eliminate that seat.
- [x] **GAME-130**: When one commander has dealt 21 or more combat damage to a seat in a contested game, the game shall eliminate that seat.
- [x] **GAME-131**: When an opposing seat still in a contested game calls `end_game` with a `result` of `win`, `loss` or `stalled`, the game shall eliminate that seat (it concedes), record its `notes`, and leave the game's status and result unchanged.
- [x] **GAME-161**: In a contested game, the game shall accept the conceding `end_game` of an opposing seat still in the game whichever seat is the seat to act and whatever the game is waiting on, including a pending choice, a reminder or a response window that waits on the conceding seat itself.
- [x] **GAME-132**: When a seat is eliminated in a contested game, every card that seat owns shall leave the game, being removed from every zone, including the battlefields of seats that control it and the stack.
- [x] **GAME-133**: When a seat is eliminated in a contested game, every permanent it controls but does not own shall return to its owner's control.
- [x] **GAME-135**: When a seat is eliminated in a contested game, every pending choice addressed to it shall be discarded.
- [x] **GAME-162**: When a seat is eliminated in a contested game, every pending choice of kind `ask` that its effect addressed to another seat (its `asked_by` is the eliminated seat) shall stay waiting and be answered by the seat it is addressed to.
- [x] **GAME-163**: When a seat is eliminated in a contested game, every pending choice of kind `hand` that shows that seat's hand (its `hand_of` is the eliminated seat) shall be discarded.
- [x] **GAME-136**: While a seat of a contested game is eliminated, the game shall never make it the active seat.
- [x] **GAME-164**: While no seat of a contested game is still in the game (every seat eliminated), the game shall keep its status and have no active seat and no seat to act.
- [x] **GAME-167**: While no seat of a contested game is still in the game (every seat eliminated), the game shall accept only `get_state`, `get_log`, `wait` and the tested seat's `end_game`, and shall answer any other call that is not a resend with an error.
- [x] **GAME-138**: When a call causes a seat's elimination in a contested game, the outcome of that call shall say which seat was eliminated and why (life, commander damage or conceding).
- [x] **GAME-169**: When a seat eliminated in a contested game has both life 0 or less and 21 or more combat damage from one commander at the same check, the outcome shall give life as the reason, as the log entry does (REC-077).
- [x] **GAME-139**: When several seats meet an elimination condition at the same check in a contested game, the game shall apply their eliminations one seat at a time in turn order starting from the active seat.
- [x] **GAME-140**: In a goldfish game, the game shall never eliminate the tested seat.
- [x] **GAME-141**: In a contested game, the game shall not eliminate a seat for attempting to draw from a library with too few cards.

## Notices

- [x] **GAME-038**: When the pooled damage dealt to the imaginary opponents of a goldfish game (`damage_dealt`) first reaches 120 or more, the game shall raise the damage notice.
- [x] **GAME-039**: When, for each of the three imaginary opponents of a goldfish game, some single commander has dealt 21 or more damage to that opponent, the game shall raise the commander damage notice.
- [x] **GAME-040**: When a goldfish game enters the turn whose number equals `turn_limit`, the game shall raise the turn limit notice.
- [x] **GAME-041**: When the tested seat's life in a goldfish game first reaches 0 or less, the game shall raise the life notice.
- [x] **GAME-042**: When a seat attempts a draw with fewer cards in its library than the draw calls for, in a goldfish game or a contested game, the game shall draw the cards that are there and raise the empty library notice.
- [x] **GAME-043**: While a game, goldfish or contested, has a raised notice, every outcome about that game to every seat shall include the notice, including after the notice's condition stops holding.
- [x] **GAME-044**: The game, goldfish or contested, shall never change its status or refuse a call because a notice has been raised.
- [x] **GAME-142**: When the tested seat of a contested game is eliminated, the game shall raise the tested-seat-eliminated notice.
- [x] **GAME-143**: When every opposing seat of a contested game has been eliminated, the game shall raise the opponents-eliminated notice.
- [x] **GAME-144**: When a contested game first enters a turn of the round whose number equals `turn_limit`, the game shall raise the turn limit notice.
- [x] **GAME-145**: When a seat of a contested game first attempts a draw with fewer cards in its library than the draw calls for, the game shall raise an empty library notice of that seat's own, naming the seat by seat number, whether or not another seat's empty library notice is already raised.
- [x] **GAME-165**: In a contested game, the game shall raise the empty library notice at most once for each seat, however many times that seat attempts a draw with too few cards.
- [x] **GAME-146**: In a contested game, the game shall not raise the damage notice (120 pooled damage), the commander damage notice (21 to each of three imaginary opponents) or the life notice, which belong to goldfish games only.

## Ending

- [x] **GAME-045**: When the tested seat calls `end_game` with a `result` of `win`, `loss` or `stalled`, in a goldfish game or a contested game, the game shall set its status to `ended` and record the result and the agent's notes, without requiring any end condition.
- [x] **GAME-046**: When the tested seat calls `end_game`, in a goldfish game or a contested game, the game shall discard every pending choice and any declared attack.
- [x] **GAME-047**: If `end_game` is called with a `result` other than `win`, `loss` or `stalled`, by any seat of a goldfish game or a contested game, then `end_game` shall return an error and change nothing.
- [x] **GAME-147**: When the tested seat of a contested game calls `end_game`, the game shall discard any open response window and every stack item.
- [x] **GAME-148**: When the tested seat of a contested game calls `end_game` while the game's status is not `ended`, the game shall accept the call whichever seat is the seat to act and whatever the game is waiting on: mulligans, a pending choice, a reminder or a response window.
- [x] **GAME-149**: When the tested seat of a contested game calls `end_game` after it has been eliminated, the game shall accept the call and end the game.
- [x] **GAME-150**: While a contested game's status is `ended`, the game shall accept only `get_state`, `get_log` and `wait`, and shall answer any other call that is not a resend with an error.
- [x] **GAME-170**: If a call to a contested game that is not a resend is refused for more than one of these reasons, then the error returned shall be the first that applies of: the game has ended (GAME-150); the calling seat is eliminated (GAME-119); the calling seat is not the seat to act for that call (GAME-118).

## Status

- [x] **GAME-048**: While a goldfish game's status is `mulligan`, the game shall accept `mulligan`, `get_state`, `get_log` and `end_game`, and of the remaining game tools none but `wait`.
- [x] **GAME-049**: While a goldfish game's status is `active`, the game shall accept every game tool except `mulligan`, `choose` and `pass`.
- [x] **GAME-050**: While a goldfish game's status is `pending_choice`, the game shall accept `choose`, `get_state`, `get_log` and `end_game`, and of the remaining game tools none but `wait`.
- [x] **GAME-051**: While a goldfish game's status is `ended`, the game shall accept `get_state` and `get_log`, and of the remaining game tools none but `wait`.
- [x] **GAME-052**: If a tool is called in a goldfish game while the game's status does not accept it, and the call is not a resend of the game's most recent change, then the call shall return an error naming the status and the tools that are accepted.
- [x] **GAME-053**: If a game tool is called with an id that is neither the game id of a game nor the seat id of a seat, then the call shall return an error and change nothing.
- [x] **GAME-054**: When a changing call is a resend of the calling seat's most recent accepted change, in a goldfish game or a contested game, the game shall answer it as a resend even when the game's status or its seat to act no longer accepts that tool from that seat.
