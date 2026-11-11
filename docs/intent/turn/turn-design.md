---
parent: high-level-design
prefix: TURN
---

# Turn

## Context and Design Philosophy

This component moves the game through the steps of a turn and from one seat's turn to the next. It performs the bookkeeping that needs no decision — untapping, drawing, emptying mana pools — and it stops at the moments that do need one: when a step trigger would happen, when cards must be discarded, and, in a contested game, when the end step's response window opens. It owns one tool, `advance`, which only the active seat calls.

In a goldfish game only the tested seat takes turns; the three imaginary opponents take none. In a contested game the seats still in the game take turns in turn order (see `game`).

## Steps

In order:

```
untap · upkeep · draw · main1 · begin_combat · declare_attackers ·
declare_blockers · combat_damage · end_combat · main2 · end · cleanup
```

Entering a step performs that step's automatic action, if it has one:

| Step | On entering |
|---|---|
| `untap` | The table turn number — the count of turns begun by all seats — and the active seat's turn count increase by one. Every permanent the active seat controls untaps. The active seat's land drops used resets to zero and its turn's statistics reset (see `records`). |
| `draw` | The active seat draws one card — except on the first turn of a game created with `draw_first_turn` false, whichever seat takes that turn. |
| `combat_damage` | The declared attack's damage is applied (see `combat`). |
| `end` | In a contested game, the end-step response window opens (see `stack`). |
| `cleanup` | Any discard is made from the active seat's hand, then the turn's snapshot is written (see `records`). |

Leaving any step empties every seat's mana pool.

The active seat may stop in any step. Stopping in a step with an automatic action is allowed; the action has already happened by then. Changes the agent makes while stopped in `cleanup` are not added to the snapshot already written.

## Turns and Rounds

A turn belongs to the active seat. When the active seat leaves `cleanup`, its turn ends and the next seat in turn order that is still in the game becomes the active seat and begins its turn by entering `untap`. In a goldfish game the next seat is the same seat.

The first turn of a game begins round 1. A new **round** begins when the turn passes to a seat that comes earlier in turn order than the seat whose turn just ended, or to the same seat when it is the only one left. The status line's `T<n>` is the number of turns the viewing seat has begun, so a seat's turn numbers mean the same in a goldfish game and a contested one; records also keep the table turn number and the round.

When the active seat is eliminated during its turn (see `game`), its turn ends: the declared attack and any pending `blocks` choices are discarded, other seats' items still on the stack are asked about and resolve as usual, and pending choices that still wait are answered. An attack or end-step window that was open asks no one further: it closes when the stack is empty. Once the stack is empty and no pending choice waits, the turn's snapshot is written as at cleanup (see `records`), every mana pool empties and the next seat begins its turn as below. When no seat is left in the game, no turn begins and the game has no active seat (see `game`).

### Beginning another seat's turn

In a contested game an advance never goes past the end of the active seat's turn. Leaving `cleanup` ends the call's advance; the next seat's turn then proceeds at once, within the same call, through its `untap`, `upkeep` and `draw` steps to its first main step, exactly as an advance to `main1` would, stopping where a reminder stops it. The new active seat is then the seat to act. The response to the call shows the turn passing; the card the new active seat drew is shown only to that seat.

## `advance`

```
advance(game_id, to?, discard?, override?)
```

Only the active seat advances, and only when it is the seat to act; in a contested game the stack must also be empty and no window open (see `stack`). With no `to`, the game moves to the next step. With `to`, the game moves forward through every step up to and including the next occurrence of the named step; if the game is already in that step, the next occurrence is in the following turn. Automatic actions happen along the way. The response lists the steps entered, any card drawn, reminders and notices. An unknown step name is an error.

An advance can stop short of its target for the reasons below. A stop is not a refusal: the response is `OK`, the game has moved as far as the stop, and the response says why it stopped and what to send next, with the change number to pass as `after`. The service does not remember the target; the agent sends `advance` again with the same `to`.

### Stopping for reminders

When the game enters a step in which a permanent has a step trigger for that step, `advance` stops in that step even if `to` names a later one. Which permanents count depends on whose turn it is, from the trigger reading's `whose` (see `card-reading`):

