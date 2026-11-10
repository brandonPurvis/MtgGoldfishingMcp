---
parent: high-level-design
prefix: CMBT
---

# Combat

## Context and Design Philosophy

Combat is mostly arithmetic: which creatures attack, which get through, how much damage that is. The service taps the attackers, adds up the damage to players from card data, and keeps the running totals. It owns one tool, `attack`.

In a goldfish game the agent decides everything, including what the imaginary opponents block. In a contested game each attacker attacks a seat, the attacked seats declare their own blockers, and the attacking seat states what happens to the creatures. The service does not work out combat between creatures: power, toughness and keywords are changed by too many effects for card data to be reliable.

## `attack`

```
attack(game_id, attackers, targets?, blocked?, commander_target?, damage?, vigilance?, haste?, reason?, override?)
```

| Parameter | Meaning |
|---|---|
| `attackers` | The attacking creatures, by name or instance id. |
| `targets` | Contested games: the seat each attacker attacks — one seat number for all, or a map from attacker to seat number. Required in a contested game with more than one opponent; with one opponent it defaults to that seat. |
| `blocked` | Goldfish games: those among the attackers that the agent decides are blocked. |
| `commander_target` | Goldfish games: which imaginary opponent (0, 1 or 2) an attacking commander attacks. With two attacking commanders, either one number for both or a map from commander to number. Defaults to 0. |
| `damage` | Map from attacker to the damage it deals, replacing the default. |
| `vigilance` | Attackers that have vigilance beyond what the service has read. |
| `haste` | Attackers that have haste beyond what the service has read. |

Names follow the usual rules (see `game`): a name given twice means two different creatures, and an instance id singles out one of several identical creatures in any of these lists and maps. `vigilance` and `haste` apply to this declaration only; they are not remembered for later calls.

### When it may be called

Only the active seat attacks, when it is the seat to act; in a contested game the stack must be empty and no window open (see `stack`), and an `attack` at any other moment is an error.

| Game is in | `attack` |
|---|---|
| `main1`, `begin_combat` | Moves the game to `declare_attackers`, doing what `advance` would on the way, and declares. Reminders for `begin_combat` are listed in the response; the attack is declared regardless. |
| `declare_attackers` | Declares, staying in the current step. |
| `declare_blockers` with no attack declared | Goldfish games: declares, staying in the current step. Contested games: an error; the `blocks` choices are created on entering the step, so an attack declared after that would go unblocked. |
| `declare_attackers` or `declare_blockers`, with an attack already declared | Goldfish games: replaces the declaration. Attackers tapped by the earlier declaration stay tapped and are not refused for being tapped. Contested games: an error; an attack is declared once for each combat. |
| `untap`, `upkeep`, `draw` | Rule check: combat this early skips the first main step. With an override, proceeds as from `main1`. |
| `combat_damage` or later | Rule check: combat is over for this turn. With an override this is an additional combat: the game returns to `declare_attackers` of the current turn (see `turn`) and declares. Creatures tapped by an earlier declaration this turn are not refused for being tapped. |

An empty `attackers` list is accepted: it moves the game and is checked for timing as any attack is, and declares no attack. In a goldfish game it clears an earlier declaration. In a contested game it opens no response window and leaves the seat free to declare an attack afterwards.

A refused `attack` changes nothing, including the step.

### What happens on declaring

