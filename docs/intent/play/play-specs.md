# Play — Specs

Design: `play-design.md`. Prefix: `PLAY`.

## Refusals

- [ ] **PLAY-001**: When a `play`, `effect` or `choose` call is refused, whether by an error or a failed rule check, the game shall be left exactly as it was before the call.
- [ ] **PLAY-002**: If a `play` or `effect` call has an error, then the call shall return `ERROR` and shall not be applied even when it carries an `override`.
- [ ] **PLAY-003**: If a `play` or `effect` call fails one or more rule checks and carries no `override`, then the call shall return `REJECTED` listing every failed rule check.
- [ ] **PLAY-004**: When a `play` or `effect` call fails one or more rule checks and carries an `override` reason, the game shall apply the call and the outcome shall name the overridden checks.
- [ ] **PLAY-005**: If a `play` or `effect` call gives an unknown delta key, an unknown `expect` key, an unparseable mana string, an unknown destination, or a delta holding both `look` and `search`, then the call shall return an error.
- [ ] **PLAY-006**: When a delta asks to tap a tapped permanent, untap an untapped permanent, or lower a counter below zero, the game shall apply the change as far as it can, stopping counters at zero, and the outcome shall note it.

## `play`: source

- [ ] **PLAY-007**: When `play` is called without `from`, the game shall look for the card in the hand and then in the command zone.
- [ ] **PLAY-008**: When `play` is called with `from` of `hand`, `command`, `graveyard`, `exile` or `library`, the game shall take the card from that zone.
- [ ] **PLAY-009**: When `play` takes a card from `library`, the game shall find it by name without revealing or reordering any other library card.
- [ ] **PLAY-010**: When `play` is called with `from` of `outside`, the game shall create a new card instance from card data resolved by name before the call is applied, or from a card definition given in `choices.definition`, and make readings for it.
- [ ] **PLAY-011**: If `play` is called with `from` of `outside`, the card's data is not found or is unavailable, and no card definition is given, then `play` shall return an error asking for a card definition.
- [ ] **PLAY-012**: When the `card` argument of `play` names one face of a multi-face card, the game shall play that face and use that face's mana cost, type line and power.

## `play`: lands

- [ ] **PLAY-013**: When the face played by `play` is a land, the game shall charge no cost and increase land drops used by one, whichever zone the land comes from.
- [ ] **PLAY-014**: If `play` plays a land when land drops used is already one or more, then `play` shall fail the land drop rule check.
- [ ] **PLAY-015**: If `play` plays a land outside `main1` and `main2`, then `play` shall fail the timing rule check.

## `play`: spells

- [ ] **PLAY-016**: When the face played by `play` is not a land, the game shall compute the cost as the face's mana cost with each `{X}` replaced by `choices.x`, plus `choices.extra_cost`, plus commander tax when the card is cast from the command zone.
- [ ] **PLAY-017**: When a commander is cast from the command zone, the game shall add `{2}` to the cost for each previous cast of that commander from the command zone, and then increase that commander's cast count by one.
- [ ] **PLAY-018**: When `play` casts a card whose mana cost contains `{X}` and `choices.x` is not given, the game shall treat X as 0 and the outcome shall state that assumption.
- [ ] **PLAY-019**: When the face played by `play` has no mana cost and is not a land, the game shall charge no mana cost and the outcome shall note it.
- [ ] **PLAY-020**: If `play` casts a face that is not an instant and does not have flash as its own keyword while the game is outside `main1` and `main2`, then `play` shall fail the timing rule check.
- [ ] **PLAY-021**: If the cost of a `play` or of an `effect` with `pay` is not payable, then the call shall fail the cost rule check.
- [ ] **PLAY-022**: When the cost rule check is overridden, the game shall tap nothing and spend nothing for the cost, and the outcome shall state that the card was played unpaid.

## `play`: destination

- [ ] **PLAY-023**: When `play` is called without `to` and the played face is a permanent, the game shall put the card onto the battlefield and set its `entered_turn` to the current turn.
- [ ] **PLAY-024**: When `play` is called without `to` and the played face is an instant or sorcery, the game shall put the card into the graveyard.
- [ ] **PLAY-025**: When `play` is called with `to`, the game shall put the card in that destination.
- [ ] **PLAY-026**: When a permanent arrives on the battlefield by `play`, or by `fetch` or `move` to `battlefield`, the game shall have it enter tapped if its enters-tapped reading says it enters tapped, and untapped otherwise.
- [ ] **PLAY-027**: When a permanent enters the battlefield under an enters-tapped reading that carries an assumption, the outcome shall state the assumption.
- [ ] **PLAY-028**: When `play` has put the card in its destination, the game shall then apply the call's delta.

## `effect`

- [ ] **PLAY-029**: When `effect` is called, the game shall apply the delta without moving any card other than as the delta says.
- [ ] **PLAY-030**: When `effect` is called with `pay`, the game shall pay that cost before applying the delta.
- [ ] **PLAY-031**: When `effect` is called without `pay`, the game shall pay nothing.
- [ ] **PLAY-032**: `effect` shall accept any text as `source`.

## Delta

