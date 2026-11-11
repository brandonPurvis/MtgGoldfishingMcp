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

A requested name matches a card when, ignoring letter case and surrounding whitespace, it equals the card's full name or the name of any one of its faces. `Valki, God of Lies` and `Tibalt, Cosmic Impostor` both match the same card.

Deck sites and players often write a multi-face card's full name with a single slash: `Fire/Ice`, `Fire / Ice` or `Fire//Ice` for `Fire // Ice`. So a requested name that contains `/` is also read as a list of face names, split at each slash separator: a `//`, or a `/` that is not part of a `//`, together with any spaces around it. Read that way, it matches a card whose faces, in order, have exactly those names, ignoring letter case and surrounding whitespace, with one part per face. A part that is empty matches no face, so `Fire///Ice` and `Fire / / Ice` match nothing.

The name as written comes first. `Summon: Choco/Mog` is a single-faced card with a slash in its own name; it is matched by that name, and a different card matching only the slash reading of a name is never chosen over the card the name itself matches.

The slash reading cannot turn a misspelled name into a different card: every part must equal a face name of the same card, in order, so a misspelling in any part leaves the name unmatched (`Fire/Ise` matches nothing). No other matching is done: no fuzzy matching, no prefix matching, no other punctuation folding.

The rule belongs to the card model in the domain, so both catalogs, and deck loading when it matches a card definition's name to a card, apply it alike. Card names given in a game are resolved by `game`'s own rule, among the names the game shows.

## Fetching

Names not in the cache are fetched from Scryfall's collection endpoint (`POST /cards/collection`), which takes up to 75 name identifiers per request and reports which were not found. A name that contains `/` is asked for in two spellings in the same request — as given, and with each slash separator written as ` // ` — because Scryfall knows a multi-face card only by its full name or a face name; each spelling counts toward the 75. Requests carry a generic client name in `User-Agent` (`mtg-goldfishing/<version>`) and an `Accept` header, and are spaced at least 100 ms apart. Nothing identifying the person running the service is sent.

Three outcomes per name:

- **Found**: converted to the card model and written to the cache.
- **Not found**: reported to the caller by name. Not cached, so a later correction or a newly released card is picked up.
- **Unavailable**: the request failed (network error, timeout after 10 seconds, or a non-success response other than not-found, once any retries below are spent). Reported to the caller as unavailable, distinct from not found.

Found cards are cached even when others in the same batch fail, so a retry fetches only what is still missing.

Every card Scryfall returns is matched back to the requested names by the name-matching rule above. A requested name that no returned card matches is **not found**, whatever Scryfall returned for it; a returned card is never accepted under a name it does not match.

### Rate limits and server errors

A request answered with status 429 (too many requests) or a server error (500 or above) is retried, up to three times, before its names are reported unavailable. Before each retry the adapter waits the longer of two times: a backoff of 1 second before the first retry, 2 before the second and 4 before the third; and the time the failed response's `Retry-After` header asks for. `Retry-After` is read in either of its forms, a whole number of seconds or an HTTP date measured by the service's own clock; one that cannot be read is ignored, and a date already past asks for no wait. An attempt that fails to complete — a network error or the 10-second timeout — ends the request, whether it was the first attempt or a retry, and its names are reported unavailable.

A `Retry-After` on a 429 or server-error response holds for the whole process: until the time it names, no request to Scryfall starts, from any caller. Scryfall uses it to say it is overloaded, and parallel deck loads in one process would otherwise each run into the same limit and spend their retries on it.

No attempt waits more than 20 seconds for a `Retry-After`. An attempt — first or retry — that, when it is due to start, would still have to wait longer is not sent, and the names of that request alone are reported unavailable at once; the lookup's other requests are made as usual: a tool call is not held open for minutes, and the agent learns the failure is temporary and may call again later. Without `Retry-After`, a request waits at most 7 seconds in all before its names are reported unavailable.

The 100 ms spacing applies to the whole process, across all callers, retries included. Cache writes replace any existing row for the same card, so two callers fetching the same card at once leave one correct row.

`commander_legal` is true only when Scryfall reports the card's Commander legality as `legal`.

