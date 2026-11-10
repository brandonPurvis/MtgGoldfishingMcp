# Feature Proposal: Contested Games

Status: proposal. This document gathers the agreed behavior of contested games ahead of the design work. Its content moves into `docs/high-level-design.md`, the leaf designs under `docs/intent/` and their EARS specs; once it has, this document is deleted. Terms are defined in `GLOSSARY.md`.

## Problem

A goldfish game measures a deck's mana base and speed well, but not how it performs against opposition. The imaginary opponents never block, never remove a threat, never counter a spell and never wipe the board, so a deck that attacks with everything every turn always wins. An agent asked to imagine an opponent's blockers or removal makes those decisions itself, in its own deck's favor, and the decisions are not recorded as anything but its own plays.

## Goal

Give better data on how **one deck** performs in realistic games: against blockers, removal, board wipes and counterspells, which are what swing real games of Commander.

The judgment is always about one deck, the tested seat's. The opposing decks are the test's equipment. Comparing two decks (for example a new version against the previous one) is done outside the service, by running each as the tested seat and comparing the records, consistent with the HLD non-goal *Statistics and analysis*.

Goldfish games remain available and unchanged, because they remain the best measure of mana base and speed.

## The shape of a game

- Every game has exactly one **tested seat** and zero to three **opposing seats**, each backed by a loaded deck. `new_game` takes one deck id for each opposing seat. Any loaded deck may be used, including the tested seat's own (a mirror match).
- With **zero** opposing seats the game is a **goldfish game**: the tested seat against three imaginary opponents. Its tools, arguments, responses, status line, records and rules are exactly what they are today, including the pooled damage total against 120 and the per-opponent commander damage `Cmdr a/b/c`. An agent written against the current player brief notices no change.
- With **one to three** opposing seats the game is a **contested game**: an (N+1)-player Commander game with **no imaginary opponents**. One opposing seat is a duel; three is a full four-player pod.
- Every seat of a contested game has its own zones, life total, mana pool, land drop, commander tax, mulligans and pending choices.
- **Starting life** is set per seat in `new_game` and defaults to 40.
- **One seed** fixes every seat's shuffles and the turn order. A seat's shuffles do not depend on which other decks are present, so the tested seat's opening hand and draws for a seed are the same in a goldfish game and in any contested game. `new_game` may fix the tested seat's position in turn order (for example, to test being on the play); the other seats are then ordered by the seed.
- A **round** is one turn for each seat still in the game. The status line's `T<n>` is the number of turns the viewing seat has taken, so a tested deck's "kill turn" means the same in both kinds of game; records also keep the table's overall turn number. A turn limit in a contested game counts rounds.

## Who plays

- **The service still does not play.** Every decision for every seat comes from an agent. The HLD non-goal *Playing the game* stands.
- **The caller decides who plays which seat**: one agent playing every seat, or one agent per seat. The service supports both and does not prefer either.
- **Each seat's goal comes from its agent's brief**, written by the caller. The service ships **one player brief** for every seat, with a section on contested games; it tells every seat to play to win. A caller who wants a harsher test (an opposing seat whose only aim is to stop the tested deck) writes that into the opposing agent's brief.
- `new_game` returns **one unguessable seat id per seat**. Every game-scoped tool takes a seat id; a call made with it acts as that seat and sees what that seat may see.

## Hidden information

- **The service hides in its views.** Every response and `get_state` shows a seat only its own hand and library contents, and everything public: every battlefield, graveyard, exile and command zone, and every seat's hand and library sizes. A pending choice that reveals cards (a search, a look at a hand) shows them only to the seat that makes the choice.
- **The service does not police agents.** `get_log` is open to any seat at any time, even though the log holds every seat's hidden cards. Whether an agent reads it is the agent's, and its caller's, business.

## Interaction

### The stack

