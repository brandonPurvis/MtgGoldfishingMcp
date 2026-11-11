# Stack — Specs

Design: `stack-design.md`. Prefix: `STACK`.

## Goldfish games

- [x] **STACK-001**: In a goldfish game, the game shall keep its stack empty and open no response window, applying every `play` and `effect` at once.
- [x] **STACK-002**: If `pass` is called in a goldfish game, then `pass` shall return an error.

## Putting items on the stack

- [x] **STACK-003**: In a contested game, when a `play` of a card whose played face is not a land is applied, the game shall put a stack item of kind `spell` on top of the stack, holding the acting seat's number as its controller and the call's delta, `to` and `choices` as stated, without applying the delta.
- [x] **STACK-004**: In a contested game, when a `play` puts a spell on the stack, the game shall pay the spell's cost when the call is applied, not when the spell resolves.
- [x] **STACK-005**: In a contested game, when a `play` from the command zone puts a commander on the stack, the game shall count the commander tax and increase that commander's cast count when the call is applied, not when the spell resolves.
- [x] **STACK-006**: In a contested game, when a `play` puts a spell on the stack, the game shall move the spell's card to the zone `stack`, where it stays while its stack item waits.
- [x] **STACK-007**: In a contested game, when an `effect` without `immediate: true` is applied, including one that records a triggered ability, the game shall put a stack item of kind `ability` on top of the stack, holding the acting seat's number as its controller, the call's `source` and its delta as stated, and no card, without applying the delta.
- [x] **STACK-008**: In a contested game, when an `effect` with `pay` puts an ability on the stack, the game shall pay that cost when the call is applied, not when the ability resolves.
- [x] **STACK-009**: In a contested game, when an `effect` with `immediate: true` is applied, the game shall apply its delta at once, put nothing on the stack and open no response window on account of it.
- [x] **STACK-010**: In a contested game, when an `effect` with `immediate: true` is applied while a response window is open, the game shall leave the window's seat being asked and its record of seats that have passed unchanged.
- [x] **STACK-011**: In a contested game, when a `play` plays a land, the game shall put nothing on the stack and open no response window on account of it.
- [x] **STACK-012**: In a contested game, the game shall give each stack item an id of the form `s<n>`, numbered from `s1` in the order items are put on the stack across the whole game, and shall never reuse an id.
- [x] **STACK-013**: In a contested game, each stack item shall record the tool that made it (`play` or `effect`) and its source: the card played for a spell, the call's `source` for an ability.
- [x] **STACK-064**: If a `play` or `effect` call in a contested game that would put an item on the stack carries a delta with an error that does not depend on where cards are — an unknown key, a malformed value, more than one of `look`, `search` and `look_at_hand`, a seat number that is not in the game or names an eliminated seat, or a `counter` entry that names no item then on the stack — then the call shall return that error when it is made and put nothing on the stack.
- [x] **STACK-065**: In a contested game, when a `play` or `effect` call puts an item on the stack, the game shall hold each `counter` entry of its delta as the id of the stack item the entry named when the call was applied, so that a spell's name is not matched again when the item resolves.
- [x] **STACK-066**: In a contested game, when a `play` or `effect` call puts an item on the stack, the game shall not look for the cards its delta names in `untap`, `tap`, `counters`, `control`, `move`, `discard` or `fetch` until the item resolves.

## Cast triggers

