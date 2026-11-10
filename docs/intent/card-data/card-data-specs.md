# Card Data — Specs

Design: `card-data-design.md`. Prefix: `CARD`.

## Card model

- [x] **CARD-001**: The card model shall represent every card as a `Card` holding one or more `Face` values, where a single-faced card has exactly one face whose name equals the card's name.
- [x] **CARD-002**: The card model shall hold a face's power and toughness as text, preserving non-numeric values such as `*` and `1+*`.
- [x] **CARD-003**: When converting a Scryfall card that lists faces, the Scryfall adapter shall build one `Face` per listed face, taking name, mana cost, type line, rules text, power and toughness from the face entry and using the card-level value for any of these the face entry lacks.
- [x] **CARD-004**: When converting a Scryfall card that lists no faces, the Scryfall adapter shall build a single `Face` from the card-level values.
- [x] **CARD-005**: The Scryfall adapter shall set a card's `commander_legal` to true only when Scryfall reports the card's Commander legality as `legal`.

## Name matching

- [x] **CARD-006**: When resolving a requested card name, the card catalog shall treat the name as matching a card only if, ignoring letter case and surrounding whitespace, it equals the card's full name or the name of one of the card's faces.
- [x] **CARD-007**: If a face name is shared by more than one cached card, then the card catalog shall resolve that name to the card whose full name sorts first.

## Fetching from Scryfall

- [x] **CARD-008**: When asked for card names that are not in the cache, the Scryfall adapter shall request them from Scryfall's collection endpoint in batches of at most 75 names.
- [x] **CARD-009**: The Scryfall adapter shall send a `User-Agent` of the form `mtg-goldfishing/<version>` and an `Accept` header on every request, and shall send nothing that identifies the person running the service.
- [x] **CARD-010**: The Scryfall adapter shall leave at least 100 ms between the starts of any two requests to Scryfall made by the same process.
- [x] **CARD-011**: When Scryfall returns a card, the Scryfall adapter shall accept it for a requested name only if that name matches the returned card under the name-matching rule (CARD-006).
- [x] **CARD-012**: If no card returned by Scryfall matches a requested name, then the Scryfall adapter shall report that name as not found.
- [x] **CARD-013**: If a request to Scryfall fails with a network error, exceeds 10 seconds, or returns a non-success status other than not-found, then the Scryfall adapter shall report the names in that request as unavailable, distinct from not found.
- [x] **CARD-014**: If a request to Scryfall returns a rate-limit or server-error status, then the Scryfall adapter shall retry that request once after one second before reporting its names as unavailable.
- [x] **CARD-020**: If Scryfall returns a card for a requested name that the card model cannot hold, then the Scryfall adapter shall report that name as unavailable and store nothing in the cache for it.

## Cache

- [x] **CARD-015**: When Scryfall returns a card that matches a requested name, the Scryfall adapter shall store the card in the cache, including when other names in the same lookup were not found or unavailable.
- [x] **CARD-016**: The Scryfall adapter shall not store anything in the cache for a name reported as not found or unavailable.
- [x] **CARD-017**: While a card is in the cache and no refresh is requested, the card catalog shall supply that card from the cache without contacting Scryfall.
- [x] **CARD-018**: When a lookup requests a refresh, the Scryfall adapter shall fetch every requested name from Scryfall again and replace the cached card for each name that is found.
- [x] **CARD-019**: If a refresh lookup reports a cached card as unavailable or not found, then the Scryfall adapter shall keep the existing cached card and report the name's refresh outcome to the caller.