- A `play` or an `effect` in a contested game goes onto the **stack** carrying the delta its controller stated. It **resolves** once every other seat has passed on it, newest first. The service keeps the order and applies the deltas; it still does not work out what any card does. This replaces the HLD non-goal "does not manage the stack" with "keeps the stack's order but does not resolve cards".
- A response is itself a `play` or `effect`, goes on top of the stack and opens its own response window.
- A countered item's delta is discarded: a counterspell is a delta that counters the held item, and a countered spell's card goes to its owner's graveyard unless that delta moves it elsewhere.
- **A held delta applies as sent** when nothing resolved above it. When something did resolve above it, its controller receives a pending choice to **confirm or restate** the delta, because the board it was written against has changed. Example: a seat casts an Aura on its creature; in response, an opposing seat destroys the creature; the Aura's controller restates the delta as "the Aura to the graveyard".
- Triggered abilities are still recorded by their controller with `effect`, as today, and can be responded to like any other stack item.

### Response windows

- A response window opens:
  - whenever something is put on the stack;
  - after attackers are declared, so removal and tricks can be used on attackers;
  - in the end step, so a seat can act at the end of another seat's turn.
- No other step opens a window.
- In a window, seats are asked **one at a time, in turn order**, beginning with the seat after the one that acted. A response puts a new item on the stack and restarts the asking from the seat after the responder, including the original actor. The window closes when every seat has passed in succession. Asking in a fixed order keeps a seed reproducible; asking every seat at once and taking the first answer would let timing decide the game.
- **Automatic pass:** the service passes for a seat that has **no untapped permanents**. This leaks a little information and loses the rare free spell cast while tapped out (Force of Will, Deflecting Swat). Both are accepted: the aim is pushback against the tested deck, not perfect play. An automatic pass is the service deciding for a seat, so it is reported, under the tenet *Best guess, shown*.

### Decisions owed to another seat's effect

- A decision that another seat's effect requires (blocks, a discard, a sacrifice, "each opponent sacrifices a creature") is a **pending choice addressed to the seat that must make it**. The game waits for that seat's answer, which is applied with that seat's own delta.
- "Look at a target player's hand" is a pending choice for the looking seat that shows it the cards in that hand.

### Deltas across seats

- A delta may move, tap and untap **public** cards of any seat, change any seat's life, and **change control** of a permanent.
- A delta may not reach another seat's hand or library directly; discards, sacrifices and other choices belonging to that seat go through its pending choice.
- The service records each card's **owner** and **controller** separately.

### Triggers of seats that are not taking their turn

- A **step trigger** of a permanent controlled by a seat other than the active one (for example "at the beginning of each upkeep") becomes a reminder for that seat, which the game waits on as it waits on a pending choice.
- An **event trigger** (for example a creature dying in combat damage, where no window opens) is recorded by its controller with `effect` at that seat's next response window or own turn. The delay is a known, accepted gap.

## Combat

- `attack` names **a target for each attacker**: a seat. In a contested game every opponent is a seat; there are no pooled damage or imaginary opponents to attack.
- After attackers are declared, a response window opens (see above). Then each attacked seat receives a pending choice to **declare its blockers**.
- **The attacking seat's agent states the result of combat between creatures** as a delta: which creatures die and any other consequence. Power, toughness and keywords are changed by too many effects for the service to compute combat between creatures from card data.
- **The service still adds up combat damage to seats** from unblocked attackers' power, with the `damage` map to override it, and keeps commander damage per commander per seat. Life totals and the 21-commander-damage rule depend on this bookkeeping.

## Elimination and the end of a game

- A seat is **eliminated** when its life reaches 0 or one commander has dealt it 21 or more combat damage. The service applies elimination itself, because no single agent should declare another seat's loss. An opposing seat may also **concede**, which eliminates it.
- On elimination, the cards the seat owns leave the game, permanents it controlled but did not own return to their owners, and it takes no more turns and is skipped by response windows.
- The service raises a **notice** when the tested seat is eliminated or when every one of its opponents is. When the tested seat is eliminated the game is over for testing purposes, whatever happens among the other seats.
- **Only the tested seat calls `end_game`**, with the result and its verdict, and it may do so at any time. This is also how a stalled game is ended.

## Coordination between agents

