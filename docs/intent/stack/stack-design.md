---
parent: high-level-design
prefix: STACK
---

# Stack

## Context and Design Philosophy

In a contested game other seats can act during a seat's turn: counter its spell, remove its attacker, cast something at the end of its turn. This component holds what makes that possible: the **stack** of plays and effects that have been made but not yet resolved, the **response windows** in which seats are asked whether they respond, and **resolution**. It owns one tool, `pass`.

The service keeps the stack's order, not its meaning. Each item carries the delta its controller stated when it was made, and resolving an item applies that delta. The service never works out what a card does on resolution; a counterspell is a delta that counters, and a spell whose board has changed is restated by its controller.

Fidelity to Magic's priority rules gives way where it would cost far more than the pushback it buys (tenet *Pushback over fidelity*): windows open at a few points only, and a seat with no untapped permanents is passed automatically.

A goldfish game has no stack. Its plays and effects are applied at once, as `play` describes, and nothing in this component applies to it.

## Stack Items

```
StackItem {
  id: string                 // "s1", "s2", ...: numbered across the game, never reused
  controller: int            // seat number
  kind: "spell" | "ability"
  card: instance id | null   // the spell's card instance, on the stack; null for an ability
  source: string             // the card played, or the effect's source
  tool: "play" | "effect"
  delta: Delta               // as stated; applied on resolution
  to: Destination | null     // where a spell's card goes on resolution, if stated
  choices: Choices | null
  disturbed: bool            // something above this item resolved while it waited
}

Game.stack: [StackItem]      // bottom first; the last item is the top
```

A spell's card is in the zone `stack` while its item waits. An ability has no card.

### What goes on the stack

In a contested game:

- `play` of a card whose played face is not a land puts a spell on the stack. The cost is paid, the commander tax counted and the card moved to the stack when the call is applied; the delta waits.
- `effect` puts an ability on the stack, its cost paid when the call is applied. An `effect` with `immediate: true` is applied at once and opens no window: it is for mana abilities, special actions, the result of combat between creatures (see `combat`), and corrections.
- Playing a land never uses the stack.

### Resolution

The top item **resolves** when every seat still in the game other than its controller has passed on it in succession since it became the top item. When no other seat is still in the game, it resolves at once.

Resolving a spell moves its card to its destination — `to` when stated, otherwise the default `play` gives (a permanent to the battlefield, an instant or sorcery to the graveyard) — and then applies its delta, the same order as a play in a goldfish game, so a permanent's delta can change the permanent itself. Resolving an ability applies its delta. Everything `play` adds to an applied delta is added here: shuffles, commander zone changes, tokens, battlefield arrival, notices and eliminations.

When an item resolves, every item still below it is marked **disturbed**.

### Confirming or restating a disturbed item

An item that is disturbed when it reaches resolution does not resolve directly. Its controller receives a pending choice of kind `resolve`, which shows the held delta and destination. The seat answers with `choose`:

- with no `restate`: the item resolves as held;
- with `restate: { delta?, to? }`: the item resolves with the given delta and destination in place of the held ones. A spell with nothing left to do is restated with `to` its owner's graveyard and an empty delta.

An undisturbed item never asks: when nothing resolved above it, its delta is applied as sent with no extra call.

### Countering

The delta key `counter` names items on the stack, by stack item id or by the name of a spell's card. A countered item is removed without its delta being applied; a countered spell's card goes to its owner's graveyard, unless the same delta moves it elsewhere with `move`. Countering is the only way an item leaves the stack unresolved, apart from an elimination (below) and the end of the game.

## Response Windows

A **response window** is a point at which the game asks seats, one at a time in turn order, whether they respond. A seat responds with `play` or `effect`, which puts an item on the stack; it declines with `pass`.

```
Window {
  kind: "stack" | "attack" | "end"   // what opened it: an item on the stack, declared attackers, the end step
  asking: int                        // seat number of the seat being asked
  passed: [int]                      // seats that have passed in succession since the asking last began
}
```

A window opens:

| Opens | Who is asked, starting from | Closes when |
|---|---|---|
| When an item is put on the stack | Every seat other than the top item's controller, starting with the next seat after it in turn order | The top item resolves (see Resolution); the window opens again for the new top item while the stack is not empty |
| After attackers are declared (see `combat`) | Every seat other than the active seat, starting with the next seat after it | Every seat other than the active seat has passed in succession with the stack empty |
| On entering the end step | Every seat other than the active seat, starting with the next seat after it | As above |

A response during a window puts its item on top of the stack, and the asking begins again for that item: every seat other than its controller, starting with the next seat after it, so the controller of the item below is asked again. When the stack has emptied inside an attack or end-step window, that window's asking begins again from the seat after the active seat.

While a window is open:

- the seat being asked is the seat to act, and only it may `play`, `effect` or `pass` (see `game` for what any seat may do at any time);
- no seat may `advance` or `attack`, and the same holds whenever the stack is not empty: either call is an error, not a rule check, whichever seat makes it;
- the seat being asked may cast only a card that is an instant or has flash, as the timing rule check in `play` describes, extended to every seat's turn: outside its own main step with an empty stack, a seat may cast only such a card.

When an attack window or an end-step window closes, the active seat is the seat to act and continues with `advance`; nothing else happens. Blocks are asked for when the active seat advances into `declare_blockers` (see `combat`).

### Automatic pass

When the seat to be asked has no untapped permanents, the service passes for it at once and asks the next seat. Every automatic pass is reported, in the response to the call that caused it and in the other seats' digests, naming the seat and why.

