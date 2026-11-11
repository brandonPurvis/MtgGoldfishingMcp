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
  active: int | null           // seat number of the active seat; null during mulligans and when no seat is left in the game
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
  seat_id: string              // the tested seat's is the game id; an opposing seat's has the same format
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

### Reading a card instance

A card instance is read from its owner's deck, whichever seat controls it: its names, its card data (type line, mana cost, power) and its readings (see `card-reading`) — the mana it makes, its haste, vigilance, evasion, reach or flash, its step triggers and whether it enters tapped — are the ones that deck holds for it. A token is read from its spec, and a card with a card definition or brought from outside the game from the data it carries. So a permanent that has changed control makes the same mana, has the same keywords and step triggers, and has the same name in every call and response as it did for its owner. What a reading says of "you" is the seat that controls the permanent: it is that seat's mana source, its permanents and commanders that a counted amount and a commander's color identity refer to (see `payment`), its creatures that a keyword grant reaches (see `combat`), and that seat that is reminded of its step triggers (see `turn`).

### Instance ids

Instance ids are assigned at game creation seat by seat: the tested seat first, then the opposing seats in the order `new_game` lists their decks. Within a seat the order is commanders first, then the remaining cards, each group sorted by lower-cased card name compared character by character, copies of one card adjacent. Later instances (tokens, cards from outside the game) take the number after the highest ever issued in the game; a number is never used twice, even after its card has left the game with an eliminated seat. So the tested seat's cards have the same ids in a goldfish game and in any contested game on the same deck.

### Seat ids and seat numbers

A seat has two names. Its **seat id** is random and unguessable, and a call made with it acts as that seat; the tested seat's seat id is the game id. An opposing seat's seat id has the same format as a game id — `g` and ten random characters — and comes from the same id source, so an id's form does not tell which seat it names. `new_game` takes these ids from the id source in a fixed order (see `application`, APP-087), so the ids a seat receives do not depend on the turn order the seed gives. Its **seat number** is its place in turn order, by which calls and responses name seats to one another (`S2`). A goldfish game has one seat, number 1, whose seat id is the game id, so its calls are made exactly as they always were.

## Turn Order

In a contested game the seats' order is drawn from the seed: a Fisher–Yates shuffle, as below, of the list (tested seat, then opposing seats in `new_game` order), driven by a generator seeded from the text `<seed>:order`. When `new_game` gives `position`, the opposing seats alone are shuffled that way and the tested seat is placed at that position.

## Shuffling

Each seat's library is shuffled on its own stream. Before its first shuffle a library is in ascending order of instance number (`c2` before `c10`). A seat's shuffle is a Fisher–Yates shuffle driven by a generator seeded with the integer value of the SHA-256 hash of `<seed>:<n>` for the tested seat and `<seed>:<shuffle_key>:<n>` for an opposing seat, where *n* is the count of that seat's shuffles so far. The *n*th shuffle of a seat depends only on the seed, its shuffle key, *n*, and its library's contents at that moment. The generator is Python's `random.Random`; the shuffle walks *i* from the last index down to 1, swapping index *i* with index ⌊`random()`·(*i*+1)⌋, drawing only on the generator's basic uniform float, the one output Python guarantees stable across versions.

If `seed` is not given to `new_game`, the service generates one and returns it. The seed is visible to the playing agents; an agent that replays decks and a seed it has already played knows what every seat will draw, and whoever starts the games decides when that is acceptable.

## The Change Number

Every accepted call that changes a game increases the game's change number by one, whichever seat made it, and every response about the game shows it. Any changing tool accepts an optional `after`: the change number the calling seat last saw.

- `after` equal to the game's change number: the call is applied.
- the call's tool and arguments (other than `after`) are the same as the calling seat's most recent accepted change, and `after` is one less than that change's number: the call is a resend. It is not applied again; that change's summary and events are reported again with a statement that the call was already applied.
- any other `after`: an error saying the game is now at a different change number.
- `after` omitted: the call is applied with no check.

Refused calls do not increase the change number. In a goldfish game the calling seat's most recent change is the game's most recent change, so a resend is recognised exactly as it always was.

## Naming Cards in Calls

Wherever a tool takes a card name, the agent may give the card's full name, the name of one of its faces, or an instance id. Matching ignores letter case. A name is resolved among the instances in the zone the operation expects. A name for a card in a hidden zone — hand or library — is resolved only among the acting seat's own cards; the one exception is the `selections` of a pending choice, whose names are resolved among the cards that choice revealed, whichever seat owns them (see `play`). A name for a card in a public zone or on the stack is resolved, within the zone being searched, first among the cards the acting seat controls, then among other seats' cards in turn order from the acting seat; an operation that looks in several zones takes the zones in its own order first and applies this order of seats inside each (see `play`). An instance id singles out any card. When several instances match:

- the operation's natural candidate wins — an untapped one for tapping or paying, a tapped one for untapping;
- then the one with the lowest instance id.

When the matching instances differ from one another (tapped state, counters, face, controller), the response names the instance chosen by id. A name that matches nothing in the expected zone is an error; when the same name exists in a different zone the error says where.

An error never tells a seat what another seat's hand or library holds. The zone an error names is always one the acting seat may see: a public zone, the stack, or its own hand or library. A name that matches nothing the acting seat may see gets the same error whether or not another seat holds a card of that name in a hidden zone. An instance id that names a card in another seat's hand or library gets an error saying the card is in a hidden zone of that seat, without saying which: that much any seat can already work out, because instance ids are dealt out seat by seat and every public zone is in view.

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

Each seat takes its own mulligans, in any order. With `keep: false` the seat's hand goes to the bottom of its library in ascending order of instance number, below the cards already there, its library is shuffled, and seven new cards are dealt. With `keep: true` the seat keeps, having put `bottom` cards on the bottom of its library in the order given. The first mulligan is free: after *k* mulligans the number of cards to bottom is *k* − 1, or zero if the seat has not mulliganed, and never more than seven.

Keeping with the wrong number of cards in `bottom` is a rule check; with `override` the cards named are bottomed as given. Naming a card in `bottom` that is not in the seat's hand is an error, as is giving `bottom` with `keep: false`, and `mulligan` from a seat that has already kept.

When the last seat keeps, the game starts: status becomes `active`, the first seat in turn order still in the game becomes the active seat, and the game proceeds through its untap, upkeep and draw steps to its first main step, exactly as `advance` would. Every seat draws on its first turn unless `draw_first_turn` is false, in which case the seat that takes the first turn of the game skips that turn's draw.

An opposing seat may concede during mulligans, whether or not it has kept (see Life, Elimination and Conceding). It is then no longer waited on, and when its concession leaves no seat that has not kept, the game starts within that call. The response to the call that starts the game shows what that start did; it shows a card drawn only to the seat that drew it.

## The Seat to Act

At any moment the game knows which seats it is waiting on: the **seats to act**. In order of precedence:

1. During mulligans: every seat still in the game that has not kept.
2. When a pending choice is waiting: the seat it is addressed to. Pending choices are answered one at a time, in the order they were created.
3. When a reminder is waiting for a seat other than the active seat (see `turn`): that seat.
4. When a response window is open: the seat being asked (see `stack`).
5. Otherwise: the active seat.

What each seat may call:

| Call | Accepted from |
|---|---|
| `get_state`, `get_log`, `wait` | Any seat, in any status. |
| `end_game` | The tested seat, in any status but `ended`; an opposing seat still in the game, to concede. Either is accepted whichever seat is the seat to act and whatever the game is waiting on, the calling seat's own pending choice included. |
| `mulligan` | A seat to act during mulligans. |
| `choose` | The seat a waiting pending choice is addressed to. |
| `play`, `effect`, `pass` | The seat to act, when it is asked in a window or answering a reminder. |
| `play`, `effect` | The active seat when it is the seat to act. |
| `attack`, `advance` | The active seat when it is the seat to act, no response window is open and the stack is empty. |

A call from any other seat is an error naming the seat to act and what it is being asked. When a call is refused for more than one reason, one error is reported, the first that applies of: the game has ended; the calling seat is eliminated; the calling seat is not the seat to act. While a response window is open or the stack is not empty, `advance` and `attack` are errors, not rule checks, from every seat, the active seat included. A call from an eliminated seat is an error, except `get_state`, `get_log` and `wait`, and `end_game` from the tested seat. When every seat has been eliminated there is no active seat and no seat to act; the game keeps its status and accepts only those calls, until the tested seat ends it.

In a goldfish game the only seat is always the seat to act, and what it may call depends on the game's status alone:

| Status | Accepted tools |
|---|---|
| `mulligan` | `mulligan`, `get_state`, `get_log`, `wait`, `end_game` |
| `active` | everything except `mulligan`, `choose` and `pass` |
| `pending_choice` | `choose`, `get_state`, `get_log`, `wait`, `end_game` |
| `ended` | `get_state`, `get_log`, `wait` |

`wait`, `pass` and the stack serve contested games. In a goldfish game `wait` is accepted in every status and returns at once (see `application`), and `pass` is an error in every status (see `stack`).

A resend of the calling seat's most recent change is answered as such whatever the game's state.

## What a Seat May See