- **`wait`**: a tool that holds the request open until the calling seat has something to do (its turn, a response window, a pending choice, a reminder), then returns what is asked of it and its status line. On timeout it returns, naming the seat the game is waiting on. An agent that plays every seat never needs `wait`, because every response says which seat acts next.
- A call from a seat that has nothing to do at that moment is refused as an **error**.
- **Digest:** every response to a seat in a contested game begins with a short digest of the other seats' **public** events since that seat's last call: casts, resolutions, attacks, blocks, life changes, eliminations. It is built from the same outcome events as responses and log entries, with hidden information left out. Without it, every agent would call `get_state` after every `wait`, against the HLD goal of needing `get_state` less than once per turn.
- **Mulligans:** before turn 1, every seat takes its own mulligans and sees only its own hand. Turn 1 begins once every seat has kept. Every seat draws on its first turn by default, as in today's first-turn draw rule.
- **Change number and resends:** the change number stays one per game and counts every seat's changes. A resend is recognised against **the sending seat's own** most recent change, because another seat may have acted between a lost response and its resend. A stale `after` is still an error.

## Records

- Every log entry and call record names the seat that made it.
- The log is one record for the whole game, holding every seat's actions, hidden zones included, and readable by any seat at any time.
- The record keeps the opposing seats' deck ids and their number, so analysis can tell a duel from a four-player game.
- The verdict belongs to the tested seat.

## Flows the behave scenarios cover

Every flow below has at least one behave scenario that drives the service through its tools, with in-memory adapters, one seat id per seat. The flows marked **(HTTP)** also run as end-to-end scenarios against the real process with SQLite, with a separate client for each seat. Each scenario cites the EARS IDs it checks, so the scenarios are written test-first once the specs exist.

### Starting a game
1. A contested game starts with one, two or three opposing seats, and each seat receives its own seat id. **(HTTP)** (GAME-056, GAME-074, GAME-077, APP-061)
2. The same decks and seed give the same turn order and the same opening hands every time. (GAME-080, GAME-082, GAME-087)
3. The tested seat's opening hand and draws for a seed are the same in a goldfish game and in a contested game. (GAME-063, GAME-083, GAME-085, GAME-086)
4. `new_game` fixes the tested seat's position in turn order; the other seats are ordered by the seed. (GAME-081, GAME-073)
5. Starting life is set per seat; a seat with none given starts at 40. (GAME-066, GAME-067, GAME-068)
6. An opposing seat may use the tested seat's own deck (a mirror match). (GAME-057)
7. Every seat takes its own mulligans and sees only its own hand; turn 1 begins once every seat has kept. (GAME-102, GAME-103, GAME-105, GAME-106, GAME-107, GAME-088)

### Turns
8. Turns pass from seat to seat in turn order; `T<n>` counts the viewing seat's own turns; a round is one turn for each seat still in the game. (TURN-031, TURN-033, TURN-040, TOOL-042)
9. A turn limit in a contested game counts rounds. (GAME-144, TURN-025)
10. A call from a seat that has nothing to do is an error. (GAME-118, APP-056, TOOL-050)
11. A step trigger of a permanent controlled by a seat other than the active one becomes a reminder for that seat, and the game waits on it. (TURN-048, TURN-051, TURN-052, GAME-111, READ-034)

### What a seat sees
12. A seat's responses and state show its own hand and library, every public zone, and only the sizes of other seats' hands and libraries. (GAME-088, GAME-089, GAME-121, GAME-122, APP-035, TOOL-051)
13. Every response to a seat begins with a digest of the other seats' public events since its last call, and the digest holds no hidden information. **(HTTP)** (APP-036, APP-037, GAME-091, REC-040, TOOL-035, TOOL-037)
14. Any seat may read the log at any time. (GAME-114, REC-055)

