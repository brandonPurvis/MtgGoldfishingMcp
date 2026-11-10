---
parent: high-level-design
prefix: GAME
---

# Game

## Context and Design Philosophy

A game is one goldfish game or one contested game: a table of seats, each backed by a loaded deck, and one seed. This component owns what a game *is* — its table, its seats, its cards and zones, and what each seat may see — and the tools that begin it, show it and end it: `new_game`, `mulligan`, `get_state`, `end_game`. How the game moves forward belongs to `turn`, `play`, `stack` and `combat`.

Three promises shape everything here. No agent learns the order of a library. The same loaded decks with the same seed always produce the same shuffles and the same turn order. And a seat's shuffles depend only on the seed and that seat's own deck, so the tested seat's draws for a seed are the same in a goldfish game and in any contested game.

A goldfish game is the one-seat case of the same model: one seat, the tested seat, against three imaginary opponents. Everything this design says about seats holds for it; what only a goldfish game has — pooled damage and commander damage against imaginary opponents — is kept by the game for that seat.

## Game State

```
Game {                         // the table
  game_id: string              // "g" + 10 random characters; also the tested seat's seat id
  seed: int
  turn_limit: int | null       // in rounds
  draw_first_turn: bool
  status: "mulligan" | "active" | "pending_choice" | "ended"   // pending_choice while any pending choice waits
  seats: [Seat]                // in turn order; seats[0] is seat number 1
  active: int | null           // seat number of the active seat; null during mulligans
  turn: int                    // table turn number: turns taken by all seats; 0 during mulligans
  round: int                   // 0 during mulligans
  step: Step | null            // null during mulligans
  change: int                  // the change number
  stack: [StackItem]           // see stack; always empty in a goldfish game
  window: Window | null        // the open response window, see stack
  pending: [PendingChoice]     // see play; each addressed to one seat, answered in order
  declared_attack: Attack | null   // see combat
  notices: [Notice]
  result: { outcome, notes } | null
  cards: [CardInstance]        // every seat's cards
  imaginary: {                 // a goldfish game only
    damage_dealt: int          // pooled across the three imaginary opponents
    commander_damage: { [instance id]: [int, int, int] }
  } | null
}

Seat {
  number: int                  // place in turn order, from 1
  seat_id: string              // the tested seat's is the game id
  deck_id: string
  tested: bool
  shuffle_key: string          // "" for the tested seat; "o1", "o2", "o3" for opposing seats
  life: int
  eliminated: bool
  kept: bool                   // has kept its opening hand
  mulligans: int
  shuffles: int                // shuffles of this seat's library so far
  turns: int                   // turns this seat has begun
  land_drops_used: int
  turn_stats: { mana_available, mana_spent, payments }   // see records; reset on this seat's untap
  mana_pool: ManaPool          // see payment
  commander_casts: { [instance id]: int }
  commander_damage: { [instance id]: { [seat number]: int } }   // combat damage dealt by each commander to each other seat
  library: [instance id]       // ordered, top first
  last_change: { tool, arguments, summary, events, change } | null   // this seat's most recent accepted change
  reminders: [Reminder]        // see turn
}

CardInstance {
  id: string                   // "c1", "c2", ...: unique across the game
  name: string
  owner: int                   // seat number
  controller: int              // seat number; equals owner unless control was changed
  zone: "library" | "hand" | "battlefield" | "graveyard" | "exile" | "command" | "stack"
  face: int
  tapped: bool
  counters: { [kind]: int }
  is_token: bool
  is_commander: bool
  entered_turn: int | null     // table turn it entered the battlefield
  token: TokenSpec | null
  definition: Card | null
}
```

The **table** is what all seats share; a **seat** is what one player has. Every rule of play is written against the acting seat — the seat whose call is being applied — and reaches other seats only where the rule says so.

A card that is not on the battlefield is always on its first face. A card that leaves the battlefield returns to its owner's control.

### Instance ids