Every response to a seat, and its `get_state`, shows only what that seat's player could see:

- **Its own** hand and the number of cards in its library. Never the order or contents of any library.
- **Every seat's** battlefield, graveyard, exile and command zone; the stack; each seat's life, hand size and library size; commander damage; who is eliminated.
- Cards revealed by a pending choice: to the seat it is addressed to only.

What a seat is shown of an event depends on whose hidden zones the event touches, never on whose call caused it. A card that moves into, between or out of a seat's own hand or library is named to that seat, whichever seat's call moved it: a seat whose draw spell resolves on another seat's `pass` is told what it drew, and a seat whose hand was looked at is told which of its cards was taken. Every other seat sees the same event in its public form.

The **public form** of an event is what any seat may see of it: a card moved from one hidden zone to another without being revealed is shown as a count (`S2 drew 2 cards`, `S3 put a card into its hand`); a card moved from a hidden zone into a public one or onto the stack is shown by name; a card moved from a public zone or the stack into a hidden zone is also shown by name, because every seat could already see it (`S2 returned Sol Ring to its hand`); a kept hand shows the number of cards kept and bottomed, and a mulligan taken shows the seat and how many it has now taken; a pending choice shows its kind and the seat it is addressed to — and, for a look at a hand, whose hand — not what it revealed. The digest of `tools` and the public event list of `records` are built from public forms, with the events that touch the reading seat's own hidden zones given to that seat in full (see `application`).

The service hides in its views and does not police agents: `get_log` is outside these limits and returns the whole record, every seat's hidden zones included, to any seat at any time (see `records`).

## `get_state`

```
get_state(game_id, detail?)
```

`detail: "summary"` (the default) lists the calling seat's hand, then for each seat in turn order its battlefield — the permanents it controls, whichever seat owns them — its graveyard and command zone, and current notices. In a contested game it also shows the stack, the open window and who is being asked, each seat's life, hand size and library size, and which seats are eliminated. Each battlefield permanent is shown with its instance id, tapped state, counters, its owner when that is not its controller, and what the service has read of it: the mana it makes, haste or vigilance it has or is granted, and the steps it has a trigger in, marked `(opp)` for a trigger read as happening only on opponents' turns, and unmarked for a trigger on its controller's turn or on each turn; a goldfish game, which has no opponents' turns, lists only the others. `detail: "full"` adds exile, each library's size, per-commander cast counts and damage, and the calling seat's payments this turn.

In a contested game the listing also gives the pending choices addressed to the calling seat, in the order they will be answered, so that a seat that has not read the response or digest that created one can still find what it owes. Each is listed with its choice id, its kind and what it asks: for a `look`, `search` or `hand` choice, the cards it revealed, by name and instance id, which the calling seat is the one seat allowed to see; for an `ask`, its text and the seat whose effect asked; for `blocks`, the attackers it may block, each with the evasion the service holds for it (see `combat`); for `resolve`, the stack item, its source, its held delta and destination, and the error that kept it from resolving as held, if any. Pending choices addressed to other seats are not listed; the status line's `Act` already names the seat a waiting choice is addressed to and its kind.

In a goldfish game `get_state` shows the one seat's zones exactly as it always has, with no pending choice listed: its status line says one is pending, and the `CHOICE` response that created it showed the revealed cards.

## Life, Elimination and Conceding

Each seat of a contested game has its own life total, starting at its `starting_life`. Life changes by deltas (see `play`) and combat damage (see `combat`).

The game checks every seat still in it each time one delta has been applied in full — a delta applied at once, each stack item's delta as it resolves, each `choose` answer's delta — and each time one combat's damage has been applied in full. It does not check between the keys of one delta, so a seat that a delta takes to 0 life and back above it is not eliminated; it does check between the stack items one call resolves, so a seat at 0 life is gone before an item below can save it. A seat is **eliminated** when:

- its life is 0 or less; or
- one commander has dealt it 21 or more combat damage; or
- it concedes: `end_game` called by an opposing seat, with any result, eliminates that seat and does not end the game.

On elimination:

- every card the seat owns leaves the game: it is removed from every zone, including permanents another seat controls and its spells on the stack;
- every permanent it controls but does not own returns to its owner's control;
- every stack item it controls, and every stack item whose card it owns, is removed (see `stack`), and every pending choice addressed to it is discarded;
- a pending choice its effect addressed to another seat (an `ask`) stays, and that seat still answers it: the effect has already resolved; a look at the eliminated seat's hand that still waits is discarded, because the cards it shows have left the game;
- it takes no more turns and is never asked in a window;
- if it was the active seat, its turn ends: other seats' items still on the stack resolve first, pending choices that still wait are answered, and then the next seat in turn order begins its turn (see `turn`).