### The stack and response windows
15. A spell with no responses resolves with the delta it was cast with, once every other seat has passed. (STACK-003, STACK-014, STACK-016, STACK-024)
16. A counterspell cast in response resolves first and counters the held spell; the countered spell's delta is not applied. **(HTTP)** (STACK-030, STACK-031, STACK-039)
17. A response restarts the asking from the seat after the responder, including the original caster; items resolve newest first. (STACK-039, STACK-035, STACK-050)
18. A held delta applies as sent when nothing resolved above it; when something did, its controller confirms or restates it. (STACK-023, STACK-024, STACK-025, STACK-026, STACK-027)
19. A seat with no untapped permanents is passed automatically, and the automatic pass is reported. (STACK-046, STACK-047, STACK-048, REC-037)
20. After attackers are declared, a window opens in which another seat may remove an attacker. (STACK-036, STACK-044, CMBT-034)
21. In the end step, a window opens in which a seat may act at the end of another seat's turn. (STACK-037, STACK-045, TURN-056)
22. A triggered ability recorded with `effect` goes on the stack and can be responded to. (STACK-007)
23. An event trigger of a seat that is not taking its turn is recorded with `effect` at that seat's next window. (STACK-056, STACK-057)

### Effects across seats
24. An effect that requires another seat to discard or sacrifice gives that seat a pending choice, and the game waits for its answer. (PLAY-097, PLAY-098, PLAY-099, GAME-109)
25. Looking at another seat's hand shows those cards to the looking seat only. (PLAY-102, PLAY-103, GAME-090)
26. A delta may destroy or exile another seat's permanent and change any seat's life. (PLAY-087, PLAY-088, PLAY-091, PLAY-092, PLAY-095)
27. A delta may change control of a permanent; owner and controller are kept separately. (PLAY-094, GAME-100, GAME-101)
28. A delta that reaches into another seat's hand or library is refused. (PLAY-079, GAME-096)

### Combat
29. `attack` names a seat for each attacker, and each attacked seat declares blockers through a pending choice. **(HTTP)** (CMBT-030, CMBT-031, CMBT-037, CMBT-039)
30. The attacking seat states what happens to creatures in combat; the service adds up combat damage to seats and commander damage per seat. (CMBT-051, CMBT-061, CMBT-062)

### Elimination and the end of a game
31. A seat at 0 life is eliminated: the cards it owns leave the game, permanents it controlled but did not own return to their owners, and it takes no more turns and is skipped by response windows. (GAME-129, GAME-132, GAME-133, GAME-136, TURN-031, STACK-062)
32. A seat dealt 21 combat damage by one commander is eliminated. (GAME-130, CMBT-062, CMBT-065)
33. An opposing seat may concede, which eliminates it. (GAME-131)
34. A notice is raised when the tested seat is eliminated, and when every opponent of the tested seat is eliminated. (GAME-142, GAME-143)
35. Only the tested seat may call `end_game`, and it may do so at any time, including while the game waits on another seat. (GAME-045, GAME-131, GAME-148)

### Coordination
36. `wait` returns when the seat has something to do, with what is asked of it. **(HTTP)** (APP-063, APP-064)
37. `wait` times out and names the seat the game is waiting on. (APP-066)
38. A resend is recognised against the sending seat's own most recent change, even when another seat acted in between. **(HTTP)** (GAME-036, GAME-126, APP-055)
39. A changing call with a stale `after` is an error. (GAME-037, GAME-127)
40. A full game played by four seats, each through its own client, produces one complete log. **(HTTP)** (REC-027, APP-015, APP-077)

### Records
41. Every log entry and call record names the seat that made it, and the record holds the opposing seats' deck ids. (REC-028, REC-052, REC-056)

### Goldfish games
42. A goldfish game's tested seat id is its game id, and its responses show no digest, stack or response window. (GAME-076, APP-040, TOOL-039, STACK-001)

## Alternatives considered

