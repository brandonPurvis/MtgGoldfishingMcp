# Play — Specs

Design: `play-design.md`. Prefix: `PLAY`.

## Refusals

- [x] **PLAY-001**: In every game, when a `play`, `effect` or `choose` call is refused, whether by an error or a failed rule check, the game shall be left exactly as it was before the call.
- [x] **PLAY-002**: In every game, if a `play` or `effect` call has an error, then the call shall return `ERROR` and shall not be applied even when it carries an `override`.
- [x] **PLAY-003**: In every game, if a `play` or `effect` call fails one or more rule checks and carries no `override`, then the call shall return `REJECTED` listing every failed rule check.
- [x] **PLAY-004**: In every game, when a `play` or `effect` call fails one or more rule checks and carries an `override` reason, the game shall apply the call and the outcome shall name the overridden checks.
- [x] **PLAY-005**: In every game, if a `play` or `effect` call gives an unknown delta key, an unknown `expect` key, an unparseable mana string, an unknown destination, or a delta holding both `look` and `search`, then the call shall return an error.
- [x] **PLAY-006**: In every game, when a delta asks to tap a tapped permanent, untap an untapped permanent, or lower a counter below zero, the game shall apply the change as far as it can, stopping counters at zero, and the outcome shall note it.
- [ ] **PLAY-074**: If a delta in a goldfish game uses a key only a contested game has — `counter`, `control`, `ask`, `look_at_hand`, or `life` or `damage` given as a map from seat number — then the call shall return an error.
- [ ] **PLAY-075**: If a delta in a contested game gives `damage` as a single number instead of a map from seat number, then the call shall return an error.
- [ ] **PLAY-076**: If a delta in a contested game holds more than one of `look`, `search` and `look_at_hand`, then the call shall return an error.
- [ ] **PLAY-077**: If a delta in a contested game gives a seat number that is not in the game or that names an eliminated seat, in `control`, `life`, `damage`, `ask` or `look_at_hand`, then the call shall return an error.
- [ ] **PLAY-078**: If a delta's `counter` in a contested game names something that is not an item on the stack (neither a stack item id nor the name of a spell's card on the stack), then the call shall return an error.
- [ ] **PLAY-079**: If a delta's `move`, `discard`, `fetch` or `tap` in a contested game names a card that is in another seat's hand or library, then the call shall return an error saying that seat's hidden zones are reached through `ask`.

## `play`: source

- [x] **PLAY-007**: In every game, when `play` is called without `from`, the game shall look for the card in the acting seat's hand and then in the acting seat's command zone.
- [x] **PLAY-008**: In every game, when `play` is called with `from` of `hand`, `command`, `graveyard`, `exile` or `library`, the game shall take the card from that zone of the acting seat.
- [ ] **PLAY-080**: In a contested game, when `play` is called with `from` of a public zone (`graveyard`, `exile` or `command`) and names a card another seat owns, by instance id or by a name that matches no card of the acting seat in that zone, the game shall take that card from the other seat's zone.
- [x] **PLAY-009**: In every game, when `play` takes a card from `library`, the game shall find it by name in the acting seat's library without revealing or reordering any other library card.
- [x] **PLAY-010**: In every game, when `play` is called with `from` of `outside`, the game shall create a new card instance from card data resolved by name before the call is applied, or from a card definition given in `choices.definition`, and make readings for it.
- [x] **PLAY-011**: In every game, if `play` is called with `from` of `outside`, the card's data is not found or is unavailable, and no card definition is given, then `play` shall return an error asking for a card definition.
- [x] **PLAY-012**: In every game, when the `card` argument of `play` names one face of a multi-face card, the game shall play that face and use that face's mana cost, type line and power.

## `play`: lands

- [x] **PLAY-013**: In every game, when the face played by `play` is a land, the game shall charge no cost and increase the acting seat's land drops used by one, whichever zone the land comes from.
- [x] **PLAY-014**: In every game, if `play` plays a land when the acting seat's land drops used is already one or more, then `play` shall fail the land drop rule check.
- [x] **PLAY-015**: In every game, if `play` plays a land while the game is in a step other than `main1` or `main2`, then `play` shall fail the timing rule check.
- [ ] **PLAY-081**: If `play` plays a land in a contested game while the acting seat is not the active seat or the stack is not empty, then `play` shall fail the timing rule check.
- [ ] **PLAY-082**: In a contested game, when `play` plays a land, the game shall at once put the land in its destination — `to` when given, otherwise the battlefield under the acting seat's control with `entered_turn` set to the current turn — then apply the call's delta, putting nothing on the stack.

