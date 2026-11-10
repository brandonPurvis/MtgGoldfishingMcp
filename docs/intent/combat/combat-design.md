---
parent: high-level-design
prefix: CMBT
---

# Combat

## Context and Design Philosophy

Combat against imaginary opponents is mostly arithmetic: which creatures attack, which get through, how much damage that is. The agent decides all of it, including what the opponents block. The service taps the attackers, adds up the damage from card data, and keeps the running totals. It owns one tool, `attack`.

## `attack`

```
attack(game_id, attackers, blocked?, commander_target?, damage?, vigilance?, haste?, reason?, override?)
```

| Parameter | Meaning |
|---|---|
| `attackers` | The attacking creatures, by name or instance id. |
| `blocked` | Those among the attackers that the agent decides are blocked. |
| `commander_target` | Which opponent (0, 1 or 2) an attacking commander attacks. With two attacking commanders, either one number for both or a map from commander to number. Defaults to 0. |
| `damage` | Map from attacker to the damage it deals, replacing the default. |
| `vigilance` | Attackers that have vigilance beyond what the service has read. |
| `haste` | Attackers that have haste beyond what the service has read. |

Names follow the usual rules (see `game`): a name given twice means two different creatures, and an instance id singles out one of several identical creatures in any of these lists and maps. `vigilance` and `haste` apply to this declaration only; they are not remembered for later calls.

### When it may be called

| Game is in | `attack` |
|---|---|
| `main1`, `begin_combat` | Moves the game to `declare_attackers`, doing what `advance` would on the way, and declares. Reminders for `begin_combat` are listed in the response; the attack is declared regardless. |
| `declare_attackers` | Declares. |
| `declare_attackers` or `declare_blockers`, with an attack already declared | Replaces the declaration. Attackers tapped by the earlier declaration stay tapped and are not refused for being tapped. |
| `untap`, `upkeep`, `draw` | Rule check: combat this early skips the first main step. With an override, proceeds as from `main1`. |
| `combat_damage` or later | Rule check: combat is over for this turn. With an override this is an additional combat: the game returns to `declare_attackers` of the current turn (see `turn`) and declares. |

An empty `attackers` list is accepted: it declares no attack, and clears an earlier declaration.

A refused `attack` changes nothing, including the step.

### What happens on declaring

Each attacker is tapped unless it has vigilance: its own, granted by another permanent the service has read, or listed in `vigilance`. The declaration is stored on the game.

### Refusals

Errors:

- an attacker that is not on the battlefield;
- an entry in `blocked`, `damage`, `vigilance` or `haste` that is not among the attackers;
- a `commander_target` outside 0–2, or a `commander_target` map naming something that is not an attacking commander.

Rule checks, overridable:

- an attacker whose type line (for a token, its `types`) does not include `Creature`;
- an attacker that is tapped, other than by this turn's earlier declaration;
- an attacker that entered the battlefield this turn and has no haste — its own, granted, or listed in `haste`;
- an attacker whose power is not a number (`*`, or absent) with no entry in `damage`;
- the two timing checks in the table above.

## Combat Damage

When the game enters `combat_damage`, the declared attack is applied and cleared:

- each attacker not in `blocked` that is on the battlefield at that moment deals its damage: the `damage` entry if there is one, otherwise the power of its face in play plus its `+1/+1` counters minus its `-1/-1` counters, never less than zero;
- that damage is added to `damage_dealt`;
- if the attacker is a commander, the same amount is also added to that commander's damage against its target opponent;
- blocked attackers deal nothing to opponents. An agent that wants a blocked creature's trample or other damage counted gives it in `damage` and leaves the creature out of `blocked`.

The response for the call that enters `combat_damage` shows each attacker's damage and the new totals. Entering `combat_damage` with no declared attack does nothing.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Who decides blocks | The agent, per attack | Never blocked; a fixed fraction blocked | Opponents are imaginary; the agent is the only party that can model them, and a goldfish game usually assumes none. |
| Default damage | Power from card data adjusted by ±1 counters | Agent always states damage | Covers most attackers with no extra tokens; `damage` covers pumps, double strike and trample. |
| Non-numeric power | Refused unless `damage` is given | Treated as zero | A silent zero would understate the deck; asking costs one retry and only for such creatures. |
| Summoning sickness on attackers | Rule check | Not checked | It is a frequent agent error that inflates results, and card data is enough to catch it. |
| Target of ordinary damage | Pooled, no target | Per-attacker opponent | See `game`: only commander damage needs a target. |
| Re-declaring | A later `attack` before damage replaces the earlier | Error on a second call | Lets the agent correct a declaration without an override. |
| Attacking before the first main step | Rule check | Allowed silently; error | Almost always a mistake that would skip the agent's land drop and spells; overridable for the rare deliberate case. |
| Extra combats | An overridden `attack` after combat returns to `declare_attackers` | A separate tool | Rare enough not to earn its own tool. |

## Open Questions & Future Decisions

### Deferred
1. First strike and double strike as separate damage steps.
2. Damage dealt to the agent by imaginary blockers or attackers; the agent records it with a `life` delta.

## References

- `docs/high-level-design.md`
- `docs/intent/game/game-design.md` (damage totals, notices, naming cards)
- `docs/intent/turn/turn-design.md` (steps, returning to combat)
- `docs/intent/card-reading/card-reading-design.md` (haste, vigilance)