| Choice | Selected | Rejected | Why |
|---|---|---|---|
| What a game is for | A verdict on the tested deck | A head-to-head comparison of two decks | One game is weak evidence that one deck beats another; comparison belongs to analysis outside the service. |
| Form of the opposition | Seats backed by loaded decks | A seeded pressure profile (scripted blockers, removal and wipes for the imaginary opponents) | A profile is a script rather than a deck, and would have the service decide what the opposition does. It may become a separate feature. |
| Imaginary opponents in a contested game | None | Imaginary opponents filling empty seats | One opposing seat with two imaginary opponents would aim all of its removal and attacks at the tested seat, a harsher test than any real game; a duel is a real format. |
| Holding spells for responses | A stack whose items carry their delta | Cast, then state the delta on resolution | Two calls for every spell even when no one responds. |
| | | Resolve immediately, react afterwards | Counterspells and responses become impossible. |
| Who is asked in a window | One seat at a time, in turn order | Every seat at once, first answer wins | Timing would decide the game, and a seed would no longer reproduce it. |
| Which steps open windows | On the stack, after attackers, the end step | Every step, as in Magic's priority rules | Too many passes for the pushback gained. |
| Reducing passes | Automatic pass when a seat has no untapped permanents | Stops chosen by each seat; guessing from card text whether a response is possible | Stops add a configuration surface not yet needed; a wrong guess from card text cannot be undone. |
| Combat between creatures | Stated by the attacking agent | Computed by the service from power, toughness and keyword readings | Too many effects change power, toughness and keywords for card data to be reliable. |
| Hidden information in the log | `get_log` open to all | Refused during a game | The service hides in its views and does not police what an agent chooses to read. |
| An opposing seat's aim | Play to win, as a real player | Archenemy: stop the tested deck at all costs | Realism is the goal; a caller can still brief an archenemy. |
| Player briefs | One brief for every seat | A separate brief for opposing seats | The tools and rules are the same for every seat. |

## Architecture

The architecture is chosen for code that stays readable, maintainable and extensible over the long term, for human and agent maintainers alike.

- **Seats live inside the one `Game` aggregate.** The game keeps table-level state (seed, change number, turn, step, status, notices, the stack, turn order). Player-level state (zones, life, mana pool, land drop, commander tax, mulligans, pending choices, reminders) moves into a seat held by the game, and cards carry an owner and a controller. A goldfish game is a game with one seat that also keeps the imaginary-opponent tallies. Every rule keeps one home, scoped to the acting seat; a cross-seat delta is one transaction on one aggregate; the existing per-game ordering and change number apply unchanged. Rejected: a separate contested-game aggregate beside the goldfish `Game`, because turn, play, payment and combat rules would either fork and drift apart or be extracted into shared services, which is the same refactor plus a second aggregate to persist and test; and a table aggregate over one goldfish-style game per seat, because turn, step and change number would live in two places, cross-seat deltas would span several games, and a goldfish game would need its own code path or become a one-seat table.
- **The stack and response windows are a new leaf component, `stack`**, separate from `play`, so that it can grow in complexity without entangling the rest of the design. It owns held plays and effects, response windows, asking in turn order, automatic passes, and confirming or restating a held delta.

## Tenets

- *It's the agent's simulation* also covers hidden information: the service hides what a seat may not see, but does not police what an agent chooses to look at.
- A new tenet, *Pushback over fidelity*, ranks second, below *It's the agent's simulation*: when an exact model of Magic's timing or hidden information would cost far more than an approximation that still lets the opposition push back, take the approximation.

## Left to the design and spec phases

- The status line and response formats in a contested game, including the digest's wording.
- Tool names and parameters, including how `new_game` takes opposing decks, starting life and the tested seat's position, and how the attacking seat states the result of combat.
- The `wait` timeout and the port behind it.

## Milestones

Each milestone lands as a tests-first PR, whose new tests are marked as expected to fail, then a code PR that makes them pass.

1. **M1 — Ports as abstract base classes.** Every port becomes an abstract base class that its implementations inherit from; no behavior changes.
2. **M2 — Seats inside the game aggregate.** The game holds a table and its seats, cards carry an owner and a controller, and a goldfish game is the one-seat case. Every goldfish behavior stays as it is.
3. **M3 — Contested games without the stack.** `new_game` with opposing seats, seat ids and seat numbers, turn order, what a seat may see, mulligans for every seat, turn rotation and rounds, deltas reaching other seats, pending choices addressed to a seat, combat with blocks and combat results, elimination and conceding, the digest, `wait`, and records naming seats. Plays resolve at once.
4. **M4 — The stack and response windows.** Held plays and effects, `pass`, the three windows, asking in turn order, automatic passes, countering, confirming or restating a disturbed item, and reminders for seats other than the active seat.
5. **M5 — The player brief and HTTP end-to-end scenarios.** The brief's contested section, the server instructions, and the behave scenarios that run against the real process with a client per seat.