Instance ids are assigned at game creation seat by seat: the tested seat first, then the opposing seats in the order `new_game` lists their decks. Within a seat the order is commanders first, then the remaining cards, each group sorted by lower-cased card name compared character by character, copies of one card adjacent. Later instances (tokens, cards from outside the game) take the next number. So the tested seat's cards have the same ids in a goldfish game and in any contested game on the same deck.

### Seat ids and seat numbers

A seat has two names. Its **seat id** is random and unguessable, and a call made with it acts as that seat; the tested seat's seat id is the game id. Its **seat number** is its place in turn order, by which calls and responses name seats to one another (`S2`). A goldfish game has one seat, number 1, whose seat id is the game id, so its calls are made exactly as they always were.

## Turn Order

In a contested game the seats' order is drawn from the seed: a Fisher–Yates shuffle, as below, of the list (tested seat, then opposing seats in `new_game` order), driven by a generator seeded from the text `<seed>:order`. When `new_game` gives `position`, the opposing seats alone are shuffled that way and the tested seat is placed at that position.

## Shuffling

Each seat's library is shuffled on its own stream. Before its first shuffle a library is in instance-id order. A seat's shuffle is a Fisher–Yates shuffle driven by a generator seeded with the integer value of the SHA-256 hash of `<seed>:<n>` for the tested seat and `<seed>:<shuffle_key>:<n>` for an opposing seat, where *n* is the count of that seat's shuffles so far. The *n*th shuffle of a seat depends only on the seed, its shuffle key, *n*, and its library's contents at that moment. The generator is Python's `random.Random`; the shuffle walks *i* from the last index down to 1, swapping index *i* with index ⌊`random()`·(*i*+1)⌋, drawing only on the generator's basic uniform float, the one output Python guarantees stable across versions.

If `seed` is not given to `new_game`, the service generates one and returns it. The seed is visible to the playing agents; an agent that replays decks and a seed it has already played knows what every seat will draw, and whoever starts the games decides when that is acceptable.

## The Change Number

Every accepted call that changes a game increases the game's change number by one, whichever seat made it, and every response about the game shows it. Any changing tool accepts an optional `after`: the change number the calling seat last saw.

- `after` equal to the game's change number: the call is applied.
- the call's tool and arguments (other than `after`) are the same as the calling seat's most recent accepted change, and `after` is one less than that change's number: the call is a resend. It is not applied again; that change's summary and events are reported again with a statement that the call was already applied.
- any other `after`: an error saying the game is now at a different change number.
- `after` omitted: the call is applied with no check.

Refused calls do not increase the change number. In a goldfish game the calling seat's most recent change is the game's most recent change, so a resend is recognised exactly as it always was.

## Naming Cards in Calls

Wherever a tool takes a card name, the agent may give the card's full name, the name of one of its faces, or an instance id. Matching ignores letter case. A name is resolved among the instances in the zone the operation expects. A name for a card in a hidden zone — hand or library — is resolved only among the acting seat's own cards. A name for a card in a public zone or on the stack is resolved first among the cards the acting seat controls, then among other seats' cards in turn order from the acting seat; an instance id singles out any card. When several instances match:

- the operation's natural candidate wins — an untapped one for tapping or paying, a tapped one for untapping;
- then the one with the lowest instance id.

When the matching instances differ from one another (tapped state, counters, face, controller), the response names the instance chosen by id. A name that matches nothing in the expected zone is an error; when the same name exists in a different zone the error says where.

A name given more than once in one list means that many different instances. Instance ids in a list are resolved first, and each name then takes a matching instance no id or earlier name has taken. If there are fewer matching instances than the name was given, that is an error. An instance id given twice in one list is an error.

Where a tool takes a map keyed by card name, an instance id is accepted as a key in the same way.

## `new_game`

```
new_game(deck_id, opponents?, starting_life?, position?, seed?, turn_limit?, draw_first_turn?)
```

