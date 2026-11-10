---
parent: high-level-design
prefix: DECK
---

# Deck

## Context and Design Philosophy

A deck is loaded once and played many times. `load_deck` takes a deck list as text, resolves every card, checks the deck against Commander's construction rules, and returns a short id. `new_game` then needs only that id, so the hundred-line list crosses the agent's context once.

A **loaded deck** is identified by its contents and nothing else: the same list always gives the same id. There are no versions, names, owners or history.

## The `load_deck` Tool

```
load_deck(cards, commander, definitions?, refresh?, override?)
```

| Parameter | Meaning |
|---|---|
| `cards` | The deck list as text, one entry per line. |
| `commander` | The commander's name, or a list of two names for a pair of commanders. |
| `definitions` | Optional list of card definitions (below). |
| `refresh` | Optional; when true, card data for every card in the deck is fetched again. |
| `override` | Optional reason; when given, failed deck checks do not stop the load. |

### List format

Each line is `<count> <name>`, `<count>x <name>`, or a bare `<name>` (count 1). Blank lines and lines starting with `#` or `//` are ignored. Trailing printing details, as exported by deck sites, are dropped: a set code in parentheses and anything after it (`1 Sol Ring (C21) 263 *F*` is `1 Sol Ring`). A line that fits none of these is an error naming the line.

A commander that also appears in `cards` is counted once. The deck is the commander or commanders plus every other entry.

A card that appears on more than one line has its counts added together. A count of zero or less is an error naming the line. Because any text is a possible card name, a stray line such as a section heading is caught as an unresolved name rather than as a format error.

### Card definitions

```
CardDefinition {
  name: string               // required; must be a card in this deck
  face?: string              // which face the fields below describe; the first face when omitted
  mana_cost?: ManaString
  type_line?: string
  oracle_text?: string
  power?: string
  toughness?: string
  color_identity?: [color]
  keywords?: [string]
  produces?: ManaString | [ManaString]   // what it taps for; replaces the mana reading
  enters_tapped?: bool       // replaces the enters-tapped reading
}
```

A definition replaces fetched card data field by field for that card within this loaded deck: fields the definition gives are used, the rest come from Scryfall. For a name Scryfall does not have, `type_line` is required and other missing fields are empty. Definitions are accepted for any card, found or not; it is the agent's simulation. They live with the loaded deck and never change the shared card cache.

`produces` given as a list is a choice between the options. A card with `produces` is treated as a mana source that taps for that mana at no other cost.

Readings (see `card-reading`) are made from the card data after definitions have been applied, so a definition's `oracle_text` is what gets read. `produces` replaces only the mana reading and `enters_tapped` only the enters-tapped reading. `Haste`, `Vigilance` or `Flash` in a definition's `keywords` is treated as the card's own keyword.

## Resolution and Errors

`load_deck` fails with an **error**, creating nothing, when:

- a line cannot be parsed;
- no commander is given, more than two are given, or a commander name is not resolved;
- a name is not found by Scryfall and has no definition (all such names are listed together);
- card data is unavailable for a name that is not cached and has no definition giving a `type_line` (the names are listed, and the response says the failure is temporary);
- a definition names a card that is not in the deck, or defines an unfound card without a `type_line`.

## Deck Checks

These are rule checks: each failure is reported, and the load is refused unless `override` is given. All failures are reported together so one override covers them.

| Check | Passes when |
|---|---|
| Size | The deck has exactly 100 cards including commanders. |
| Singleton | No card appears more than once, except cards whose type line includes `Basic`, cards whose rules text says a deck can have any number of them, and cards whose rules text allows a stated number of copies, up to that number. |
| Color identity | Every card's color identity is within the combined color identity of the commanders. |
| Legality | Every card is legal in Commander. A card supplied only by definition passes. |
| Commander eligibility | Each commander is a legendary creature, or its rules text says it can be your commander. |

Pairings between two commanders (partner, background, and similar) are not checked.

## Deck Id

The id is `d` followed by the first ten hexadecimal characters of a SHA-256 hash over a canonical form of the deck: the commander names sorted, the other entries as `(count, name)` sorted by name using the canonical card names, the definitions sorted by name with their fields in a fixed order, and the resolved card data of every card. Formatting, line order, letter case and comments do not affect the id. Definitions and card data do.

A loaded deck never changes once created. Every `load_deck` call resolves the cards, runs the deck checks and computes the id afresh; if a loaded deck with that id exists it is returned as it is, otherwise one is created. A deck that failed its checks needs its `override` on every call. With `refresh`, card data is fetched again first: if any card's data has changed, the contents hash differently and the result is a new loaded deck with a new id, and the earlier one, with any games on it, is untouched.

If two different decks would ever produce the same id, the newer one's id is lengthened, two characters at a time, until it is unique.

`override` reasons are recorded on the loaded deck each time one is used.

## What a Loaded Deck Holds

- its id, commanders and entries;
- the resolved card data for every card, with definitions already applied, so games on this deck do not depend on later changes to the cache;
- the mana, step-trigger and keyword readings for every card;
- the check failures that were overridden and the reasons.

## Response

On success the response states the id, card count and commanders, then, when non-empty: definitions applied; mana abilities read with assumptions (with each assumption); mana abilities not read; mana sources the auto payment system will not use on its own (those that are sacrificed or carry another cost); cards that grant haste or vigilance; cards read as entering tapped, and those assumed to enter untapped with their condition; keyword readings made with assumptions; and overridden checks. Step triggers are not listed here; they appear as reminders during play.

```
OK Loaded deck d3f9a01c2e: 100 cards, commander Atraxa, Praetors' Voice.
Mana read with assumptions: Nimbus Maze (ignores activation condition), Shrine of the Forsaken Gods (ignores conditional bonus)
Mana not read: Mana Flare
```

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| How the commander is named | A `commander` parameter | A `*CMDR*` marker inside the list text | Lists exported from deck sites carry no marker; a parameter spares the agent editing text. |
| Scope of card definitions | Any card, found or not | Only cards Scryfall cannot find | Tenet *It's the agent's simulation*: the agent may be experimenting with a changed card. |
| Where definitions live | With the loaded deck | In the shared card cache | A definition is one deck's experiment and must not leak into other decks. |
| Id derivation | Hash of canonical contents, definitions and resolved card data | Random id; hash of the raw text; hash of the list without card data | Same contents must give the same id so a reload is free and games are reproducible; raw-text hashing would make whitespace matter; leaving card data out would let a refresh change what an existing id means. |
| Card data snapshot per deck | Loaded deck stores its resolved card data and never changes | Read the cache at game time; update the deck in place on refresh | A game started tomorrow must behave like one started today, and a game in progress must not change under the agent. |
| Deck check failures | Refuse unless overridden | Warn only; refuse always | Matches every other rule check in the service: approximate, explained, overridable. |

## Open Questions & Future Decisions

### Deferred
1. Commander pairing rules (partner, partner with, backgrounds, companions) are not checked.
2. Sideboards and "outside the game" card pools are not part of a loaded deck; a card brought in from outside the game is resolved when it is played.

## References

- `docs/high-level-design.md`
- `docs/intent/card-data/card-data-design.md`
- `docs/intent/card-reading/card-reading-design.md`
