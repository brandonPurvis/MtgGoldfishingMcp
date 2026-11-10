---
parent: high-level-design
prefix: TURN
---

# Turn

## Context and Design Philosophy

This component moves the game through the steps of a turn. It performs the bookkeeping that needs no decision — untapping, drawing, emptying the mana pool — and it stops at the moments that do need one: when a step trigger would happen, and when cards must be discarded. It owns one tool, `advance`.

Only the agent's own turns exist. When one turn ends the next begins; the three imaginary opponents take no turns.

## Steps

In order:

```
untap · upkeep · draw · main1 · begin_combat · declare_attackers ·
declare_blockers · combat_damage · end_combat · main2 · end · cleanup
```

Entering a step performs that step's automatic action, if it has one:

| Step | On entering |
|---|---|
| `untap` | The turn number increases by one. Every permanent untaps. Land drops used resets to zero. The turn's statistics reset (see `records`). |
| `draw` | One card is drawn — except on turn 1 of a game created with `draw_first_turn` false. |
| `combat_damage` | The declared attack's damage is applied (see `combat`). |
| `cleanup` | Any discard is made, then the turn's snapshot is written (see `records`). |

Leaving any step empties the mana pool.

The agent may stop in any step. Stopping in a step with an automatic action is allowed; the action has already happened by then. Changes the agent makes while stopped in `cleanup` are not added to the snapshot already written.

## `advance`

```
advance(game_id, to?, discard?, override?)
```

With no `to`, the game moves to the next step. With `to`, the game moves forward through every step up to and including the next occurrence of the named step; if the game is already in that step, the next occurrence is in the following turn. Automatic actions happen along the way. The response lists the steps entered, any card drawn, reminders and notices. An unknown step name is an error.

An advance can stop short of its target for two reasons, below. A stop is not a refusal: the response is `OK`, the game has moved as far as the stop, and the response says why it stopped and what to send next, with the change number to pass as `after`. The service does not remember the target; the agent sends `advance` again with the same `to`.

### Stopping for reminders

When the game enters a step in which a permanent the agent controls has a step trigger, `advance` stops in that step even if `to` names a later one. This gives the agent the chance to resolve the trigger with an `effect` call at the right moment — before the draw for an upkeep trigger, for instance — rather than learning of it after the fact. A step the game is *leaving* never stops an advance; only a step being entered does.

```
advance(g7, to="main1")

OK end → cleanup → T7 untap → upkeep
Reminder (upkeep): Phyrexian Arena
Stopped at upkeep for the reminder. Send advance(to="main1", after=42) again to continue.
T7 upkeep · Hand 4 · Lands 6 (6 untapped) · ... · #42
```

Reminders are found from the step-trigger readings (see `card-reading`) of the face in play of each permanent on the battlefield. One reminder is issued per permanent; several permanents with the same name are listed once with a count (`Rhystic Study ×2`). Reminders are not enforced: the agent may advance straight on.

### Stopping before cleanup

The hand may hold at most seven cards at cleanup. When an advance is about to enter `cleanup` with more than seven cards in hand and the call gives neither `discard` nor `override`, it stops in `end` instead and says how many cards must be discarded.

Entering `cleanup` with more than seven cards in hand therefore needs one of:

- `discard` naming exactly the excess number of cards in hand: they are discarded on entering cleanup;
- `override` with a reason: no discard is made, for effects that remove the maximum hand size;
- both, with `discard` naming any number of cards: the named cards are discarded as given.

Refusals:

- An advance that *starts* in `end` with more than seven cards in hand and gives neither `discard` nor `override` is refused as a rule check, and the game does not move. This is the same condition as the stop, met when there is nowhere earlier to stop.
- `discard` naming a number of cards different from the excess, without `override`, is a rule check, and the game does not move.
- `discard` naming a card not in hand is an error.
- `discard` given on an advance that does not enter `cleanup` — because the target is earlier, or the advance stopped for a reminder first — is an error, and the game does not move.

A refused advance never moves the game.

## Turn Limit

`turn_limit` is not enforced. Entering the limit turn raises the turn-limit notice (see `game`), and the agent decides when to end the game.

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
| Opponents' turns | Do not exist | Model three empty turns | Nothing happens in them that the service tracks. |
| Until-end-of-turn effects | Not tracked | Expire them at cleanup | The service does not know what effects are in force; the agent accounts for them. |

## Open Questions & Future Decisions

### Deferred
1. Reminders for permanents in zones other than the battlefield.
2. Extra turns and extra steps other than extra combats; the agent models these by continuing to advance.

## References

- `docs/high-level-design.md`
- `docs/intent/card-reading/card-reading-design.md` (step triggers)
- `docs/intent/combat/combat-design.md`
- `docs/intent/game/game-design.md` (status, notices, change number)
- `docs/intent/records/records-design.md` (snapshots, reminder records)