| Parameter | Meaning |
|---|---|
| `deck_id` | The tested seat's loaded deck. |
| `opponents` | Loaded deck ids for zero to three opposing seats, in order; a deck may appear more than once and may be `deck_id` itself. Empty or omitted: a goldfish game. |
| `starting_life` | Starting life per seat: a number for every seat, or a list giving the tested seat's and then each opposing seat's in `opponents` order. Default 40. |
| `position` | The tested seat's place in turn order, from 1. Omitted: drawn from the seed with the rest. |
| `seed`, `turn_limit`, `draw_first_turn` | As for every game; `turn_limit` counts rounds. |

Creates the game, assigns instance ids, places each seat's commanders in the command zone, shuffles each seat's library on its own stream, and deals each seat seven cards. The game starts in status `mulligan`.

A goldfish game's response gives the game id, the seed and the opening hand. A contested game's response is for whoever starts the game and lists, in turn order, each seat's number, seat id, deck id, starting life and whether it is the tested seat, with the seed; it shows no hand. Each seat sees its own hand through its own calls.

Errors: an unknown deck id; more than three opponents; a `starting_life` list whose length is not the number of seats, or a value below 1; a `position` outside 1 to the number of seats; `position` or `starting_life` lists given for a goldfish game, where the only seat's place is 1 and `starting_life` must be a number; `turn_limit` not a positive integer.

## `mulligan`

```
mulligan(game_id, keep, bottom?, override?)
```

Each seat takes its own mulligans, in any order. With `keep: false` the seat's hand returns to its library, its library is shuffled, and seven new cards are dealt. With `keep: true` the seat keeps, having put `bottom` cards on the bottom of its library in the order given. The first mulligan is free: after *k* mulligans the number of cards to bottom is *k* − 1, or zero if the seat has not mulliganed, and never more than seven.

Keeping with the wrong number of cards in `bottom` is a rule check; with `override` the cards named are bottomed as given. Naming a card in `bottom` that is not in the seat's hand is an error, as is giving `bottom` with `keep: false`, and `mulligan` from a seat that has already kept.

When the last seat keeps, the game starts: status becomes `active`, the first seat in turn order becomes the active seat, and the game proceeds through its untap, upkeep and draw steps to its first main step, exactly as `advance` would. Every seat draws on its first turn unless `draw_first_turn` is false, in which case the first seat in turn order skips its first draw. The response to the call that starts the game shows what that start did; it shows a card drawn only to the seat that drew it.

## The Seat to Act

At any moment the game knows which seats it is waiting on: the **seats to act**. In order of precedence:

1. During mulligans: every seat that has not kept.
2. When a pending choice is waiting: the seat it is addressed to. Pending choices are answered one at a time, in the order they were created.
3. When a reminder is waiting for a seat other than the active seat (see `turn`): that seat.
4. When a response window is open: the seat being asked (see `stack`).
5. Otherwise: the active seat.

What each seat may call:

| Call | Accepted from |
|---|---|
| `get_state`, `get_log`, `wait` | Any seat, in any status. |
| `end_game` | The tested seat, in any status but `ended`; an opposing seat still in the game, to concede. |
| `mulligan` | A seat to act during mulligans. |
| `choose` | The seat a waiting pending choice is addressed to. |
| `play`, `effect`, `pass` | The seat to act, when it is asked in a window or answering a reminder. |
| `play`, `effect`, `attack`, `advance` | The active seat when it is the seat to act. |

A call from any other seat is an error naming the seat to act and what it is being asked. A call from an eliminated seat is an error, except `get_state`, `get_log` and `wait`.

In a goldfish game the only seat is always the seat to act, and what it may call depends on the game's status alone:

| Status | Accepted tools |
|---|---|
| `mulligan` | `mulligan`, `get_state`, `get_log`, `end_game` |
| `active` | everything except `mulligan` and `choose` |
| `pending_choice` | `choose`, `get_state`, `get_log`, `end_game` |
| `ended` | `get_state`, `get_log` |

`wait`, `pass` and the stack exist only in contested games; in a goldfish game `wait` returns at once and `pass` is an error.

A resend of the calling seat's most recent change is answered as such whatever the game's state.

## What a Seat May See