### Faces by layout

When Scryfall gives a card a list of faces, each entry becomes a `Face`, taking its name, mana cost, type line, rules text, power and toughness from the entry and falling back to the card-level value for any of these the entry lacks. A card with no list of faces becomes one `Face` built from the card-level values. No layout is treated specially beyond this.

So the halves of a split card such as `Fire // Ice`, and the two parts of an adventure card, each become a face with its own mana cost and type line, taken from its face entry; the card-level mana cost Scryfall gives such a card, both costs joined by ` // `, is never a face's cost. Each face is castable as itself (see `play`). The card-level mana value and color identity are kept as Scryfall reports them.

## Cache

One row per card, keyed by the lower-cased full name, with a lookup row for each face name. Cached data is kept until a caller asks for a refresh, in which case the named cards are fetched again and their rows replaced. If a refresh fetch is unavailable or reports a cached card as not found, the existing rows stay and the caller is told.

A face name maps to one card. If two cards share a face name, the name resolves to the card whose full name sorts first.

Rows are keyed only by the names Scryfall gives — full names and face names — never by a spelling a caller used. A name with a slash finds its card in the cache as it is matched: by its own text first, then by its slash reading, so `Fire/Ice` is supplied from the `Fire // Ice` row without contacting Scryfall. A cached card found by the slash reading is used without asking Scryfall whether some uncached card bears the name as written; no card's name is another card's full name with ` // ` written as `/`, so this never chooses differently in practice.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Lookup endpoint | Collection endpoint, 75 exact names per request | One request per card; Scryfall bulk data file | A 100-card deck is two requests. Per-card lookup is 100 requests; the bulk file is hundreds of megabytes for data mostly never used. |
| Name matching | Exact, case-insensitive, full name or any face name | Fuzzy matching | A typo must be an error. Fuzzy matching can resolve a typo to an unrelated card with no warning. |
| A multi-face card's full name written with `/` | Read by the card model's name-matching rule, after the name as written, as a list of face names | Rewrite `/` to ` // ` while parsing the deck list; leave it unmatched and require ` // ` | The parser cannot tell `Fire/Ice` from `Summon: Choco/Mog`, whose own name has a slash, without the card data; rewriting would lose a real card. Deck sites export the slash form, so requiring ` // ` would turn ordinary lists into errors or card definitions. Reading the slash as a face separator, checked face by face, keeps every misspelling an error. |
| Retrying rate-limited and failed requests | Up to three retries, waiting the longer of a 1-2-4 second backoff and `Retry-After`; a `Retry-After` holds for the whole process; no wait over 20 seconds | One retry after a fixed second; retrying until Scryfall answers; a per-request `Retry-After` | One retry after a second fails again while Scryfall is still limiting. Unbounded retries hold a tool call open indefinitely. A per-request pause lets other callers in the process keep sending into a limit Scryfall has announced, which risks the client being blocked. Twenty seconds is long enough for a short limit to clear and short enough for a tool call. |
| Cache lifetime | Until refresh is requested | Time-based expiry | Card text changes rarely; an expiry would add network calls to ordinary play for no visible benefit. Refresh is there for the rare change. |
| Not-found names | Not cached | Cache the miss | Misses are usually typos or cards not yet released; caching them would make a correct retry fail. |
| Power and toughness type | String | Integer | Scryfall reports `*` and `1+*`; forcing integers would lose them. `combat` decides what to do with non-numeric power. |

## Open Questions & Future Decisions

### Deferred
1. Tokens are described by the agent and are not fetched. Fetching token data from Scryfall would need set-specific identifiers.
2. Cards whose Scryfall name is shared by more than one object (art cards, tokens with a card's name) are not expected in deck lists; the collection endpoint returns the playable card.
3. A card printed under another name — a reskinned printing, which Scryfall gives as a flavor name beside the card's own name — is not resolved by that printed name. Such a card is loaded by its own name, or by a card definition that gives its fields in full; a card definition cannot name another card to take its data from.

## References

- `docs/high-level-design.md`
- Scryfall collection endpoint: `https://scryfall.com/docs/api/cards/collection`
