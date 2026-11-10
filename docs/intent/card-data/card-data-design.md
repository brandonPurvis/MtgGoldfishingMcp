---
parent: high-level-design
prefix: CARD
---

# Card Data

## Context and Design Philosophy

Every check the service makes rests on card data: mana costs, type lines, power, rules text. This component obtains that data from Scryfall by exact name, keeps it in a cache so no card is fetched twice, and presents it to the rest of the service as one card model. It does not interpret the data; reading rules text belongs to `card-reading`.

It has two parts. The **card model** — `Card` and `Face` — is part of the domain. The **Scryfall adapter** implements the application's `CardCatalog` port (see `application`): it fetches, caches and converts Scryfall's data into the card model. The rest of the service sees only the port. Tests use an in-memory catalog loaded from recorded card data, which passes the same contract tests as the Scryfall adapter.

Exactness is the point. A misspelled name must fail, never resolve to a different card, because a silently wrong card corrupts every later check.

## Card Model

```
Card {
  name: string              // full name; "Valki, God of Lies // Tibalt, Cosmic Impostor" for multi-face cards
  layout: string            // Scryfall layout: normal, split, transform, modal_dfc, adventure, ...
  faces: [Face]             // one entry for single-faced cards, two or more otherwise
  mana_value: number        // card-level, as Scryfall reports it
  color_identity: [W|U|B|R|G]
  keywords: [string]        // every keyword word appearing on the card, own or granted
  produced_colors: [W|U|B|R|G|C]   // which colors the card can make; no amounts
  commander_legal: bool
  source: "scryfall" | "definition" | "scryfall+definition"
}

Face {
  name: string
  mana_cost: ManaString     // "" when the face has no cost
  type_line: string
  oracle_text: string
  power: string | null      // string because it may be "*" or "1+*"
  toughness: string | null
}
```

A single-faced card is a card with one face whose name equals the card name. Every consumer works with faces, so multi-face cards need no special handling elsewhere.

`keywords` lists keyword words that appear anywhere on the card, including ones the card grants to other permanents; whether a keyword is the card's own is decided by `card-reading`.

## Name Matching

A requested name matches a card when, ignoring letter case and surrounding whitespace, it equals the card's full name or the name of any one of its faces. `Valki, God of Lies` and `Tibalt, Cosmic Impostor` both match the same card. No other matching is done: no fuzzy matching, no prefix matching, no punctuation folding.

## Fetching

Names not in the cache are fetched from Scryfall's collection endpoint (`POST /cards/collection`), which takes up to 75 name identifiers per request and reports which were not found. Requests carry a generic client name in `User-Agent` (`mtg-goldfishing/<version>`) and an `Accept` header, and are spaced at least 100 ms apart. Nothing identifying the person running the service is sent.

Three outcomes per name:

- **Found**: converted to the card model and written to the cache.
- **Not found**: reported to the caller by name. Not cached, so a later correction or a newly released card is picked up.
- **Unavailable**: the request failed (network error, timeout after 10 seconds, or a non-success response other than not-found). Reported to the caller as unavailable, distinct from not found.

Found cards are cached even when others in the same batch fail, so a retry fetches only what is still missing.

Every card Scryfall returns is matched back to the requested names by the name-matching rule above. A requested name that no returned card matches is **not found**, whatever Scryfall returned for it; a returned card is never accepted under a name it does not match.

A request that fails with a rate-limit or server-side status is retried once after one second before its names are reported unavailable. The 100 ms spacing applies to the whole process, across all callers. Cache writes replace any existing row for the same card, so two callers fetching the same card at once leave one correct row.

`commander_legal` is true only when Scryfall reports the card's Commander legality as `legal`.

### Faces by layout

When Scryfall gives a card a list of faces, each entry becomes a `Face`, taking its name, mana cost, type line, rules text, power and toughness from the entry and falling back to the card-level value for any of these the entry lacks. A card with no list of faces becomes one `Face` built from the card-level values. No layout is treated specially beyond this.

## Cache

One row per card, keyed by the lower-cased full name, with a lookup row for each face name. Cached data is kept until a caller asks for a refresh, in which case the named cards are fetched again and their rows replaced. If a refresh fetch is unavailable or reports a cached card as not found, the existing rows stay and the caller is told.

A face name maps to one card. If two cards share a face name, the name resolves to the card whose full name sorts first.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Lookup endpoint | Collection endpoint, 75 exact names per request | One request per card; Scryfall bulk data file | A 100-card deck is two requests. Per-card lookup is 100 requests; the bulk file is hundreds of megabytes for data mostly never used. |
| Name matching | Exact, case-insensitive, full name or any face name | Fuzzy matching | A typo must be an error. Fuzzy matching can resolve a typo to an unrelated card with no warning. |
| Cache lifetime | Until refresh is requested | Time-based expiry | Card text changes rarely; an expiry would add network calls to ordinary play for no visible benefit. Refresh is there for the rare change. |
| Not-found names | Not cached | Cache the miss | Misses are usually typos or cards not yet released; caching them would make a correct retry fail. |
| Power and toughness type | String | Integer | Scryfall reports `*` and `1+*`; forcing integers would lose them. `combat` decides what to do with non-numeric power. |

## Open Questions & Future Decisions

### Deferred
1. Tokens are described by the agent and are not fetched. Fetching token data from Scryfall would need set-specific identifiers.
2. Cards whose Scryfall name is shared by more than one object (art cards, tokens with a card's name) are not expected in deck lists; the collection endpoint returns the playable card.

## References

- `docs/high-level-design.md`
- Scryfall collection endpoint: `https://scryfall.com/docs/api/cards/collection`
