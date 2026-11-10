# Deck — Specs

Design: `deck-design.md`. Prefix: `DECK`.

## Parsing the list

- [x] **DECK-001**: When parsing the `cards` text given to `load_deck`, the deck parser shall read each non-ignored line as `<count> <name>`, `<count>x <name>`, or a bare `<name>` with a count of one.
- [x] **DECK-002**: When parsing the `cards` text given to `load_deck`, the deck parser shall ignore blank lines and lines that start with `#` or `//`.
- [x] **DECK-003**: When a deck list line carries a set code in parentheses after the card name, the deck parser shall drop the set code and everything after it.
- [x] **DECK-004**: When the same card appears on more than one deck list line, the deck parser shall add the counts together.
- [x] **DECK-005**: If a deck list line gives a count of zero or less, then `load_deck` shall return an error naming the line and create nothing.
- [x] **DECK-006**: When a card named in the `commander` parameter of `load_deck` also appears in `cards`, `load_deck` shall count that card once.

## Commanders

- [x] **DECK-007**: If `load_deck` is given no commander or more than two commanders, then `load_deck` shall return an error and create nothing.
- [x] **DECK-008**: If a commander name given to `load_deck` resolves to no card and has no card definition, then `load_deck` shall return an error naming it and create nothing.

## Card definitions

- [x] **DECK-009**: When `load_deck` is given a card definition for a card in the deck, the loaded deck shall use each field the definition gives in place of the fetched card data and the fetched value for every field it does not give.
- [x] **DECK-010**: `load_deck` shall accept a card definition for any card in the deck, whether or not Scryfall has that card.
- [x] **DECK-011**: When a card definition names a `face`, `load_deck` shall apply the definition's face-level fields to that face, and to the card's first face when no `face` is named.
- [x] **DECK-012**: If a card definition names a card that is not in the deck, then `load_deck` shall return an error naming it and create nothing.
- [x] **DECK-013**: If a card definition is given for a name Scryfall does not have and the definition gives no `type_line`, then `load_deck` shall return an error naming it and create nothing.
- [x] **DECK-014**: When a card definition gives `produces`, the loaded deck shall treat that card as a mana source that taps for the stated mana at no other cost, in place of the card's mana reading, with a list of mana strings meaning a choice between them.
- [x] **DECK-015**: When a card definition gives `enters_tapped`, the loaded deck shall use that value in place of the card's enters-tapped reading.
- [x] **DECK-016**: When a card definition's `keywords` includes `Haste`, `Vigilance` or `Flash`, the loaded deck shall treat that keyword as the card's own.
- [x] **DECK-017**: The loaded deck shall hold readings made from each card's data after card definitions have been applied.
- [x] **DECK-018**: `load_deck` shall never change the shared card cache on account of a card definition.

## Resolution errors

- [x] **DECK-019**: If one or more deck list names are not found by Scryfall and have no card definition, then `load_deck` shall return a single error listing all of them and create nothing.
- [x] **DECK-020**: If card data is unavailable for a name that is not cached and has no card definition giving a `type_line`, then `load_deck` shall return an error that lists those names, says the failure is temporary, and creates nothing.

## Deck checks

- [x] **DECK-021**: If the deck, including commanders, does not have exactly 100 cards, then `load_deck` shall fail the size check.
- [x] **DECK-022**: If a card appears more than once and its type line does not include `Basic` and its rules text does not allow multiple copies, then `load_deck` shall fail the singleton check.
- [x] **DECK-023**: If a card whose rules text allows a stated number of copies appears more times than that number, then `load_deck` shall fail the singleton check.
- [x] **DECK-024**: If a card's color identity is not within the combined color identity of the commanders, then `load_deck` shall fail the color identity check.
- [x] **DECK-025**: If a card obtained from Scryfall is not legal in Commander, then `load_deck` shall fail the legality check.
- [x] **DECK-026**: If a commander is not a legendary creature and its rules text does not say it can be your commander, then `load_deck` shall fail the commander eligibility check.
- [x] **DECK-027**: If any deck check fails and `load_deck` was given no `override`, then `load_deck` shall respond `REJECTED`, list every failed deck check, and create nothing.
- [x] **DECK-028**: When deck checks fail and `load_deck` was given an `override` reason, `load_deck` shall create the loaded deck and record the failed checks and the reason on it.

## Deck id and loaded decks

- [x] **DECK-029**: `load_deck` shall derive the deck id as `d` followed by the first ten hexadecimal characters of a SHA-256 hash over the sorted commander names, the other entries as count and canonical card name sorted by name, the card definitions sorted by name, and the resolved card data of every card.
- [x] **DECK-030**: When two `load_deck` calls give lists that differ only in formatting, line order, letter case or comments and resolve to the same card data, `load_deck` shall return the same deck id for both.
- [x] **DECK-031**: When `load_deck` computes an id for which a loaded deck already exists, `load_deck` shall return that existing loaded deck unchanged.
- [x] **DECK-032**: The deck component shall never alter a loaded deck after it has been created.
- [x] **DECK-033**: When `load_deck` is called with `refresh` and a card's fetched data has changed, `load_deck` shall create a loaded deck with a new id and leave every existing loaded deck unchanged.
- [x] **DECK-034**: If a newly computed deck id is already held by a loaded deck with different contents, then `load_deck` shall lengthen the new id two hexadecimal characters at a time until it is unique.
- [x] **DECK-035**: The loaded deck shall hold its id, commanders, entries, resolved card data, readings, and any overridden deck checks with their reasons.

## Response

- [x] **DECK-036**: When `load_deck` succeeds, the outcome shall state the deck id, the card count and the commanders.
- [x] **DECK-037**: When `load_deck` succeeds, the outcome shall report, each only when non-empty: card definitions applied, mana abilities read with assumptions and those assumptions, mana abilities not read, mana sources the auto payment system will not use on its own, cards that grant haste or vigilance, cards read as entering tapped, cards assumed to enter untapped with their conditions, keyword readings made with assumptions, and overridden deck checks.