The response to the call that caused an elimination says which seat was eliminated and why: life, commander damage or conceding. A seat that meets the life and the commander-damage condition at the same check is reported as eliminated for life. When several seats meet a condition at the same check, their eliminations are applied one at a time in turn order starting from the active seat. When that leaves no seat in the game, no turn begins: both notices below are raised and the game waits for the tested seat to end it.

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
| Empty library | Both | A seat attempted to draw with too few cards in its library; the draw takes what there is. In a contested game each seat has its own notice, naming it, raised the first time it happens to that seat. |

A notice never changes the game's status and never stops play. Once raised, a notice stays even if its condition stops holding.

## `end_game`

```
end_game(game_id, result, notes?)
```

From the tested seat, ends the game with `result` of `win`, `loss` or `stalled` and the agent's free-text verdict. The result is trusted; no condition is required, and the game may be ended whatever it is waiting on. Every pending choice, open window, stack item and declared attack is discarded, and a snapshot is written for the turn in progress if it does not have one (see `records`). After this the status is `ended` and only `get_state`, `get_log` and `wait` are accepted.

From an opposing seat, `end_game` concedes: the seat is eliminated, its `notes` are recorded, and the game goes on. A concession is accepted at any moment, like the tested seat's `end_game`: during mulligans, out of turn, and while the game waits on the conceding seat.

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
| An opposing seat's seat id | The same format as a game id, from the same id source | A distinct prefix for seat ids | An id that showed it named an opposing seat would tell whoever saw it something about the table for no gain; one format also keeps one id source and one lookup. |
| The stack when the active seat is eliminated | Other seats' items resolve before its turn ends | The turn ends at once and the stack is discarded | Those items were made by seats still in the game and may matter to them; discarding them would undo plays no one countered. |
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
| When a seat may concede | At any moment, mulligans included | Only when it is the seat to act; only once the game is active | A seat that has stopped playing must not be able to stall the table by never answering, and an agent's decision to leave is its own (tenet *It's the agent's simulation*). |
| When elimination is checked | After each delta applied in full and each combat's damage | Once at the end of the call; after each key of a delta | A call can resolve several stack items, and a seat at 0 life would otherwise be saved by an item of its own lower on the stack; checking between keys would eliminate a seat partway through one effect that also restores it. |
| Order of simultaneous eliminations | Turn order from the active seat | Ascending seat number | Every other ordering between seats in this design starts from the seat that is acting, so one rule serves all of them. |
| Pending choices an eliminated seat caused | An `ask` stays; a look at its hand is discarded | Discard both; keep both | The effect that asked has resolved, and the seats it named owe its cost whatever became of its controller. A hand that has left the game cannot be chosen from. |
| Who sees a hidden card's name | The seat whose hidden zone the event touches, whichever seat's call caused it | The calling seat sees its call's events in full; the affected seat calls `get_state` | Most spells resolve on another seat's `pass`. Showing names by caller would show one seat another's draws, and leave the seat that drew to ask for its state after every draw spell. |
| A card moved from a public zone into a hidden zone | Named to every seat | Shown as a count, like any move into a hidden zone | Every seat could see the card before it moved, so a count would hide nothing and would leave the other seats to work out from the battlefield which card went. |
| Errors about another seat's hidden cards | Nothing for a name; "a hidden zone of that seat" for an instance id | Name the zone, as for the acting seat's own cards; one uniform error for both | Naming the zone, or confirming a name, would let a seat probe hands and libraries. An instance id's owner and its absence from public view are already public, so saying so costs nothing and explains the refusal (tenet *Clear before cheap*). |
| A permanent controlled by a seat that does not own it, in `get_state` | On its controller's battlefield, with its owner named | On its owner's battlefield, with its controller named | A battlefield is read to see what a seat can do and what can be done to it, which follows control; the owner matters only when the permanent leaves. |
| Which deck a card instance is read from | Its owner's, whichever seat controls it | The controlling seat's deck | A deck holds data and readings only for its own cards: read from the controlling seat's deck, a permanent taken from another seat would lose its mana, keywords and triggers. Control changes who the reading's "you" is, not what the card is. |
| Pending choices in a contested game's `get_state` | Those addressed to the calling seat, with what each asks | None, as in a goldfish game; every seat's choices | A seat that waits, or that missed the line that created a choice, needs one call that tells it what it owes. Other seats' choices may reveal cards the calling seat may not see. |
| Empty library notices | One for each seat | One notice naming the first seat; one notice whose text grows | A raised notice never changes; a second seat running out is a separate condition the tested seat may care about. |

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