## `play`: spells

- [x] **PLAY-016**: In every game, when the face played by `play` is not a land, the game shall compute the cost as the face's mana cost with each `{X}` replaced by `choices.x`, plus `choices.extra_cost`, plus commander tax when the card is cast from the command zone.
- [x] **PLAY-017**: In every game, when a commander is cast from the command zone, the game shall add `{2}` to the cost for each previous cast of that commander from the command zone, and then increase that commander's cast count by one.
- [x] **PLAY-018**: In every game, when `play` casts a card whose mana cost contains `{X}` and `choices.x` is not given, the game shall treat X as 0 and the outcome shall state that assumption.
- [x] **PLAY-019**: In every game, when the face played by `play` has no mana cost and is not a land, the game shall charge no mana cost and the outcome shall note it.
- [x] **PLAY-020**: In every game, if `play` casts a face that is not an instant and does not have flash as its own keyword while the game is in a step other than `main1` or `main2`, then `play` shall fail the timing rule check.
- [ ] **PLAY-083**: If `play` in a contested game casts a face that is not an instant and does not have flash as its own keyword while the acting seat is not the active seat or the stack is not empty, then `play` shall fail the timing rule check.
- [x] **PLAY-021**: In every game, if the cost of a `play` or of an `effect` with `pay` is not payable, then the call shall fail the cost rule check.
- [x] **PLAY-022**: In every game, when the cost rule check is overridden, the game shall tap nothing and spend nothing for the cost, and the outcome shall state that the card was played unpaid.

## `play`: destination

- [x] **PLAY-023**: In a goldfish game, when `play` is called without `to` and the played face is a permanent, the game shall put the card onto the battlefield and set its `entered_turn` to the current turn.
- [x] **PLAY-024**: In a goldfish game, when `play` is called without `to` and the played face is an instant or sorcery, the game shall put the card into the graveyard.
- [x] **PLAY-025**: In a goldfish game, when `play` is called with `to`, the game shall put the card in that destination.
- [x] **PLAY-026**: In every game, when a permanent arrives on the battlefield by `play`, or by `fetch` or `move` to `battlefield`, the game shall have it enter tapped if its enters-tapped reading says it enters tapped, and untapped otherwise.
- [x] **PLAY-027**: In every game, when a permanent enters the battlefield under an enters-tapped reading that carries an assumption, the outcome shall state the assumption.
- [x] **PLAY-028**: In a goldfish game, when `play` has put the card in its destination, the game shall then apply the call's delta, within the same call.

## `effect`

- [x] **PLAY-029**: In a goldfish game, when `effect` is called, the game shall apply the delta at once without moving any card other than as the delta says.
- [x] **PLAY-030**: In every game, when `effect` is called with `pay`, the game shall pay that cost when the call is applied and before its delta is applied, so that mana added by the same call's delta cannot pay it.
- [x] **PLAY-031**: In every game, when `effect` is called without `pay`, the game shall pay nothing.
- [x] **PLAY-032**: In every game, `effect` shall accept any text as `source`.
- [ ] **PLAY-084**: In a goldfish game, when `effect` is called with `immediate`, true or false, the game shall apply the call exactly as it would without it.

## Delta