Each attacker is tapped unless it has vigilance: its own, granted by a permanent the service has read (including the attacker's own grant when that grant includes itself), or listed in `vigilance`. The declaration is stored on the game.

In a contested game, declaring attackers opens a response window (see `stack`), in which other seats may remove or change attackers before blocks. An attacker that has left the battlefield or changed control by the time of blocks, or whose target seat has been eliminated, is removed from the declaration.

## Blocks in a Contested Game

When the active seat advances into `declare_blockers` with an attack declared, each attacked seat still in the game, in turn order from the active seat, receives a pending choice of kind `blocks` showing the attackers attacking it. The seat answers with `choose`:

```
blocks: { [blocker]: attacker }      // each blocking creature and the attacker it blocks
```

Blockers are named among the creatures the answering seat controls on the battlefield; attackers among the attackers attacking that seat. Several blockers may block one attacker. An empty `blocks` declares no blocks. Errors: a blocker the seat does not control on the battlefield; an attacker not attacking that seat; a blocker named twice. Rule checks: a blocker that is tapped, or whose type line does not include `Creature`.

A seat with no untapped creatures is not asked: the service declares no blocks for it and reports that, as it reports an automatic pass.

An attacker named in any `blocks` answer is blocked. When every attacked seat has answered, the active seat is the seat to act again.

## The Result of Combat Between Creatures

The attacking seat states what happens to the creatures — which die, which survive, what else combat damage causes to them — with an `effect` that has `immediate: true`, normally once the game is in `combat_damage`. That delta may move and change any seat's permanents as `play` allows; the service applies it as stated and does not check it against the creatures' power and toughness. Combat damage to seats is not part of it: the service adds that up, below.

### Refusals

Errors:

- an attacker that is not on the battlefield, naming the zone it is in when it is elsewhere;
- an attacker the attacking seat does not control;
- an entry in `blocked`, `damage`, `vigilance`, `haste` or `targets` that is not among the attackers;
- a `commander_target` outside 0–2, or a `commander_target` map naming something that is not an attacking commander;
- in a contested game: an `attack` when an attack has already been declared for the current combat; `blocked` or `commander_target` given; a target that is the attacking seat itself, not a seat number in the game, or an eliminated seat; an attacker with no target when the game has more than one opponent;
- in a goldfish game: `targets` given.

Rule checks, overridable:

- an attacker whose type line (for a token, its `types`) does not include `Creature`;
- an attacker that is tapped, other than by an earlier attack declaration this turn;
- an attacker that entered the battlefield this turn and has no haste — its own, granted by a permanent the service has read (including the attacker's own grant when that grant includes itself), or listed in `haste`;
- an attacker whose power is not a number (`*`, or absent) with no entry in `damage`;
- the two timing checks in the table above.

## Combat Damage

When the game enters `combat_damage`, the declared attack is applied and cleared. Each attacker that is not blocked and is on the battlefield at that moment deals its damage: the `damage` entry if there is one, otherwise the power of its face in play plus its `+1/+1` counters minus its `-1/-1` counters, never less than zero.

In a goldfish game:

- that damage is added to the pooled damage against the imaginary opponents;
- if the attacker is a commander, the same amount is also added to that commander's damage against its target opponent;
- blocked attackers deal nothing to opponents. An agent that wants a blocked creature's trample or other damage counted gives it in `damage` and leaves the creature out of `blocked`.

In a contested game:

- that damage is taken from the life of the seat the attacker attacks;
- if the attacker is a commander, the same amount is added to that commander's damage against that seat;
- a blocked attacker deals damage to its seat only through its `damage` entry, which the attacking seat gives for trample; without one it deals none;
- eliminations are then applied (see `game`).

The response for the call that enters `combat_damage` shows each attacker's damage and the new totals. Entering `combat_damage` with no declared attack does nothing.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Who decides blocks in a goldfish game | The agent, per attack | Never blocked; a fixed fraction blocked | Opponents are imaginary; the agent is the only party that can model them, and a goldfish game usually assumes none. |
| Who decides blocks in a contested game | Each attacked seat, through a `blocks` pending choice | The attacking seat | Blocking is the defender's decision and depends on what only it knows. |
| Combat between creatures | Stated by the attacking seat as an immediate `effect` | Computed by the service from power, toughness and keyword readings; stated by the defending seat | Too many effects change power, toughness and keywords for card data to be reliable. The attacking seat already states its creatures' damage. |
| A blocked attacker's damage to a seat | Only through `damage` | Excess power over blockers' toughness | Trample is the attacker's to claim, as damage modifiers already are. |
| Seats with nothing to block with | Not asked; no blocks declared and reported | Asked anyway | A call with only one possible answer costs a round trip for nothing, as an automatic pass does. |
| Default damage | Power from card data adjusted by ±1 counters | Agent always states damage | Covers most attackers with no extra tokens; `damage` covers pumps, double strike and trample. |
| Non-numeric power | Refused unless `damage` is given | Treated as zero | A silent zero would understate the deck; asking costs one retry and only for such creatures. |
| Summoning sickness on attackers | Rule check | Not checked | It is a frequent agent error that inflates results, and card data is enough to catch it. |
| Target of ordinary damage in a goldfish game | Pooled, no target | Per-attacker opponent | See `game`: only commander damage needs a target. |
| Target in a contested game | A seat per attacker, defaulting to the only opponent | One seat per attack | Attacking several opponents at once is ordinary in multiplayer Commander. |
| Re-declaring in a goldfish game | A later `attack` before damage replaces the earlier | Error on a second call | Lets the agent correct a declaration without an override. |
| Re-declaring in a contested game | Error: one declaration for each combat | Replace the earlier declaration, as in a goldfish game | The first declaration opened the attack window and other seats have answered it, with removal or with a pass; replacing it would undo what they answered. An additional combat is a new combat and takes its own declaration. |
| Attacking with another seat's creature | Error | Rule check | Whose creature it is is structure, not an approximation from card data; a seat that has taken control of a creature says so with `control` first. |
| Attacking before the first main step | Rule check | Allowed silently; error | Almost always a mistake that would skip the agent's land drop and spells; overridable for the rare deliberate case. |
| Extra combats | An overridden `attack` after combat returns to `declare_attackers` | A separate tool | Rare enough not to earn its own tool. |

## Open Questions & Future Decisions

### Deferred
1. First strike and double strike as separate damage steps.
2. Damage dealt to the agent by imaginary blockers or attackers in a goldfish game; the agent records it with a `life` delta.
3. Attacking planeswalkers and battles; the attacking seat records such damage in its combat result.

## References

- `docs/high-level-design.md`
- `docs/intent/game/game-design.md` (damage totals, notices, naming cards)
- `docs/intent/turn/turn-design.md` (steps, returning to combat)
- `docs/intent/card-reading/card-reading-design.md` (haste, vigilance)
- `docs/intent/stack/stack-design.md` (the attack window; `immediate` effects)
- `docs/intent/play/play-design.md` (pending choices)