An automatic pass loses the rare spell a tapped-out seat could still cast, and tells the others that seat had no untapped permanent. Both are accepted (tenet *Pushback over fidelity*).

When every seat to be asked is passed automatically, the item resolves within the call that put it on the stack, and that call's response shows the resolution.

## `pass`

```
pass(game_id, after?)
```

The seat being asked declines to respond. `game_id` is the calling seat's seat id (see `game`).

`pass` also answers a reminder that makes the calling seat the seat to act (see `turn`): the seat declines to record the trigger now.

Errors:

- the calling seat is not the seat to act;
- the calling seat owes a pending choice: it answers with `choose`;
- the calling seat is the active seat and the seat to act with no window open and no reminder: it moves on with `advance`.

## Triggers

A triggered ability is recorded by its controller with `effect`, as in a goldfish game, and goes on the stack like any other ability, where it can be responded to.

A seat records only when it is the seat to act. A trigger that happens while another seat is acting — a creature dying in combat damage, where no window opens — is recorded by its controller at the next window in which it is asked, or on its own turn. The delay is a known gap (tenet *Pushback over fidelity*).

## Elimination and the Stack

When a seat is eliminated (see `game`), every item it controls is removed from the stack without resolving, and so is every item whose card it owns — a spell another seat cast with a card of the eliminated seat's — because that card leaves the game with the seat's other cards. A spell the eliminated seat controlled whose card another seat owns goes to its owner's graveyard. If the seat was being asked, the asking moves to the next seat. Remaining items keep their places; none is marked disturbed by the removal.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| What an item carries | The delta its controller stated, applied on resolution | Cast now, state the delta on resolution; resolve at once and let others react afterwards | A spell nobody answers still takes one call. Resolving at once makes counterspells and responses impossible. |
| How a seat declines | A `pass` tool | `advance` from a non-active seat; passing implied by `wait` | `advance` moves the turn and belongs to the active seat; overloading it would make one tool mean two things. An implied pass would let a seat lose its chance to respond by waiting. |
| Who is asked first | The seat after the top item's controller, in turn order | The active seat first, as in Magic's priority rules; the controller first | Asking the controller about its own item rarely yields anything, and starting after it gives every other seat the chance in a fixed order. |
| Asking order | One seat at a time, in turn order | Every seat at once, first answer wins | Timing would decide the game, and a seed would no longer reproduce it. |
| When windows open | On the stack, after attackers are declared, in the end step | In every step, as Magic's priority rules do | Too many passes for the pushback gained. Removal on attackers and plays at the end of a turn are what these three points add. |
| Reducing passes | An automatic pass for a seat with no untapped permanents, reported | Stops chosen by each seat; guessing from card text whether a response is possible | Stops add configuration not yet needed. A wrong guess from card text cannot be undone. Reporting follows tenet *Best guess, shown*. |
| Order of resolving a spell | The card moves to its destination, then the delta is applied | The delta first, then the card | A play in a goldfish game moves the card first, so one order serves both kinds of game, and a permanent's delta can put counters on it or tap it as it enters. |
| A held delta after the board changed | The controller confirms or restates it, only when something resolved above it | Always confirm; never confirm | Asking every time doubles the calls for unanswered spells; never asking applies deltas written for a board that no longer exists. |
| How countering is stated | A `counter` delta key naming items | Moving the countered card with `move` | An ability has no card to move. One key covers spells and abilities. |
| Effects that must not wait | `immediate: true` on `effect` | Infer from the delta (only `mana`, for instance); never immediate | An inference would misjudge abilities whose delta happens to look like a mana ability. Never immediate would give mana abilities and combat results a window they do not have. |
| Triggers outside a window | Recorded at the controller's next window or turn | A window after every event; a call from any seat at any time | A window after every event multiplies passes; calls at any time break the one-seat-at-a-time order that makes a seed reproducible. |
| Removal of an eliminated seat's items | Removed, nothing marked disturbed | Marked disturbed | Nothing resolved; the board the waiting deltas were written for has changed no more than when any permanent leaves. |
| A spell whose card an eliminated seat owns | Removed with that seat's items, whoever controls it | Left on the stack to resolve without its card | Every card the seat owns leaves the game; an item with no card could not move it on resolution. |
| Where blocks are asked for | When the active seat advances into `declare_blockers` (see `combat`) | When the attack window closes | A closing window then does one thing in every case: it returns the game to the active seat. Blocks belong to a step, and the step is entered by `advance`. |

## Open Questions & Future Decisions

### Deferred
1. Stops: a seat choosing the windows it wants to be asked in, should automatic passes prove too few.
2. Holding priority: a seat putting two items on the stack before others are asked. Today a seat's second item goes on the stack the next time it is asked.
3. Split second and other rules that forbid responses; the seats observe them by passing.
4. Copies of spells on the stack; an `effect` whose delta does what the copy does.

## References

- `docs/high-level-design.md` (tenet *Pushback over fidelity*; *The service keeps the stack's order, not its meaning*)
- `docs/intent/play/play-design.md` (deltas, pending choices, `choose`)
- `docs/intent/game/game-design.md` (seats, turn order, the seat to act, elimination)
- `docs/intent/combat/combat-design.md` (the attack window, combat results)
- `docs/intent/turn/turn-design.md` (the end step, reminders)
- Magic Comprehensive Rules 117 (timing and priority), 405 (stack), 608 (resolving spells and abilities)
