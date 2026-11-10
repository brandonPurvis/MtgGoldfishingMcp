---
parent: high-level-design
prefix: GAME
---

# Game

## Context and Design Philosophy

A game is one goldfish game: one agent, one loaded deck, one seed. This component owns what a game *is* — its cards, zones and counters — and the tools that begin it, show it and end it: `new_game`, `mulligan`, `get_state`, `end_game`. How the game moves forward belongs to `turn`, `play` and `combat`.

Two promises shape everything here. The agent never learns the order of its library. And the same loaded deck with the same seed always produces the same shuffles.

## Game State

```
Game {
  game_id: string            // "g" + 10 random characters
  deck_id: string
  seed: int
  turn_limit: int | null
  draw_first_turn: bool
  status: "mulligan" | "active" | "pending_choice" | "ended"
  turn: int                  // 0 during mulligans
  step: Step | null          // null during mulligans
  change: int                // the change number: accepted changing calls so far
  last_change: { tool, arguments, summary, events } | null   // the most recent accepted changing call and what it reported
  life: int                  // starts at 40
  land_drops_used: int
  turn_stats: {              // reset on entering untap
    mana_available: int      // see records
    mana_spent: int
    payments: [Payment]      // each payment made this turn
  }
  mana_pool: ManaPool        // see payment
  mulligans: int
  shuffles: int              // number of shuffles performed so far
  commander_casts: { [instance id]: int }      // casts from the command zone
  damage_dealt: int          // pooled across the three opponents
  commander_damage: { [instance id]: [int, int, int] }   // per commander, per opponent
  cards: [CardInstance]
  library: [instance id]     // ordered, top first
  declared_attack: Attack | null   // see combat
  pending_choice: PendingChoice | null   // see play
  notices: [Notice]
  result: { outcome, notes } | null
}

CardInstance {
  id: string                 // "c1", "c2", ...
  name: string               // card name, or token name
  zone: "library" | "hand" | "battlefield" | "graveyard" | "exile" | "command"
  face: int                  // index of the face in play; 0 unless the agent played another
  tapped: bool
  counters: { [kind]: int }
  is_token: bool
  is_commander: bool
  entered_turn: int | null   // turn it entered the battlefield
  token: TokenSpec | null    // see play
  definition: Card | null    // card data for a card brought in from outside the game
}
```

Instance ids are assigned at game creation in a fixed order — commanders first, then the remaining cards, each group sorted by lower-cased card name compared character by character, copies of one card adjacent — and later instances (tokens, cards from outside the game) take the next number. Fixed assignment is part of reproducibility.

A card that is not on the battlefield is always on its first face: `face` returns to 0 whenever a card leaves the battlefield.

Game ids are random and long enough to be unguessable, because knowing a game id is the only thing needed to act on that game.

## Shuffling

The library's order before the first shuffle is its instance-id order. A shuffle is a Fisher–Yates shuffle driven by a generator seeded with the integer value of the SHA-256 hash of the text `<seed>:<n>`, where *n* is the count of shuffles so far, so the *n*th shuffle of a game depends only on the seed, *n*, and the library's contents at that moment. The shuffle draws only on the generator's basic uniform float, the one output Python guarantees stable across versions.

If `seed` is not given to `new_game`, the service generates one and returns it, so any game can be reproduced afterwards. The seed is visible to the playing agent; an agent that replays a deck and seed it has already played knows what it will draw, and whoever starts the games decides when that is acceptable.

## The Change Number

Every accepted call that changes a game increases the game's change number by one, and every response about the game shows it. Any changing tool accepts an optional `after` argument: the change number the agent last saw.

- `after` equal to the game's change number: the call is applied.
- `after` one less than the game's change number, and the call's tool and arguments (other than `after`) are the same as the game's most recent accepted change: the call is a resend. It is not applied again; the original summary and events are reported again with a statement that the call was already applied. Since nothing has changed since, they render to the original response.
- any other `after`: an error saying the game is now at a different change number, so the agent knows its picture is stale.
- `after` omitted: the call is applied with no check.

Refused calls do not increase the change number.

## Naming Cards in Calls

Wherever a tool takes a card name, the agent may give the card's full name, the name of one of its faces, or an instance id. Matching ignores letter case. A name is resolved among the instances in the zone the operation expects. When several instances match:

- the operation's natural candidate wins — an untapped one for tapping or paying, a tapped one for untapping;
- then the one with the lowest instance id.

When the matching instances differ from one another (tapped state, counters, face), the response names the instance chosen by id so the agent can see which one was used. A name that matches nothing in the expected zone is an error; when the same name exists in a different zone the error says where.

A name given more than once in one list means that many different instances: `tap: ["Forest", "Forest"]` taps two Forests. If there are fewer matching instances than the name was given, that is an error. An instance id given twice in one list is an error.

Where a tool takes a map keyed by card name, an instance id is accepted as a key in the same way, which is how one of several identical permanents is singled out.