- [x] **PLAY-033**: In a goldfish game, the game shall apply the keys of a delta in the order `untap`, `tap`, `mana`, `tokens`, `counters`, `move`, `discard`, `fetch`, `draw`, `life`, `damage`, `shuffle`, then `look` or `search`, whatever order the keys were given in.
- [ ] **PLAY-085**: In a contested game, the game shall apply the keys of a delta in the order `counter`, `untap`, `tap`, `mana`, `tokens`, `counters`, `control`, `move`, `discard`, `fetch`, `draw`, `life`, `damage`, `shuffle`, then `ask`, then `look_at_hand`, `look` or `search`, whatever order the keys were given in.
- [x] **PLAY-034**: In every game, when a delta has `mana`, the game shall add that mana to the acting seat's mana pool.
- [x] **PLAY-035**: In every game, when a delta has `tokens`, the game shall create, for each token spec, `count` token instances on the battlefield with the spec's name, types, power and toughness, mana production and tapped state, and `entered_turn` set to the current turn.
- [ ] **PLAY-086**: In every game, when a delta creates a token, the game shall record the acting seat (the seat whose delta creates it) as the token's owner and as its controller.
- [x] **PLAY-036**: In every game, when a delta has `counters`, the game shall change the named permanents' counters by the signed amounts given and remove any counter kind that reaches zero.
- [x] **PLAY-037**: In every game, when a delta has `move`, the game shall find each named card among the acting seat's hand, then the battlefield, graveyard, exile and command zone, in that order, move it to the stated destination, and the outcome shall state the zone it came from.
- [ ] **PLAY-087**: In a contested game, when a delta's `move` looks for a named card on the battlefield, in a graveyard, in exile or in a command zone, the game shall look among those zones of every seat, and never in another seat's hand.
- [ ] **PLAY-088**: In a contested game, when a delta's `move` sends a card to `hand`, `graveyard`, `exile`, `command`, `library_top` or `library_bottom`, the game shall put it in that zone of the card's owner, whichever seat moves it.
- [ ] **PLAY-089**: In a contested game, when a delta's `move` sends a card to `battlefield` or `battlefield_tapped`, the game shall put it there under the acting seat's control, whichever seat owns it.
- [ ] **PLAY-090**: If a delta's `move` in a contested game names a spell's card that is on the stack and the same delta's `counter` does not counter that card's stack item, then the call shall return an error.
- [x] **PLAY-038**: In every game, the game shall never take a card from a library on account of a delta's `move` key.
- [x] **PLAY-039**: In every game, when a delta has `discard`, the game shall move the named cards from the acting seat's hand to the acting seat's graveyard.
- [x] **PLAY-040**: In every game, when a delta has `fetch`, the game shall take the named cards out of the acting seat's library, shuffle that library, and then put each card in its stated destination, so that cards fetched to `library_top` or `library_bottom` are placed after the shuffle, each such list placed top to bottom with its first-named card topmost.
- [x] **PLAY-041**: In every game, if a delta's `fetch` names a card that is not in the acting seat's library, then the call shall return an error.
- [x] **PLAY-042**: In every game, when a delta has `draw`, the game shall move that many cards from the top of the acting seat's library to the acting seat's hand and the outcome shall list exactly the cards drawn.
- [x] **PLAY-043**: In every game, when a delta has `life` as a single number, the game shall change the acting seat's life by the signed amount.
- [x] **PLAY-044**: In a goldfish game, when a delta has `damage`, the game shall add that amount to `damage_dealt` (the damage pooled across the three imaginary opponents).
- [ ] **PLAY-091**: In a contested game, when a delta has `life` as a map from seat number, the game shall change each named seat's life by its signed amount.
- [ ] **PLAY-092**: In a contested game, when a delta has `damage` as a map from seat number, the game shall take each amount from that seat's life.
- [ ] **PLAY-093**: In a contested game, the game shall never add damage from a delta's `damage` key to any commander's damage against a seat.
- [ ] **PLAY-094**: In a contested game, when a delta has `control`, the game shall make each named seat the controller of the permanents listed under its seat number, and each such permanent shall keep that controller until it leaves the battlefield or that seat is eliminated.
- [ ] **PLAY-095**: In a contested game, the game shall accept `tap`, `untap`, `counters`, `control` and `move` in a delta for cards that another seat owns or controls in a public zone (battlefield, graveyard, exile, command zone).
- [x] **PLAY-045**: In every game, when a delta has `shuffle` true, the game shall shuffle the acting seat's library.
- [x] **PLAY-046**: In every game, when a card moves to `battlefield_tapped`, the game shall put it onto the battlefield tapped.
- [x] **PLAY-047**: In every game, when any card arrives on the battlefield, the game shall set its `entered_turn` to the current turn.
- [x] **PLAY-048**: In every game, when a card leaves the battlefield, the game shall clear its tapped state and counters.
- [x] **PLAY-049**: In every game, when a token leaves the battlefield, the game shall remove the token from the game.
- [x] **PLAY-050**: In every game, the game shall increase a seat's land drops used only when that seat plays a land with `play`, never when a land arrives on the battlefield by `fetch` or `move`.
- [x] **PLAY-051**: In every game, when a `play`, `effect` or `choose` call has been applied, the game shall re-examine every end condition and raise any notice newly due.