Every response to a seat, and its `get_state`, shows only what that seat's player could see:

- **Its own** hand and the number of cards in its library. Never the order or contents of any library.
- **Every seat's** battlefield, graveyard, exile and command zone; the stack; each seat's life, hand size and library size; commander damage; who is eliminated.
- Cards revealed by a pending choice: to the seat it is addressed to only.

The **public form** of an event is what any seat may see of it: a card moved between hidden zones, or into a hidden zone, is shown as a count (`S2 drew 2 cards`, `S3 put a card into its hand`); a card moved from a hidden zone into a public one or onto the stack is shown by name; a mulligan shows the number of cards kept and bottomed; a pending choice shows its kind and the seat it is addressed to, not what it revealed. The digest of `tools` and the public event list of `records` are built from public forms.

The service hides in its views and does not police agents: `get_log` returns the whole record to any seat (see `records`).

## `get_state`

```
get_state(game_id, detail?)
```

`detail: "summary"` (the default) lists the calling seat's hand, then for each seat in turn order its battlefield, graveyard and command zone, and current notices. In a contested game it also shows the stack, the open window and who is being asked, each seat's life, hand size and library size, and which seats are eliminated. Each battlefield permanent is shown with its instance id, tapped state, counters, its controller when that is not its owner, and what the service has read of it: the mana it makes, haste or vigilance it has or is granted, and the steps it has a trigger in, marked `(opp)` for a trigger on opponents' turns; a goldfish game, which has no opponents' turns, lists only the others. `detail: "full"` adds exile, each library's size, per-commander cast counts and damage, and the calling seat's payments this turn.

In a goldfish game `get_state` shows the one seat's zones exactly as it always has.

## Life, Elimination and Conceding

Each seat of a contested game has its own life total, starting at its `starting_life`. Life changes by deltas (see `play`) and combat damage (see `combat`).

After every applied call the game checks every seat still in it. A seat is **eliminated** when:

- its life is 0 or less; or
- one commander has dealt it 21 or more combat damage; or
- it concedes: `end_game` called by an opposing seat, with any result, eliminates that seat and does not end the game.

On elimination:

- every card the seat owns leaves the game: it is removed from every zone, including permanents another seat controls and its spells on the stack;
- every permanent it controls but does not own returns to its owner's control;
- every stack item it controls is removed (see `stack`), and every pending choice addressed to it is discarded;
- it takes no more turns and is never asked in a window;
- if it was the active seat, its turn ends at once and the next seat in turn order begins its turn (see `turn`).

The response to the call that caused an elimination says which seat was eliminated and why. Eliminations are applied in turn order when several happen at once.

In a goldfish game the seat is never eliminated: its life reaching 0 raises the life notice, as below.

## End Conditions and Notices

The service watches for conditions that would normally end a game. When one is first reached it adds a notice, and the notice appears on every later response to every seat until the game ends.

| Notice | Game | Reached when |
|---|---|---|
| Damage | Goldfish | Pooled damage to the imaginary opponents is 120 or more. |
| Commander damage | Goldfish | For each of the three imaginary opponents, some one commander has dealt 21 or more to that opponent. |
| Life | Goldfish | The seat's life is 0 or less. |
| Tested seat eliminated | Contested | The tested seat is eliminated. |
| Opponents eliminated | Contested | Every opposing seat is eliminated. |
| Turn limit | Both | The game enters a turn of round `turn_limit`. In a goldfish game rounds and turns are the same. |
| Empty library | Both | A seat attempted to draw with too few cards in its library; the draw takes what there is. The notice names the seat. |

A notice never changes the game's status and never stops play. Once raised, a notice stays even if its condition stops holding.

## `end_game`

```
end_game(game_id, result, notes?)
```

From the tested seat, ends the game with `result` of `win`, `loss` or `stalled` and the agent's free-text verdict. The result is trusted; no condition is required, and the game may be ended whatever it is waiting on. Every pending choice, open window, stack item and declared attack is discarded, and a snapshot is written for the turn in progress if it does not have one (see `records`). After this the status is `ended` and only `get_state`, `get_log` and `wait` are accepted.