| Permanent controlled by | Reminded for a trigger on |
|---|---|
| The active seat | its controller's turn, or each turn |
| Another seat (contested games) | each turn, or each opponent's turn |
 This gives the agent the chance to resolve the trigger with an `effect` call at the right moment — before the draw for an upkeep trigger, for instance — rather than learning of it after the fact. A step the game is *leaving* never stops an advance; only a step being entered does.

```
advance(g7, to="main1")

OK end → cleanup → T7 untap → upkeep
Reminder (upkeep): Phyrexian Arena
Stopped at upkeep for the reminder. Send advance(to="main1", after=42) again to continue.
T7 upkeep · Hand 4 · Lands 6 (6 untapped) · ... · #42
```

Reminders are found from the step-trigger readings of the face in play of each permanent on the battlefield, each read from its owner's deck (see `game`). One reminder is issued per permanent, to the seat that controls it; several permanents with the same name and controller are listed once with a count (`Rhystic Study ×2`).

A reminder for the active seat is not enforced and is never waited on: the active seat may record the trigger with `effect` or advance straight on, and `pass` remains an error for it.

A reminder for another seat makes that seat a seat to act (see `game`). The game waits on it until each of its reminders of that step is answered or it passes:

- an `effect` that goes on the stack and whose `source` names a reminded permanent, by the rule in `records`, records that trigger and answers the reminders of every permanent it names;
- `pass` declines every reminder of that step the seat has not answered (see `stack`);
- a `play`, an `effect` with `immediate: true`, or an `effect` that names no reminded permanent, is applied as it would be in a response window, and the reminders still wait.

Several seats' reminders are taken one seat at a time, in turn order from the active seat. While any such reminder waits, the stack stands still: no seat is asked about the items the reminded seats have put on it, no automatic pass is made and nothing resolves. The asking for the top item begins once the last reminded seat has answered or passed, so every reminded seat records its trigger before any of them resolves. Once the stack is empty again and no pending choice waits, the active seat is the seat to act and continues with `advance` — except in `end`, where the end-step response window is open and its asking of the other seats begins at that point (see `stack`).

### Stopping at the end step

In a contested game, entering `end` opens the end-step response window, and the advance stops there even if `to` names a later step. The response says the other seats are being asked and which seat is asked first. When the window closes, the active seat is the seat to act and sends `advance` again to continue.

When every other seat is passed automatically, or none is left in the game, the window closes within the advance and nothing waits: the advance goes on toward its `to`, and the response reports the automatic passes.

### Stopping before cleanup

The active seat's hand may hold at most seven cards at cleanup. When an advance is about to enter `cleanup` with more than seven cards in hand and the call gives neither `discard` nor `override`, it stops in `end` instead and says how many cards must be discarded.

Entering `cleanup` with more than seven cards in hand therefore needs one of:

- `discard` naming exactly the excess number of cards in hand: they are discarded on entering cleanup;
- `override` with a reason: no discard is made, for effects that remove the maximum hand size;
- both, with `discard` naming any number of cards: the named cards are discarded as given.

Refusals:

- An advance that *starts* in `end` with more than seven cards in hand and gives neither `discard` nor `override` is refused as a rule check, and the game does not move. This is the same condition as the stop, met when there is nowhere earlier to stop.
- `discard` naming a number of cards different from the excess — counted on entering `cleanup`, so cards drawn on the way count — without `override`, is a rule check, and the game does not move.
- `discard` naming a card not in hand is an error.
- `discard` given on an advance that does not enter `cleanup` — because the target is earlier, or the advance stopped for a reminder first — is an error, and the game does not move.

A refused advance never moves the game.

## Turn Limit

`turn_limit` is not enforced. Entering the first turn of round `turn_limit` raises the turn-limit notice (see `game`), and the tested seat decides when to end the game. In a goldfish game every turn is a round.

## Returning to Combat

