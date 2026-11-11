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
  cast_with: string | null   // a cast trigger: the id of the spell it was stated with
  disturbed: bool            // something above this item resolved while it waited
}

Game.stack: [StackItem]      // bottom first; the last item is the top
```

A spell's card is in the zone `stack` while its item waits. An ability has no card.

### What goes on the stack

In a contested game:

- `play` of a card whose played face is not a land puts a spell on the stack. The cost is paid, the commander tax counted and the card moved to the stack when the call is applied; the delta waits.
- The cast triggers stated with that `play` (see `play`) go on the stack in the same call, above the spell: each is an ability controlled by the casting seat, holding the trigger's `source`, `delta` and `choices` and the spell's id as `cast_with`. They are put on in reverse of the order listed, so that the first listed is on top and resolves first; each takes the next stack item id as it goes on, so the first listed has the highest id. No seat is asked between the items of one call: the response window opens once, for the top item, when the last of them is on the stack.
- `effect` puts an ability on the stack, its cost paid when the call is applied. An `effect` with `immediate: true` is applied at once and opens no window: it is for mana abilities, special actions, the result of combat between creatures (see `combat`), and corrections.
- Playing a land never uses the stack. A land played while a window is open leaves the window as it was: the same seat is still asked, and the passes already made stand.

**What is checked when.** A held delta is written before the board it will meet exists, so the call that puts it on the stack checks only what does not depend on where cards are: its shape (unknown keys, malformed values, more than one of `look`, `search` and `look_at_hand`), its seat numbers, and its `counter` entries, each of which must name an item on the stack at that moment and is held from then on as that item's id. A cast trigger's delta is checked the same way, against the stack with its spell already on it and none of the call's cast triggers yet, so its `counter` may name its own spell but never another cast trigger of the same call. The cards the delta names are not looked for until the item resolves, and are then found in the game as it stands, with the item's controller as the acting seat. A permanent's delta can therefore name the permanent itself, which is not on the battlefield when the spell is cast.

### Resolution

The top item **resolves** when every seat still in the game other than its controller has passed on it in succession since it became the top item. When no other seat is still in the game, it resolves at once.

Resolving a spell moves its card to its destination — `to` when stated, otherwise the default `play` gives (a permanent to the battlefield, an instant or sorcery to the graveyard) — and then applies its delta, the same order as a play in a goldfish game, so a permanent's delta can change the permanent itself. Resolving an ability applies its delta. Everything `play` adds to an applied delta is added here: shuffles, commander zone changes, tokens, battlefield arrival, notices and eliminations. Every seat is checked for elimination once each resolving item's delta has been applied in full, never between its keys (see `game`), and eliminations are applied then, before the next seat is asked or the next item resolves, so when one call resolves several items a seat brought to 0 life by the first loses its items lower on the stack before they resolve.

A stated `to` follows the rule every move follows (see `play`): `hand`, `graveyard`, `exile`, `command` and the library are the card owner's, and the battlefield is entered under the control of the item's controller.

A commander never goes from the stack to a graveyard or to exile unasked. Whether its spell resolves there, is countered, or is removed because its controller was eliminated, the card goes to its owner's command zone instead and the response says so, unless the delta that sends it there — the item's own, held or restated, or the countering delta — sets `commander_stays`.

When an item resolves, every item still below it is marked **disturbed**, with one exception: a cast trigger that resolves, as held or restated, marks neither the spell it was stated with nor the other cast triggers stated with that spell. The casting seat wrote all of them in one call, knowing its cast triggers resolve first and in their order, so the spell's delta already describes the board its cast triggers leave. Any other item that resolves above them, such as another seat's response, disturbs them as usual.

### Confirming or restating a disturbed item

An item that is disturbed when it reaches resolution does not resolve directly. Its controller receives a pending choice of kind `resolve`, which shows the held delta and destination. The seat answers with `choose`:

- with no `restate`: the item resolves as held;
- with `restate: { delta?, to? }`: the item resolves with the given delta and destination in place of the held ones. A spell with nothing left to do is restated with `to` its owner's graveyard and an empty delta.

An undisturbed item never asks: when nothing resolved above it, its delta is applied as sent with no extra call.

A restated delta is a delta like any other. It may hold any key, it is not compared with the held one, and it is applied as part of the item's resolution: nothing new goes on the stack and no window opens for it. A `to` given for an ability, which has no card, is an error.

### A held delta that can no longer be applied

A held delta may name a card that has since left, a stack item that is gone, or a seat that has been eliminated. Applying it would be an error, and the call that caused the resolution is another seat's `pass`, which cannot answer for it. The item then does not resolve, disturbed or not: nothing of it is applied, its card stays on the stack, and its controller receives the same `resolve` pending choice, which also states the error. The controller restates the delta to what the item now does. An answer that still cannot be applied, with or without `restate`, is an error to the answering seat, and the choice goes on waiting.

### Countering

The delta key `counter` names items on the stack, by stack item id or by the name of a spell's card. A countered item is removed without its delta being applied; a countered spell's card goes to its owner's graveyard (a commander to its owner's command zone, as above), unless the same delta moves it elsewhere with `move`. Countering is the only way an item leaves the stack unresolved, apart from an elimination (below) and the end of the game.

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

A response during a window puts its item on top of the stack, and the asking begins again for that item: every seat other than its controller, starting with the next seat after it, so the controller of the item below is asked again. When the stack has emptied inside an attack or end-step window, that window's asking begins again from the seat after the active seat. If the active seat is eliminated while such a window is open, no further seat is asked in it and it closes once the stack is empty: the turn it belonged to is ending (see `turn`).

The asking waits for decisions that come first. While a pending choice waits, or a reminder waits for a seat other than the active seat (see `game` for the order in which seats act), no seat is asked, no automatic pass is made and nothing resolves. So when a resolving item's delta asks seats for a sacrifice, the window for the item below begins only after they have answered, and an automatic pass is judged by the board their answers left. On entering the end step the end-step window is open at once, but when other seats have reminders for that step its asking begins only after each has recorded its trigger or passed and the stack has emptied.

While a window is open:

- the seat being asked is the seat to act, and only it may `play`, `effect` or `pass` (see `game` for what any seat may do at any time);
- no seat may `advance` or `attack`, and the same holds whenever the stack is not empty: either call is an error, not a rule check, whichever seat makes it;
- the seat being asked may cast only a card that is an instant or has flash, as the timing rule check in `play` describes, extended to every seat's turn: outside its own main step with an empty stack, a seat may cast only such a card.

When an attack window or an end-step window closes, the active seat is the seat to act and continues with `advance`; nothing else happens. An end-step window in which every other seat is passed automatically, or with no other seat left in the game, closes within the advance that entered the end step, and that advance goes on toward its `to` (see `turn`). Blocks are asked for when the active seat advances into `declare_blockers` (see `combat`).

### Automatic pass

When the seat to be asked has no untapped permanents, the service passes for it at once and asks the next seat. Every automatic pass is reported, in the response to the call that caused it and in the other seats' digests, naming the seat and why.

An automatic pass loses the rare spell a tapped-out seat could still cast, and tells the others that seat had no untapped permanent. Both are accepted (tenet *Pushback over fidelity*).

When every seat to be asked is passed automatically, the item resolves within the call that put it on the stack, and that call's response shows the resolution.

## `pass`

```
pass(game_id, after?)
```

The seat being asked declines to respond. `game_id` is the calling seat's seat id (see `game`).

`pass` also answers a reminder that makes the calling seat the seat to act (see `turn`): the seat declines to record the trigger now. A reminder for the active seat does not make the game wait, so the active seat has nothing to pass on: it records the trigger with `effect` or advances.

An `effect` with `immediate: true` never answers a reminder, whatever its `source`. A reminded seat that taps for mana with one is still the seat to act, until it calls `pass` or records the trigger with an `effect` that goes on the stack and whose `source` names the reminded permanent (see `turn`).

Errors:

- the calling seat is not the seat to act;
- the calling seat owes a pending choice: it answers with `choose`;
- the calling seat is the active seat and the seat to act with no window open, whether or not it was reminded of a trigger in the current step: it moves on with `advance`.

## Triggers

A triggered ability is recorded by its controller with `effect`, as in a goldfish game, and goes on the stack like any other ability, where it can be responded to.

A cast trigger of the casting seat is the exception to recording with `effect`: it is stated with the `play` that casts the spell, because a spell that every other seat is passed on automatically resolves within that call (see Automatic pass), before its caster could make another. It goes on the stack above its spell, so it resolves first, even though nobody responds. A copy of the spell made by a cast trigger is the trigger's delta, stating what the copy does. Another seat's trigger on the same cast is recorded by that seat with `effect` in the first window it is asked in after the cast, which is about the caster's top cast trigger when there is one.

A seat records only when it is the seat to act. A trigger that happens while another seat is acting — a creature dying in combat damage, where no window opens — is recorded by its controller at the next window in which it is asked, or on its own turn. The delay is a known gap (tenet *Pushback over fidelity*).

## Elimination and the Stack

When a seat is eliminated (see `game`), every item it controls is removed from the stack without resolving, and so is every item whose card it owns — a spell another seat cast with a card of the eliminated seat's — because that card leaves the game with the seat's other cards. A spell the eliminated seat controlled whose card another seat owns goes to its owner's graveyard, or to its owner's command zone when it is a commander. If the seat was being asked, the asking moves to the next seat. Remaining items keep their places; none is marked disturbed by the removal.

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
| When a held delta's cards are found | At resolution, in the game as it then stands; shape, seat numbers and `counter` entries are checked when the call is made | Find and fix every card when the call is made; check everything twice | A delta is written for the board after the spell resolves: a permanent's delta names a permanent not yet on the battlefield. `counter` names items that exist when the response is made, and holding their ids keeps a spell's name from matching a different item later. |
| A held delta that cannot be applied at resolution | Its controller restates it through the `resolve` choice | Skip the parts that fail; remove the item without effect; return the error to the call that caused the resolution | The controller knows what its spell does now that its target is gone. Skipping parts would be the service deciding what a card does, and the passing seat cannot correct another seat's delta. |
| Asking while a choice or another seat's reminder waits | Suspended, automatic passes included | The window goes on at once | An answer changes the board the next item meets and the permanents an automatic pass is judged by; resolving a lower item first would apply effects out of order. |
| Eliminations when one call resolves several items | After each resolution | Once, after the call | A seat at 0 life has left the game; its lower items resolving, and perhaps saving it, would make the result depend on how many seats were passed automatically. |
| A commander leaving the stack | To its owner's command zone, unless `commander_stays` | To the graveyard as any spell | The commander zone change holds wherever a move comes from (see `play`); a countered commander is the commonest case of it. |
| What a restate may hold | Any delta, unchecked against the held one | Only a smaller version of the held delta | The service cannot tell smaller from different, and the controller is trusted with the first delta as much as the second. |
| Where a caster's cast triggers go | On the stack above the spell, in the `play` call, before any seat is asked | Asking the caster first after every spell; general holding priority | Asking the caster costs a call on every spell; holding priority in general is a larger change than the case that loses triggers today, a spell resolving within its own `play`. |
| Stack item ids of several cast triggers | Numbered in the order put on the stack, so the first listed, put on last, has the highest id | Numbered in the order listed | Every id says when its item went on the stack; one rule for all items. |
| A spell disturbed by its own cast triggers | Not disturbed by them, nor are its other cast triggers | Disturbed, as by any item resolving above | The caster wrote the spell's delta for the board its cast triggers leave; a `resolve` choice after every cast trigger would cost the call the parameter exists to save. |
| Where blocks are asked for | When the active seat advances into `declare_blockers` (see `combat`) | When the attack window closes | A closing window then does one thing in every case: it returns the game to the active seat. Blocks belong to a step, and the step is entered by `advance`. |

## Open Questions & Future Decisions

### Deferred
1. Stops: a seat choosing the windows it wants to be asked in, should automatic passes prove too few.
2. Holding priority: a seat putting two items on the stack before others are asked, other than a spell and its cast triggers. Today a seat's second item goes on the stack the next time it is asked.
3. Split second and other rules that forbid responses; the seats observe them by passing.
4. Copies of spells on the stack; an `effect` whose delta does what the copy does.
5. A cast trigger that casts another spell (cascade, discover): no delta puts a spell on the stack, so the spell found is cast with `play` the next time its caster is asked, or its effect is stated in the trigger's delta.

## References

- `docs/high-level-design.md` (tenet *Pushback over fidelity*; *The service keeps the stack's order, not its meaning*)
- `docs/intent/play/play-design.md` (deltas, pending choices, `choose`)
- `docs/intent/game/game-design.md` (seats, turn order, the seat to act, elimination)
- `docs/intent/combat/combat-design.md` (the attack window, combat results)
- `docs/intent/turn/turn-design.md` (the end step, reminders)
- Magic Comprehensive Rules 117 (timing and priority), 405 (stack), 608 (resolving spells and abilities)