- [x] **STACK-086**: In a contested game, when a `play` that puts a spell on the stack gives cast triggers, the game shall, in the same call and after putting the spell on the stack, put above it one stack item of kind `ability` for each cast trigger, holding the casting seat's number as its controller, the trigger's `source`, `delta` and `choices` as stated, the spell's stack item id as `cast_with`, and no card, without applying the delta.
- [x] **STACK-087**: In a contested game, when a `play` puts cast triggers on the stack, the game shall put them on in reverse of the order listed, so that the first listed is the top item and resolves first, each taking the next stack item id as it goes on (STACK-012), so that the first listed holds the highest id.
- [x] **STACK-088**: In a contested game, the game shall check the `counter` entries of a cast trigger's delta (STACK-064, STACK-065) against the stack as it stands once that trigger's spell is on it and before any cast trigger of the same call is, so that an entry may name that spell or any item below it and never another cast trigger of the same call.
- [x] **STACK-089**: In a contested game, when a cast trigger resolves, whether with its held delta or with one its controller restated, the game shall not mark as disturbed the spell whose id it holds as `cast_with`, nor any other cast trigger holding the same `cast_with`.
- [x] **STACK-090**: In a contested game, when a `play` puts a spell and its cast triggers on the stack and every seat asked about each item in turn is passed automatically (STACK-035, STACK-046), with no pending choice created along the way (STACK-070), the game shall resolve within that call each cast trigger, the first listed first, and then the spell, and that call's response shall show each resolution.
- [x] **STACK-091**: In a contested game, when a spell is countered or removed from the stack, the game shall leave on the stack every cast trigger stated with it, each to resolve, be countered or be removed as any other stack item.

## Resolution

- [x] **STACK-014**: In a contested game, when every seat still in the game other than the top stack item's controller has passed in succession since that item became the top item, the game shall resolve that item.
- [x] **STACK-015**: In a contested game, when an item is put on the stack and no seat other than its controller is still in the game, the game shall resolve the item at once.
- [x] **STACK-016**: In a contested game, when a stack item of kind `spell` resolves, the game shall first move its card from the stack to its destination and then apply its delta, so that the delta can change the permanent the spell has become.
- [x] **STACK-017**: In a contested game, when a spell resolves whose stack item holds a `to`, the game shall move the spell's card to that destination, which for `hand`, `graveyard`, `exile`, `command`, `library_top` and `library_bottom` is that zone of the card's owner, whichever seat controls the item.
- [x] **STACK-080**: In a contested game, when a spell resolves whose stack item holds a `to` of `battlefield` or `battlefield_tapped`, the game shall put its card onto the battlefield under the control of the item's controller, whichever seat owns the card, with `entered_turn` set to the table turn (the game's count of turns taken by all seats, not the controller's own turn count).
- [x] **STACK-018**: In a contested game, when a spell resolves whose stack item holds no `to` and whose played face is a permanent, the game shall put its card onto the battlefield under the control of the item's controller with `entered_turn` set to the table turn (the game's count of turns taken by all seats, not the controller's own turn count).
- [x] **STACK-019**: In a contested game, when a spell resolves whose stack item holds no `to` and whose played face is an instant or sorcery, the game shall put its card into its owner's graveyard, or into its owner's command zone when the card is a commander (STACK-073).
- [x] **STACK-020**: In a contested game, when a stack item of kind `ability` resolves, the game shall apply its delta and remove the item from the stack.
- [x] **STACK-021**: In a contested game, when a stack item's delta is applied on resolution, the game shall apply it with the item's controller as the acting seat, whichever seat's call caused the resolution.
- [x] **STACK-022**: In a contested game, when a stack item's delta is applied on resolution, the game shall add everything it adds to a delta applied at once by `play`: shuffles, commander zone changes, tokens, battlefield arrival, notices, and the check of every seat for elimination once that item's delta has been applied in full and before the next item resolves or the next seat is asked (GAME-128, GAME-160).
- [x] **STACK-023**: In a contested game, when a stack item resolves, the game shall mark every item still below it on the stack as disturbed, except the items STACK-089 leaves undisturbed when the resolving item is a cast trigger.
- [x] **STACK-024**: In a contested game, when a stack item that is not disturbed reaches resolution, the game shall apply its delta as sent, without asking its controller for any further call.
- [x] **STACK-081**: In a contested game, when a stack item's delta is applied on resolution, the game shall resolve every card name and instance id in it, other than its `counter` entries, against the game as it stands at that moment, with the item's controller as the acting seat.
- [x] **STACK-072**: In a contested game, when a stack item has resolved, the game shall check every seat still in the game for elimination and apply every elimination due before it makes any further automatic pass or resolves any further item, including within the same call.
- [x] **STACK-073**: In a contested game, when a spell's card that is a commander would go from the stack to its owner's graveyard or to exile — on resolution, on being countered, or on removal because another seat was eliminated — the game shall put it in its owner's command zone instead, and the outcome shall say so.
- [x] **STACK-074**: In a contested game, when the delta that sends a commander's card from the stack to the graveyard or to exile — the resolving item's own delta, held or restated, or the delta that counters the item — sets `commander_stays`, the game shall put the card in the graveyard or exile as written.