From an opposing seat, `end_game` concedes: the seat is eliminated, its `notes` are recorded, and the game goes on.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Where seats live | Inside the one game, which holds the table and its seats | A separate contested-game aggregate; a table over one goldfish game per seat | See the HLD. Every rule keeps one home, scoped to the acting seat, and a change touching several seats is one operation. |
| The tested seat's seat id | The game id | A separate random id | A goldfish game's calls stay exactly as they are, and records stay keyed by the game id. |
| How seats name each other | Seat numbers in turn order | Seat ids; commander names | Seat ids would hand out access to the seat; commander names collide in a mirror match. |
| Shuffle streams | One per seat, keyed by the tested seat's empty key or an opposing seat's `o<k>` | One stream for the table | With one stream the tested seat's draws would change with the opposing decks, and its goldfish and contested games on one seed could not be compared. |
| Instance ids | Tested seat first, then opposing seats in `new_game` order | Interleaved; per-seat prefixes | The tested seat's ids match its goldfish game; plain ids stay short in every call. |
| Turn order | Drawn from the seed; the tested seat's position may be fixed | Always the tested seat first; the caller gives the whole order | Position matters in Commander; drawing it keeps seeds meaningful, fixing it lets a caller isolate it. |
| Who acts | One rule, the seat to act, with a fixed precedence | Each tool checks its own conditions | One place answers "whose call is it?", which `wait`, the status line and every refusal need. |
| Calls from the wrong seat | Error | Rule check | The game's order is structural: a call out of turn has no meaning to apply. |
| Elimination | Applied by the service | Declared by an agent | No agent should declare another seat's loss; the bookkeeping is already the service's. |
| Conceding | `end_game` from an opposing seat | A separate tool | One tool for "I am done", whose effect depends on whose verdict the game is. |
| Empty library in a contested game | Notice only | Elimination | Drawing from an empty library is rare and its rules have exceptions; the seat may concede. |
| What `new_game` shows in a contested game | Seat ids and turn order, no hand | The tested seat's hand | Its caller may be an orchestrator, not the tested seat's agent. |
| Opponents' life in a goldfish game | One pooled damage total against 120 | A life total per imaginary opponent | Pooling removes a decision that carries no information; commander damage stays per opponent because 21 from one commander is a per-opponent rule. |
| Commander damage with two commanders | Tracked per commander | One combined track | The 21-damage rule counts each commander separately. |
| Shuffle generator | Own Fisher–Yates over the seeded generator's basic float | The standard library's `shuffle` | Only the basic float is guaranteed stable across Python versions. |
| First turn draw | Every seat draws; switchable, which skips the first seat's draw | Never draw; always draw | Commander is multiplayer, where no one skips the first draw; the switch models going first in a duel. |
| End conditions | Notices; only the tested seat ends the game | End the game automatically | The agent may want to keep playing, or may judge a result the service cannot see. |
| Mulligan rule | London mulligan with one free mulligan | Seven-card redraws only | The Commander mulligan rule. |
| Names versus ids | Names everywhere, own cards first; ids accepted and shown when instances differ | Ids everywhere | Names are what agents think in; resolving own cards first makes the common case need no id in a mirror match. |
| `end_game` while anything is pending | Allowed | Blocked until resolved | A game that is decided, or stalled on a silent seat, must still be endable. |

## Open Questions & Future Decisions

### Deferred
1. Results beyond `win`, `loss` and `stalled`.
2. Poison counters and other loss tracks; the agents record them and a seat concedes.
3. Drawing from an empty library as a cause of elimination.

## References

- `docs/high-level-design.md` (*Seats inside one game*; *Each seat sees its own game*)
- `docs/intent/deck/deck-design.md`
- `docs/intent/turn/turn-design.md`
- `docs/intent/stack/stack-design.md`
- Magic Comprehensive Rules 800.4a (a player leaving the game), 903 (Commander)