An additional combat (see `combat`) moves the game back to `declare_attackers` within the same turn. This is the only backward move. It empties the mana pool like leaving any step, does not change the turn number, and the steps then proceed forward again from `declare_attackers`.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Reminders during a multi-step advance | Stop in the step that has the reminder | Pass through and list reminders afterwards | A trigger that looks at or changes the library before the draw gives a different game if resolved after it. Stopping costs one extra call on turns that have a trigger. |
| Too many cards at cleanup | Stop in `end` and ask for the discard | Refuse the whole advance; advance to cleanup and refuse there | The hand at cleanup cannot always be known when the call is made, since a draw may lie in between. A stop moves the game as far as it safely can and is not a refusal, so a refused call still never changes state. |
| Remembering the target after a stop | Not remembered; the agent repeats `to` | Service stores the target | No hidden state between calls; the response spells out what to send. |
| Which steps the agent can stop in | All of them | Only steps without automatic actions | One rule, no exceptions to learn; stopping in `untap` is useless but harmless. |
| `to` naming the current step | Next occurrence, in the following turn | No-op; error | "Advance to main1" from main1 can only sensibly mean next turn's. |
| Imaginary opponents' turns | Do not exist | Model three empty turns | Nothing happens in them that the service tracks. |
| How far an advance goes in a contested game | To the end of the active seat's turn; the next turn proceeds to its first main step in the same call | The caller's `to` crossing into other seats' turns | A seat must not move the game through another seat's turn; proceeding to the next main step spares the new active seat calls for steps with nothing to do. |
| Another seat's step triggers | A reminder that makes that seat a seat to act | Listed to the active seat only; not reminded | The trigger is the other seat's to record, and it can only record when it is a seat to act. |
| How long a reminded seat is waited on | Until each of its reminders is answered by an `effect` naming the permanent, or it passes | One `effect` or `pass` ends the wait; one call for each reminder, a `pass` for each declined | A seat with two reminded permanents would lose the second trigger after one `effect`. One `pass` for all that remain keeps a seat that wants none of them to a single call. |
| The stack while reminders wait | Stands still until every reminded seat has answered or passed | Automatic passes and resolution go on at once | A first seat's trigger could otherwise resolve inside its own call, before a later seat had been asked for a trigger of the same step. Every trigger of a step goes on the stack before any resolves, as at a table. |
| `play` from a seat waited on for a reminder | Accepted as in a response window; the reminder still waits | Refused; accepted and ends the wait | The seat is a seat to act, and what it may cast is already limited by the timing rule check. Ending the wait would lose the trigger it was reminded of. |
| `pass` from the active seat at its own reminder | An error, as at any other moment with no window open | Accepted as declining the trigger | Nothing waits on the active seat for its reminder, so there is nothing for a pass to answer; `pass` keeps one meaning, an answer to being asked. |
| An end-step window that every seat is passed through automatically | The advance goes on | The advance stops in `end` anyway | A stop exists so that someone can act. With no one asked, stopping costs the active seat a call for nothing, as an automatic pass spares the others theirs. |
| Which seat `draw_first_turn` false applies to | The seat that takes the first turn of the game | Seat number 1 | The switch models going first. When seat number 1 concedes during mulligans, another seat goes first. |
| The next turn after the active seat is eliminated | Begins once the stack is empty and no pending choice waits | Begins as soon as the stack is empty | A discard or sacrifice another seat still owes was required by an effect that resolved during the ended turn; a new turn should not begin with it outstanding. |
| When a round begins | When turn order wraps: the turn passes to a seat earlier in turn order than the one whose turn just ended | Whenever the first seat still in the game begins a turn | When the first seat is eliminated during its own turn, the seat after it becomes the first seat still in the game and would begin a new round after a round of one turn. Counting the wrap keeps a round one turn for each seat still in the game. |
| What `T<n>` counts | The viewing seat's own turns | The table turn number | "Turn 7" then means the same for a deck in a goldfish game and in a contested one. |
| Turn limit in a contested game | In rounds | In table turns; in the tested seat's turns | A round is the unit of a multiplayer game. |
| Until-end-of-turn effects | Not tracked | Expire them at cleanup | The service does not know what effects are in force; the agent accounts for them. |

## Open Questions & Future Decisions

### Deferred
1. Reminders for permanents in zones other than the battlefield.
2. Extra turns and extra steps other than extra combats; the agent models these by continuing to advance.
3. A new active seat stopping in its own upkeep or draw step with no reminder, to act there; today it acts from its first main step.

## References

- `docs/high-level-design.md`
- `docs/intent/card-reading/card-reading-design.md` (step triggers)
- `docs/intent/combat/combat-design.md`
- `docs/intent/stack/stack-design.md` (the end-step window, `pass`)
- `docs/intent/game/game-design.md` (status, notices, change number)
- `docs/intent/records/records-design.md` (snapshots, reminder records)