## Confirming or restating a disturbed item

- [x] **STACK-025**: In a contested game, when a disturbed stack item (one that was on the stack when an item above it resolved) reaches resolution, the game shall not resolve it and shall instead create a pending choice of kind `resolve` addressed to the item's controller, showing the held delta and destination.
- [x] **STACK-026**: In a contested game, when the controller answers a `resolve` pending choice with `choose` and no `restate`, the game shall resolve the stack item with its held delta and destination.
- [x] **STACK-027**: In a contested game, when the controller answers a `resolve` pending choice with `choose` and `restate`, the game shall resolve the stack item with the `delta` given in `restate` in place of the held delta and the `to` given in `restate` in place of the held destination.
- [x] **STACK-028**: In a contested game, when a `restate` answering a `resolve` pending choice omits `delta` or omits `to`, the game shall use the stack item's held value for the omitted one.
- [x] **STACK-029**: In a contested game, when a spell is restated with an empty delta and `to` of `graveyard`, the game shall put the spell's card into its owner's graveyard, or into its owner's command zone when the card is a commander (STACK-073), and apply nothing else.
- [x] **STACK-067**: In a contested game, if a stack item reaches resolution and moving its card or applying its held delta would be an error (a named card that is no longer where the delta needs it, a `counter` entry whose item has left the stack, a seat that has since been eliminated), then the game shall apply no part of the item, leave it on the stack with its card, and create a pending choice of kind `resolve` addressed to the item's controller, whether or not the item is disturbed.
- [x] **STACK-068**: In a contested game, when a `resolve` pending choice is created because the held delta cannot be applied (STACK-067), the pending choice shall state the error alongside the held delta and destination.
- [x] **STACK-069**: If the answer to a `resolve` pending choice in a contested game, with or without `restate`, cannot be applied without an error, then `choose` shall return that error, leave the item on the stack and leave the pending choice waiting.
- [x] **STACK-075**: In a contested game, the game shall accept in a `restate` delta every key a stacked delta may hold, `counter`, `ask`, `look_at_hand`, `look` and `search` included, and shall not compare the restated delta with the held one.
- [x] **STACK-082**: In a contested game, when a stack item resolves with a restated delta, the game shall put no new item on the stack and open no response window on account of the restated delta.
- [x] **STACK-076**: If a `restate` answering a `resolve` pending choice in a contested game gives `to` for a stack item of kind `ability`, which has no card, then `choose` shall return an error and change nothing.

## Countering

- [x] **STACK-030**: In a contested game, when an applied delta has `counter`, the game shall find each named stack item by its stack item id or by the name of a spell's card on the stack, and remove it from the stack without applying its delta.
- [x] **STACK-031**: In a contested game, when a countered stack item is a spell and the countering delta's `move` does not name its card, the game shall put the spell's card into its owner's graveyard, or into its owner's command zone when the card is a commander (STACK-073).
- [x] **STACK-032**: In a contested game, when a countered stack item is a spell and the countering delta's `move` names its card, the game shall put the spell's card in the destination that `move` gives.
- [x] **STACK-033**: In a contested game, the game shall remove a stack item from the stack unresolved only when a delta's `counter` names it, when its controller or the owner of its card is eliminated, or when `end_game` from the tested seat ends the game.