## Commanders changing zones

- [x] **PLAY-052**: In every game, when a commander would move to the graveyard or to exile by a delta, a `choose` selection or a discard, and the delta does not set `commander_stays`, the game shall move the commander to its owner's command zone instead and the outcome shall say so.
- [x] **PLAY-053**: In every game, when a delta sets `commander_stays` and moves a commander to the graveyard or to exile, the game shall move the commander there as written.
- [x] **PLAY-054**: In every game, when a commander is moved to the hand or the library, the game shall move it there.

## Choices

- [x] **PLAY-055**: In every game, the game shall record `choices.modes`, `choices.targets` and `choices.notes` with the call and shall never refuse a call on account of their content.

## Pending choices

- [x] **PLAY-056**: In every game, when a delta has `look`, the game shall reveal up to `n` cards from the stated end of the acting seat's library (the top when no end is stated), in order starting from that end, create a pending choice for the acting seat holding them and the `rest` destination, and set the game's status to `pending_choice`.
- [x] **PLAY-057**: In every game, if a delta's `look` gives no `rest`, then the call shall return an error.
- [x] **PLAY-058**: In every game, when a delta has `search`, the game shall reveal the cards of the acting seat's library sorted by name, limited to cards whose name, or any face's name or type line, contains `filter`, ignoring case, when a filter is given, create a pending choice for the acting seat holding them, and set the game's status to `pending_choice`.
- [x] **PLAY-059**: In every game, when a `look` or `search` would reveal no cards, the game shall create no pending choice, and the outcome shall be `OK` and state that there was nothing to reveal.
- [x] **PLAY-060**: In every game, when a `search` reveals no cards, the game shall still shuffle the acting seat's library.
- [x] **PLAY-061**: In every game, when applying a seat's own `play` or `effect` call creates a `look` or `search` pending choice for that seat, the outcome shall have status `CHOICE` and list the choice id and the revealed cards.
- [x] **PLAY-062**: In every game, when `choose` is called with the id of the waiting `look` or `search` pending choice by the seat it is addressed to, the game shall move each selected revealed card to the destination it is listed under and, when no other pending choice waits, set the game's status to `active`.
- [x] **PLAY-063**: In every game, when `choose` answers a `look`, the game shall move every revealed card not selected to the `rest` destination, in `rest_order` when given (listed top to bottom), and otherwise so that cards returned to the end they were looked at from keep their order, and cards sent elsewhere go in the order revealed.
- [x] **PLAY-064**: In every game, when `choose` answers a `search`, the game shall leave unselected cards in the library and shuffle the library before placing any selected card on the top or bottom of the library.
- [x] **PLAY-065**: In every game, when `choose` selects several cards to `library_top`, the game shall place them with the first-named card on top and above any unselected cards that also go to the top.
- [x] **PLAY-066**: In every game, if `choose` gives a choice id other than the waiting pending choice's, or names a card that was not revealed, then `choose` shall return an error and change nothing.
- [x] **PLAY-067**: In every game, `choose` shall accept an empty `selections` for a `look` or `search` pending choice.
- [ ] **PLAY-097**: In a contested game, when a delta has `ask`, the game shall create one pending choice of kind `ask` for each seat named in each entry, in turn order starting from the seat after the acting seat, each carrying the entry's `text` and the acting seat's number as `asked_by`.
- [ ] **PLAY-098**: In a contested game, when an `ask` entry gives `seats` as `"opponents"`, the game shall address it to every seat other than the acting seat that is still in the game.
- [ ] **PLAY-099**: In a contested game, when a seat answers an `ask` pending choice with `choose` and a `delta`, the game shall apply that delta at once with the answering seat as the acting seat, putting nothing on the stack.
- [ ] **PLAY-100**: If the `delta` answering an `ask` pending choice in a contested game holds `ask`, `look_at_hand`, `look` or `search`, then `choose` shall return an error.
- [ ] **PLAY-101**: In a contested game, the game shall never refuse the answer to an `ask` pending choice on account of how it compares with the choice's `text`.
- [ ] **PLAY-102**: In a contested game, when a delta has `look_at_hand`, the game shall create a pending choice of kind `hand` addressed to the acting seat that reveals to it the cards in the named seat's hand, recording the acting seat (the looking seat) as `asked_by` and the named seat (the seat whose hand is shown) as `hand_of`.
- [ ] **PLAY-103**: In a contested game, when `choose` answers a `hand` pending choice, the game shall move each selected card to the destination it is listed under, in the zones of the card's owner whichever seat answers, and leave every revealed card not selected, which may be all of them, in the hand it was revealed from.
- [ ] **PLAY-104**: In a contested game, when a delta's `look_at_hand` names a seat whose hand is empty, the game shall create no pending choice and the outcome shall state that there was nothing to reveal.
- [ ] **PLAY-105**: In a contested game, while more than one pending choice waits, the game shall accept `choose` only for the pending choice created earliest, so that pending choices are answered one at a time in the order they were created.
- [ ] **PLAY-106**: If `choose` in a contested game gives the id of a pending choice addressed to a seat other than the calling seat, then `choose` shall return an error and change nothing.
- [ ] **PLAY-107**: In every game, if `choose` gives an argument other than those its pending choice's kind is answered with (`selections`, and for a `look` `rest_order`, for `look` and `search`; `selections` and `delta` for `hand`; `delta` for `ask`; `restate` or nothing for `resolve`; `blocks` for `blocks`), then `choose` shall return an error and change nothing.
- [ ] **PLAY-111**: In a contested game, when `choose` answering a `hand` pending choice selects a card to `battlefield` or `battlefield_tapped` and the answer's `delta` gives no `control` for that card, the game shall put the card onto the battlefield under its owner's control.
- [ ] **PLAY-112**: In a contested game, when `choose` answering a `hand` pending choice selects a card to `battlefield` or `battlefield_tapped` and the answer's `delta` names that card under a seat number in `control`, the game shall put the card onto the battlefield under that seat's control.
- [ ] **PLAY-113**: If the `delta` given with `choose` for a `hand` pending choice in a contested game holds any key other than `control`, or its `control` names a card that the same answer does not select to the battlefield, then `choose` shall return an error and change nothing.