- [ ] **PLAY-033**: The game shall apply the keys of a delta in the order `untap`, `tap`, `mana`, `tokens`, `counters`, `move`, `discard`, `fetch`, `draw`, `life`, `damage`, `shuffle`, then `look` or `search`, whatever order the keys were given in.
- [ ] **PLAY-034**: When a delta has `mana`, the game shall add that mana to the mana pool.
- [ ] **PLAY-035**: When a delta has `tokens`, the game shall create, for each token spec, `count` token instances on the battlefield with the spec's name, types, power and toughness, mana production and tapped state, and `entered_turn` set to the current turn.
- [ ] **PLAY-036**: When a delta has `counters`, the game shall change the named permanents' counters by the signed amounts given and remove any counter kind that reaches zero.
- [ ] **PLAY-037**: When a delta has `move`, the game shall find each named card among the hand, battlefield, graveyard, exile and command zone, in that order, move it to the stated destination, and the outcome shall state the zone it came from.
- [ ] **PLAY-038**: The game shall never take a card from the library on account of a delta's `move` key.
- [ ] **PLAY-039**: When a delta has `discard`, the game shall move the named cards from the hand to the graveyard.
- [ ] **PLAY-040**: When a delta has `fetch`, the game shall take the named cards out of the library, shuffle the library, and then put each card in its stated destination, so that cards fetched to `library_top` or `library_bottom` are placed after the shuffle.
- [ ] **PLAY-041**: If a delta's `fetch` names a card that is not in the library, then the call shall return an error.
- [ ] **PLAY-042**: When a delta has `draw`, the game shall move that many cards from the top of the library to the hand and the outcome shall list exactly the cards drawn.
- [ ] **PLAY-043**: When a delta has `life`, the game shall change the agent's life by the signed amount.
- [ ] **PLAY-044**: When a delta has `damage`, the game shall add that amount to `damage_dealt`.
- [ ] **PLAY-045**: When a delta has `shuffle` true, the game shall shuffle the library.
- [ ] **PLAY-046**: When a card moves to `battlefield_tapped`, the game shall put it onto the battlefield tapped.
- [ ] **PLAY-047**: When any card arrives on the battlefield, the game shall set its `entered_turn` to the current turn.
- [ ] **PLAY-048**: When a card leaves the battlefield, the game shall clear its tapped state and counters.
- [ ] **PLAY-049**: When a token leaves the battlefield, the game shall remove the token from the game.
- [ ] **PLAY-050**: The game shall increase land drops used only when a land is played with `play`, never when a land arrives on the battlefield by `fetch` or `move`.
- [ ] **PLAY-051**: When a `play`, `effect` or `choose` call has been applied, the game shall re-examine every end condition and raise any notice newly due.

## Commanders changing zones

- [ ] **PLAY-052**: When a commander would move to the graveyard or to exile by a delta, a `choose` selection or a discard, and the delta does not set `commander_stays`, the game shall move the commander to the command zone instead and the outcome shall say so.
- [ ] **PLAY-053**: When a delta sets `commander_stays` and moves a commander to the graveyard or to exile, the game shall move the commander there as written.
- [ ] **PLAY-054**: When a commander is moved to the hand or the library, the game shall move it there.

## Choices

- [ ] **PLAY-055**: The game shall record `choices.modes`, `choices.targets` and `choices.notes` with the call and shall never refuse a call on account of their content.

## Pending choices

- [ ] **PLAY-056**: When a delta has `look`, the game shall reveal up to `n` cards from the stated end of the library, in order starting from that end, create a pending choice holding them and the `rest` destination, and set the game's status to `pending_choice`.
- [ ] **PLAY-057**: If a delta's `look` gives no `rest`, then the call shall return an error.
- [ ] **PLAY-058**: When a delta has `search`, the game shall reveal the library's cards sorted by name, limited to cards whose name or type line contains `filter` ignoring case when a filter is given, create a pending choice holding them, and set the game's status to `pending_choice`.
- [ ] **PLAY-059**: When a `look` or `search` would reveal no cards, the game shall create no pending choice, and the outcome shall be `OK` and state that there was nothing to reveal.
- [ ] **PLAY-060**: When a `search` reveals no cards, the game shall still shuffle the library.
- [ ] **PLAY-061**: When a `look` or `search` creates a pending choice, the outcome shall have status `CHOICE` and list the choice id and the revealed cards.
- [ ] **PLAY-062**: When `choose` is called with the pending choice's id, the game shall move each selected revealed card to the destination it is listed under and set the game's status to `active`.
- [ ] **PLAY-063**: When `choose` resolves a `look`, the game shall move every revealed card not selected to the `rest` destination, in `rest_order` when given and otherwise in the order revealed.
- [ ] **PLAY-064**: When `choose` resolves a `search`, the game shall leave unselected cards in the library and shuffle the library before placing any selected card on the top or bottom of the library.
- [ ] **PLAY-065**: When `choose` selects several cards to `library_top`, the game shall place them with the first-named card on top and above any unselected cards that also go to the top.
- [ ] **PLAY-066**: If `choose` gives a choice id other than the pending choice's, or names a card that was not revealed, then `choose` shall return an error and change nothing.
- [ ] **PLAY-067**: `choose` shall accept an empty `selections`.

## Expect

- [ ] **PLAY-068**: When a `play` or `effect` call includes `expect`, the game shall apply the call and then compare each expected value with the game's state, and the outcome shall carry one warning for each value that differs, stating the actual and expected values.
- [ ] **PLAY-069**: The game shall never refuse a call because an `expect` value differs from the game's state.
- [ ] **PLAY-070**: `expect` shall accept only the keys `hand`, `lands`, `untapped_lands`, `life`, `pool`, `library`, `tax`, `damage_dealt` and `step`, and an error for any other key shall list these.
- [ ] **PLAY-071**: When comparing `expect.tax`, the game shall use the tax on the next cast of the commander, taking the higher when there are two commanders.
- [ ] **PLAY-072**: When comparing `expect.pool`, the game shall compare mana symbols without regard to their order or any spending restriction.
- [ ] **PLAY-073**: When a call with `expect` creates a pending choice, the game shall compare the expected values at the moment the pending choice is created.