## Response windows

- [x] **STACK-034**: In a contested game, when a call has put its item, or a spell and its cast triggers, on the stack, the game shall open, once and only after the last of them is on the stack, a response window of kind `stack` for the top item that asks every seat still in the game other than that item's controller, one seat at a time in turn order, starting with the next seat after the controller.
- [x] **STACK-035**: In a contested game, when the top stack item resolves or is removed and the stack is not empty, the game shall open the `stack` response window again for the new top item, asking every seat still in the game other than that item's controller, starting with the next seat after it in turn order.
- [x] **STACK-036**: In a contested game, when `attack` declares one or more attackers, the game shall open a response window of kind `attack` that asks every seat still in the game other than the active seat, one at a time in turn order, starting with the next seat after the active seat.
- [x] **STACK-037**: In a contested game, when the game enters the `end` step, the game shall open a response window of kind `end` that asks every seat still in the game other than the active seat, one at a time in turn order, starting with the next seat after the active seat.
- [x] **STACK-038**: In a contested game, the game shall open a response window only when an item is put on the stack, when attackers are declared, and on entering the `end` step, and at no other step or event.
- [x] **STACK-039**: In a contested game, when the seat being asked in a response window responds with a `play` or `effect` that puts an item on the stack, the game shall begin the asking again for that item: every seat still in the game other than the responder, starting with the next seat after the responder in turn order and including the controller of the item below.
- [x] **STACK-040**: In a contested game, when the stack becomes empty inside an `attack` or `end` response window and the active seat is still in the game, the game shall begin that window's asking again from the next seat after the active seat, with no seat counted as having passed.
- [x] **STACK-041**: In a contested game, when every seat still in the game other than the active seat has passed in succession with the stack empty, the game shall close the open `attack` or `end` response window.
- [x] **STACK-084**: In a contested game, when the active seat is eliminated while an `attack` or `end` response window is open, the game shall ask no further seat in that window and shall close it once the stack is empty, without beginning its asking again (TURN-061).
- [x] **STACK-042**: In a contested game, while a response window is open and neither a pending choice nor a reminder for a seat other than the active seat is waiting, the seat being asked shall be the seat to act, and only it may call `play`, `effect` or `pass`.
- [x] **STACK-043**: If any seat of a contested game calls `advance` or `attack` while a response window is open or the stack is not empty, then the call shall return an error, not a failed rule check, and change nothing.
- [x] **STACK-044**: In a contested game, when an `attack` response window closes, the active seat shall be the seat to act, and the game shall create no pending choice and move to no other step on that account.
- [x] **STACK-045**: In a contested game, when an `end` response window closes after the game has waited on a seat in it or on a seat's reminder in `end`, the active seat shall be the seat to act and shall continue its turn with `advance`.
- [x] **STACK-085**: In a contested game, when the `end` response window opens on entering `end` and every seat it would ask is passed automatically, or no seat other than the active seat is still in the game, with no reminder issued to another seat, the window shall close within the `advance` that entered `end`, and that advance shall go on toward its `to` (TURN-068).
- [x] **STACK-070**: In a contested game, while a pending choice waits or a reminder waits for a seat other than the active seat, the game shall ask no seat in a response window, make no automatic pass and resolve no stack item.
- [x] **STACK-071**: In a contested game, when the last waiting pending choice has been answered and the last waiting reminder for a seat other than the active seat has been answered with `effect` or `pass`, and a response window is open, the game shall go on with that window's asking, judging each automatic pass by the permanents the seat controls at that moment.
- [x] **STACK-083**: In a contested game, when the game enters `end` and issues a reminder to a seat other than the active seat, the `end` response window shall be open from the moment the step is entered, and its asking shall begin only once every such reminder has been answered with `effect` or `pass` and the stack is empty.
- [x] **STACK-077**: In a contested game, when a `play` plays a land while a response window is open (the timing rule check overridden), the game shall leave the window's seat being asked and its record of seats that have passed unchanged.