## Expect

- [x] **PLAY-068**: In every game, when a `play` or `effect` call includes `expect`, the game shall apply the call and then compare each expected value with the acting seat's state, and the outcome shall carry one warning for each value that differs, stating the actual and expected values.
- [x] **PLAY-069**: In every game, the game shall never refuse a call because an `expect` value differs from the game's state.
- [x] **PLAY-070**: In a goldfish game, `expect` shall accept only the keys `hand`, `lands`, `untapped_lands`, `life`, `pool`, `library`, `tax`, `damage_dealt` and `step`, and an error for any other key shall list these.
- [x] **PLAY-071**: In every game, when comparing `expect.tax`, the game shall use the tax on the next cast of the acting seat's commander, taking the higher when it has two commanders.
- [x] **PLAY-072**: In every game, when comparing `expect.pool`, the game shall compare the mana symbols of the acting seat's mana pool without regard to their order or any spending restriction.
- [x] **PLAY-073**: In every game, when a call with `expect` creates a pending choice as it is applied, the game shall compare the expected values at the moment the pending choice is created.
- [ ] **PLAY-108**: In a contested game, `expect` shall accept only the keys `hand`, `lands`, `untapped_lands`, `life`, `pool`, `library`, `tax` and `step`, and `damage_dealt` or any other key shall be an error that lists these.
- [ ] **PLAY-109**: In a contested game, the game shall compare each `expect` value of `hand`, `lands`, `untapped_lands`, `life`, `pool`, `library` and `tax` with the acting seat's own hand, permanents, life, mana pool, library and commander tax, never another seat's.
- [ ] **PLAY-110**: In a contested game, when a `play` or `effect` call with `expect` puts an item on the stack, the game shall compare the expected values when the call is applied (cost paid, item on the stack), not when the item resolves.