## `new_game`

```
new_game(deck_id, seed?, turn_limit?, draw_first_turn?)
```

Creates the game, places commanders in the command zone, shuffles the rest into the library, and deals seven cards. The game starts in status `mulligan`. The response gives the game id, the seed and the opening hand. `draw_first_turn` defaults to true.

An unknown `deck_id` is an error. `turn_limit`, when given, must be a positive integer.

## `mulligan`

```
mulligan(game_id, keep, bottom?, override?)
```

With `keep: false` the hand returns to the library, the library is shuffled, and seven new cards are dealt. With `keep: true` the agent keeps the hand, having put `bottom` cards from it on the bottom of the library in the order given. The first mulligan is free: after *k* mulligans the number of cards to bottom is *k* − 1, or zero if the agent has not mulliganed, and never more than seven.

Keeping with the wrong number of cards in `bottom` is a rule check; with `override` the cards named are bottomed as given. Naming a card in `bottom` that is not in hand is an error, as is giving `bottom` with `keep: false`.

Keeping starts the game: status becomes `active` and the game proceeds through the untap, upkeep and draw steps of turn 1 to the first main step, exactly as `advance` would, drawing a card unless `draw_first_turn` is false. The response shows any card drawn.

## `get_state`

```
get_state(game_id, detail?)
```

`detail: "summary"` (the default) lists the hand, the battlefield, the graveyard, the command zone and current notices. Each battlefield permanent is shown with its instance id, tapped state, counters, and what the service has read of it: the mana it makes, haste or vigilance it has or is granted, and the steps it has a trigger in. `detail: "full"` adds exile, the number of cards in the library, per-commander cast counts and damage, and the payments made this turn. Library contents and order are never returned.

`get_state` is accepted in every status, including `ended`.

## End Conditions and Notices

The service watches for conditions that would normally end a game. When one is first reached it adds a notice, and the notice appears on every later response until the game ends.

| Notice | Reached when |
|---|---|
| Damage | `damage_dealt` is 120 or more. |
| Commander damage | For each of the three opponents, some one commander has dealt 21 or more to that opponent. |
| Turn limit | The game enters the turn whose number equals `turn_limit`. |
| Life | The agent's life is 0 or less. |
| Empty library | A draw was attempted with too few cards in the library. The draw takes what cards there are. |

A notice never changes the game's status and never stops play. Once raised, a notice stays even if its condition stops holding.

## `end_game`

```
end_game(game_id, result, notes?)
```

Ends the game with `result` of `win`, `loss` or `stalled` and the agent's free-text verdict. The agent's result is trusted; no condition is required. Any pending choice and any declared attack are discarded, and a snapshot is written for the turn in progress if it does not have one (see `records`). After this the status is `ended` and only `get_state` and `get_log` are accepted.

## Status and What Is Accepted

| Status | Accepted tools |
|---|---|
| `mulligan` | `mulligan`, `get_state`, `get_log`, `end_game` |
| `active` | everything except `mulligan` and `choose` |
| `pending_choice` | `choose`, `get_state`, `get_log`, `end_game` |
| `ended` | `get_state`, `get_log` |

A tool called in a status that does not accept it is an error that names the status and what can be done instead.

A resend of the game's most recent change is answered as such whatever the status (see The Change Number).

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Opponents' life | One pooled damage total against 120 | A life total per opponent | A goldfish game has no reason to choose which opponent takes ordinary damage; pooling removes a decision that carries no information. Commander damage stays per opponent because 21 from one commander is a per-opponent rule. |
| Commander damage with two commanders | Tracked per commander | One combined track | The 21-damage rule counts each commander separately. |
| Shuffle generator | Own Fisher–Yates over the seeded generator's basic float | The standard library's `shuffle` | Only the basic float is guaranteed stable across Python versions; a seed must keep meaning the same game. |
| First turn draw | Draws by default, switchable per game | Never draw; always draw | A goldfish game stands in for a four-player game, where no one skips the first draw. The switch lets an agent model going first in a two-player game. |
| End conditions | Notices only | End the game automatically | The agent may want to keep playing to see how far ahead the deck is, or may judge a win by a route the service cannot see. |
| Mulligan rule | London mulligan with one free mulligan | Seven-card redraws only | This is the Commander mulligan rule. |
| Names versus ids | Names everywhere, ids accepted and shown when instances differ | Ids everywhere | Names are what the agent already thinks in and cost nothing to look up. |
| `end_game` while a choice is pending | Allowed | Blocked until the choice is made | An agent that has decided the game is over should not be forced to resolve a choice first. |

## Open Questions & Future Decisions

### Deferred
1. Results beyond `win`, `loss` and `stalled`.
2. Poison counters and other alternative loss tracks for opponents; the agent declares such wins.

## References

- `docs/high-level-design.md`
- `docs/intent/deck/deck-design.md`
- `docs/intent/turn/turn-design.md`