## Automatic pass

- [x] **STACK-046**: In a contested game, when the seat about to be asked in a response window controls no untapped permanent, the game shall pass for that seat at once (an automatic pass) and ask the next seat.
- [x] **STACK-047**: In a contested game, when the game makes an automatic pass, the response to the call that caused it shall report the automatic pass, naming the seat and the reason (no untapped permanents).
- [x] **STACK-048**: In a contested game, when the game makes an automatic pass, the automatic pass shall be a public event, naming the seat and the reason, that appears in the digests of the other seats.
- [x] **STACK-049**: In a contested game, when every seat to be asked about a newly put stack item is passed automatically, the game shall resolve the item within the call that put it on the stack, and that call's response shall show the resolution.

## `pass`

- [x] **STACK-050**: In a contested game, when the seat being asked in a response window calls `pass`, the game shall record that seat as having passed and ask the next seat in turn order that has not yet passed in succession, or resolve the top item or close the window when none remains.
- [x] **STACK-051**: In a contested game, when a seat other than the active seat that is the seat to act because of a reminder (a step trigger of a permanent it controls) calls `pass`, the game shall take it as that seat's choice not to record the trigger now and shall stop waiting on that seat for that reminder.
- [x] **STACK-079**: In a contested game, when a seat other than the active seat that is the seat to act because of a reminder sends an `effect` with `immediate: true`, whatever its `source`, the game shall apply the effect at once and go on waiting on that seat for its reminder, which only a `pass` or an `effect` that goes on the stack and whose `source` names the reminded permanent (TURN-063) answers.
- [x] **STACK-052**: If `pass` is called in a contested game by a seat that is not the seat to act, then `pass` shall return an error and change nothing.
- [x] **STACK-053**: If `pass` is called in a contested game by a seat that owes a pending choice, then `pass` shall return an error saying the seat answers with `choose`.
- [x] **STACK-054**: If `pass` is called in a contested game by the active seat when it is the seat to act, and no response window is open, then `pass` shall return an error saying the seat moves on with `advance`, whether or not a reminder was issued to it for the current step (a reminder for the active seat never makes the game wait on it).
- [x] **STACK-055**: In a contested game, `pass` shall accept an optional `after` change number, checked as for every changing call.

## Triggers outside a window

- [x] **STACK-056**: In a contested game, when a triggered ability other than a reminded step trigger triggers while its controller is not the seat to act (a creature dying in combat damage, for example), the game shall open no response window for it and shall not make its controller a seat to act.
- [x] **STACK-057**: In a contested game, when a seat that is asked in a response window, or that is the active seat and the seat to act, records with `effect` a triggered ability that triggered earlier, the game shall accept the call and put the ability on the stack like any other.

## Elimination

- [x] **STACK-058**: In a contested game, when a seat is eliminated, the game shall remove every stack item that seat controls from the stack without resolving it.
- [x] **STACK-059**: In a contested game, when a stack item of kind `spell` is removed because a seat was eliminated, the spell's card shall leave the game when the eliminated seat owns it, and otherwise go to its owner's graveyard, or to its owner's command zone when it is a commander (STACK-073).
- [x] **STACK-060**: In a contested game, when the seat being asked in a response window is eliminated, the game shall move the asking to the next seat still in the game.
- [x] **STACK-061**: In a contested game, when stack items are removed because a seat was eliminated, the game shall keep the remaining items in their order and shall mark none of them disturbed on account of the removal.
- [x] **STACK-062**: In a contested game, the game shall never ask an eliminated seat in a response window.
- [x] **STACK-063**: In a contested game, when a seat is eliminated, the game shall remove from the stack without resolving every stack item whose card that seat owns, whichever seat controls the item.
