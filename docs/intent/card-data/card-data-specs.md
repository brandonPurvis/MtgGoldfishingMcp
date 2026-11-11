# Card Data — Specs

Design: `card-data-design.md`. Prefix: `CARD`.

## Card model

- [x] **CARD-001**: The card model shall represent every card as a `Card` holding one or more `Face` values, where a single-faced card has exactly one face whose name equals the card's name.
- [x] **CARD-002**: The card model shall hold a face's power and toughness as text, preserving non-numeric values such as `*` and `1+*`.
- [x] **CARD-003**: When converting a Scryfall card that lists faces, the Scryfall adapter shall build one `Face` per listed face, taking name, mana cost, type line, rules text, power and toughness from the face entry and using the card-level value for any of these the face entry lacks.
- [x] **CARD-004**: When converting a Scryfall card that lists no faces, the Scryfall adapter shall build a single `Face` from the card-level values.
- [x] **CARD-005**: The Scryfall adapter shall set a card's `commander_legal` to true only when Scryfall reports the card's Commander legality as `legal`.

## Name matching

- [ ] **CARD-006**: When resolving a requested card name, the card catalog shall treat the name as matching a card if, ignoring letter case and surrounding whitespace, it equals the card's full name or the name of one of the card's faces, and shall treat it as matching a card by no other rule than this one and CARD-021.
- [ ] **CARD-021**: When resolving a requested card name that contains `/`, the card catalog shall also treat the name as matching a card if the name, split at each slash separator (a `//`, or a `/` that is not part of a `//`, together with the spaces around it), has exactly one part for each face of the card and each part equals the name of the face in the same position, ignoring letter case and surrounding whitespace.
- [ ] **CARD-022**: If, among the cards the card catalog has for a lookup, whether cached or returned by Scryfall, a requested card name matches one card under CARD-006 and a different card only under CARD-021, then the card catalog shall resolve the name to the card it matches under CARD-006.
- [x] **CARD-007**: If a face name is shared by more than one cached card, then the card catalog shall resolve that name to the card whose full name sorts first.

## Fetching from Scryfall

- [ ] **CARD-008**: When asked for card names that are not in the cache, the Scryfall adapter shall request them from Scryfall's collection endpoint with at most 75 name identifiers in each request, the spellings of one requested name (CARD-023) always in the same request.
- [ ] **CARD-023**: When the Scryfall adapter requests from Scryfall a card name that contains `/`, it shall put in the same request, as a second name identifier, the name with each slash separator (CARD-021) written as ` // `, unless that spelling equals the name as given, ignoring surrounding whitespace.
- [x] **CARD-009**: The Scryfall adapter shall send a `User-Agent` of the form `mtg-goldfishing/<version>` and an `Accept` header on every request, and shall send nothing that identifies the person running the service.
- [x] **CARD-010**: The Scryfall adapter shall leave at least 100 ms between the starts of any two requests to Scryfall made by the same process.
- [x] **CARD-011**: When Scryfall returns a card, the Scryfall adapter shall accept it for a requested name only if that name matches the returned card under the name-matching rule (CARD-006).
- [x] **CARD-012**: If no card returned by Scryfall matches a requested name, then the Scryfall adapter shall report that name as not found.
- [x] **CARD-013**: If a request to Scryfall fails with a network error, exceeds 10 seconds, or returns a non-success status other than not-found, then the Scryfall adapter shall report the names in that request as unavailable, distinct from not found.
- [ ] **CARD-014**: If a request to Scryfall returns status 429 or a server-error status (500 or above), then the Scryfall adapter shall retry that request, up to three times, before reporting its names as unavailable.
- [ ] **CARD-031**: If an attempt at a request to Scryfall, whether the first attempt or a retry, fails with a network error, exceeds 10 seconds, or returns a non-success status other than 429 or a server-error status, then the Scryfall adapter shall make no further attempt at that request.
- [ ] **CARD-026**: Before retrying a request to Scryfall, the Scryfall adapter shall wait the longer of a backoff of 1 second before the first retry, 2 seconds before the second and 4 seconds before the third, and the time the failed response's `Retry-After` header asks for.
- [ ] **CARD-027**: When a response from Scryfall carries a `Retry-After` header, the Scryfall adapter shall read it as a whole number of seconds to wait or as an HTTP date to wait until by the service's own clock, a date already past asking for no wait.
- [ ] **CARD-028**: If a `Retry-After` header from Scryfall is neither a whole number of seconds nor an HTTP date, then the Scryfall adapter shall ignore it.
- [ ] **CARD-029**: When a response from Scryfall with status 429 or a server-error status carries a `Retry-After` header, the Scryfall adapter shall start no request to Scryfall, for any caller in the same process, until the time that header asks for has passed.
- [ ] **CARD-030**: If, when an attempt at a request to Scryfall (the first attempt or a retry) is due to start, the time still to wait for a `Retry-After` header is more than 20 seconds, then the Scryfall adapter shall not send it and shall report the names in that request, and only those, as unavailable without waiting.
- [x] **CARD-020**: If Scryfall returns a card for a requested name that the card model cannot hold, then the Scryfall adapter shall report that name as unavailable and store nothing in the cache for it.

## Cache

- [x] **CARD-015**: When Scryfall returns a card that matches a requested name, the Scryfall adapter shall store the card in the cache, including when other names in the same lookup were not found or unavailable.
- [x] **CARD-016**: The Scryfall adapter shall not store anything in the cache for a name reported as not found or unavailable.
- [x] **CARD-017**: While a card is in the cache and no refresh is requested, the card catalog shall supply that card from the cache without contacting Scryfall.
- [ ] **CARD-024**: When a requested card name matches no cached card under CARD-006 but matches a cached card under CARD-021, and no refresh is requested, the card catalog shall supply that cached card without contacting Scryfall.
- [x] **CARD-018**: When a lookup requests a refresh, the Scryfall adapter shall fetch every requested name from Scryfall again and replace the cached card for each name that is found.
- [x] **CARD-019**: If a refresh lookup reports a cached card as unavailable or not found, then the Scryfall adapter shall keep the existing cached card and report the name's refresh outcome to the caller.
