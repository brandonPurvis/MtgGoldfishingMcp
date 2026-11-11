---
parent: high-level-design
prefix: CMBT
---

# Combat

## Context and Design Philosophy

Combat is mostly arithmetic: which creatures attack, which get through, how much damage that is. The service taps the attackers, adds up the damage to players from card data, and keeps the running totals. It owns one tool, `attack`.

In a goldfish game the agent decides everything, including what the imaginary opponents block. In a contested game each attacker attacks a seat, the attacked seats declare their own blockers, the service checks those blocks against the attackers' evasion, and the attacking seat states what happens to the creatures and how much trample damage gets past the blockers. The service does not work out combat between creatures: power, toughness and keywords are changed by too many effects for card data to be reliable.

## `attack`

```
attack(game_id, attackers?, targets?, blocked?, commander_target?, damage?, vigilance?, haste?, evasion?, trample?, reason?, override?)
```

| Parameter | Meaning |
|---|---|
| `attackers` | The attacking creatures, by name or instance id. Required, except in an `attack` that states trample damage (see Trample Damage). |
| `targets` | Contested games: the seat each attacker attacks — one seat number for all, or a map from attacker to seat number. Required in a contested game with more than one opponent; with one opponent it defaults to that seat. |
| `blocked` | Goldfish games: those among the attackers that the agent decides are blocked. |
| `commander_target` | Goldfish games: which imaginary opponent (0, 1 or 2) an attacking commander attacks. With two attacking commanders, either one number for both or a map from commander to number. Defaults to 0. |
| `damage` | Map from attacker to the damage it deals, replacing the default. In a contested game it is the damage the attacker deals if it is not blocked. |
| `vigilance` | Attackers that have vigilance beyond what the service has read. |
| `haste` | Attackers that have haste beyond what the service has read. |
| `evasion` | Contested games: map from attacker to the evasion it has beyond what the service has read — `flying`, `horsemanship` or `unblockable` (can't be blocked), or a list of them — such as evasion a spell gave it until end of turn. |
| `trample` | Contested games, once blocks are known: map from a blocked attacker to its trample damage (see Trample Damage). |

Names follow the usual rules (see `game`): a name given twice means two different creatures, and an instance id singles out one of several identical creatures in any of these lists and maps. `vigilance`, `haste` and `evasion` apply to this declaration only; they are not remembered for later calls.

### When it may be called

Only the active seat attacks, when it is the seat to act; in a contested game the stack must be empty and no window open (see `stack`), and an `attack` at any other moment is an error.

| Game is in | `attack` |
|---|---|
| `main1`, `begin_combat` | Moves the game to `declare_attackers`, doing what `advance` would on the way, and declares. The active seat's own reminders for `begin_combat` are listed in the response; the attack is declared regardless. A reminder for another seat stops the move, as below. |
| `declare_attackers` | Declares, staying in the current step. |
| `declare_blockers` with no attack declared | Goldfish games: declares, staying in the current step. Contested games: an error; the `blocks` choices are created on entering the step, so an attack declared after that would go unblocked. |
| `declare_attackers` or `declare_blockers`, with an attack already declared | Goldfish games: replaces the declaration. Attackers tapped by the earlier declaration stay tapped and are not refused for being tapped. Contested games: an error; an attack is declared once for each combat. The one exception is an `attack` that states trample damage, in `declare_blockers` (see Trample Damage). |
| `untap`, `upkeep`, `draw` | Rule check: combat this early skips the first main step. With an override, proceeds as from `main1`. |
| `combat_damage` or later | Rule check: combat is over for this turn. With an override this is an additional combat: the game returns to `declare_attackers` of the current turn (see `turn`) and declares. Creatures tapped by an earlier declaration this turn are not refused for being tapped. |

An empty `attackers` list is accepted: it moves the game and is checked for timing as any attack is, and declares no attack. In a goldfish game it clears an earlier declaration. In a contested game it opens no response window and leaves the seat free to declare an attack afterwards.

In a contested game, when the move toward `declare_attackers` enters a step in which another seat is reminded of a step trigger (see `turn`), the `attack` stops in that step, as an `advance` would: nothing is declared, no attacker is tapped, and the reminded seat is the seat to act. The response is `OK`, says the attack was not declared, and says to send `attack` again. A beginning-of-combat trigger is thereby recorded before attackers are chosen, not after.

A refused `attack` changes nothing, including the step.

### What happens on declaring

Each attacker is tapped unless it has vigilance: its own, granted by a permanent the service has read that the attacker's controller controls (including the attacker's own grant when that grant includes itself; a permanent another seat controls grants nothing), or listed in `vigilance`. The attacker and every permanent that could grant it a keyword are each read from their owner's deck, whichever seat controls them (see `game`). The declaration, with any `evasion` it states, is stored on the game.

In a contested game, declaring attackers opens a response window (see `stack`), in which other seats may remove or change attackers before blocks. An attacker that has left the battlefield or changed control by the time of blocks, or whose target seat has been eliminated, is removed from the declaration. The same holds at combat damage: an attacker that has left the battlefield or changed control since blocks, or whose target seat has since been eliminated, deals no damage.

## Blocks in a Contested Game

When the active seat advances into `declare_blockers` with an attack declared, each attacked seat still in the game, in turn order from the active seat, receives a pending choice of kind `blocks` showing the attackers attacking it, each with the evasion the service holds for it (see Evasion). The seat answers with `choose`:

```
blocks: { [blocker]: attacker }      // each blocking creature and the attacker it blocks
```

Blockers are named among the creatures the answering seat controls on the battlefield; attackers among the attackers attacking that seat. Several blockers may block one attacker. An empty `blocks` declares no blocks. Errors: a blocker the seat does not control on the battlefield; an attacker not attacking that seat; a blocker named twice. Rule checks: a blocker that is tapped, or whose type line does not include `Creature`; a block the attacker's evasion forbids (see Evasion). With an override reason the blocks are recorded as given and the outcome names the overridden checks.

A seat with no untapped creatures is not asked: the service declares no blocks for it and reports that, as it reports an automatic pass.

An attacker named in any `blocks` answer is blocked, and stays blocked for the rest of the combat even if every creature blocking it leaves the battlefield. When every attacked seat has answered, the active seat is the seat to act again.

### Evasion

When a `blocks` answer is given, the service checks each blocker against the evasion of the attacker it blocks:

| Attacker has | A blocker may block it only if it has |
|---|---|
| flying | flying or reach |
| horsemanship | horsemanship |
| can't be blocked | — no blocker may |

An attacker with more than one evasion is checked for each, and each block that fails is a separate failed check. A failed check names the blocker, the attacker and the evasion, and says whether the service read it — with any assumption the reading carries — or the attacking seat stated it in `evasion`.

An attacker has an evasion when it has it of its own, when a permanent the attacker's controller controls grants it (including the attacker's own grant when that grant includes itself; a permanent another seat controls grants nothing), or when the `attack` that declared it lists that evasion for it in `evasion`. A blocker has flying, reach or horsemanship when it has it of its own or a permanent the answering seat controls grants it, on the same terms. A grant limited to a subtype reaches only creatures of that subtype. The attacker, the blocker and every permanent that could grant either of them a keyword are each read as `game` reads a card instance — a card from its owner's deck, whichever seat controls it; a token or a card with data of its own from that data — as they stand when the answer is given. An evasion both read and listed in `evasion` is one evasion, shown and checked once.

Evasion is judged only when blocks are declared, as in Magic: an attacker that gains or loses evasion afterwards keeps the blocks already recorded. The blocking seat has no parameter for flying or reach its blocker has only for this turn; it overrides the failed check with that as its reason. So does a blocking seat whose attacker has lost an evasion the service still reads.

The evasion checked is limited to flying, horsemanship and "can't be blocked", with reach as the blocker's answer to flying; see Open Questions for the rest.

## Trample Damage

In a contested game a blocked attacker deals no combat damage to the seat it attacks — neither its power nor its `damage` entry — unless the attacking seat states its trample damage. The attacking seat knows its blockers' toughness and what has happened to them, so it states that damage itself once blocks are known: after every attacked seat has answered its `blocks` choice, while the game is in `declare_blockers`, with an `attack` that gives `trample` and no declaration:

```
attack(game_id, trample: { [attacker]: damage })
```

Each entry is the combat damage that attacker deals the seat it attacks, its blockers already accounted for. The service does not check the amount against the attacker's power, its blockers' toughness or a trample reading. A blocked attacker whose blockers have all left the battlefield deals only its trample damage, which for an attacker with trample is normally all of it, as in Magic.

An `attack` that states trample damage declares nothing: it taps nothing, opens no response window, moves to no other step, and leaves the active seat the seat to act. It may follow spells the attacking seat casts once blocks are known. A later one replaces the trample damage of each attacker it names and leaves the others' as they were; an entry of 0 takes an earlier one back. Its outcome lists each named attacker with its trample damage and the seat it attacks, and every seat sees it.

Errors:

- `trample` in a goldfish game;
- `trample` given with `attackers` (even an empty list), `targets`, `damage`, `vigilance`, `haste` or `evasion`;
- `trample` when the game is not in `declare_blockers` with an attack declared;
- an entry naming something that is not among the declared attack's attackers, or an attacker that is not blocked;
- an amount that is not a whole number of zero or more.

An `attack` with neither `attackers` nor `trample` is an error, in either kind of game.

## The Result of Combat Between Creatures

The attacking seat states what happens to the creatures — which die, which survive, what else combat damage causes to them — with an `effect` that has `immediate: true`, normally once the game is in `combat_damage`. That delta may move and change any seat's permanents as `play` allows; the service applies it as stated and does not check it against the creatures' power and toughness. Combat damage to seats is not part of it: the service adds that up, below, trample damage included.

Nothing marks an `effect` as a combat result; it is an immediate effect like any other. A `life` or `damage` key in it is applied as stated — lifelink is stated this way — and the service deals the declared attack's damage on entering `combat_damage` regardless. A seat that states its attackers' damage to a seat in its combat result therefore counts it twice.

### Refusals

Errors:

- an attacker that is not on the battlefield, naming the zone it is in when it is elsewhere and the attacking seat may see that zone (see `game` for a card in another seat's hand or library);
- an attacker the attacking seat does not control;
- an entry in `blocked`, `damage`, `vigilance`, `haste`, `evasion` or `targets` that is not among the attackers;
- an `evasion` value other than `flying`, `horsemanship` or `unblockable`, or a non-empty list of distinct ones;
- a `commander_target` outside 0–2, or a `commander_target` map naming something that is not an attacking commander;
- in a contested game: an `attack` when an attack has already been declared for the current combat, other than one that states trample damage; `blocked` or `commander_target` given; a target that is the attacking seat itself, not a seat number in the game, or an eliminated seat; an attacker with no target when the game has more than one opponent; any attacker at all when no opponent is left in the game;
- in a goldfish game: `targets` or `evasion` given;
- the errors of Trample Damage.

Rule checks, overridable:

- an attacker whose type line (for a token, its `types`) does not include `Creature`;
- an attacker that is tapped, other than by an earlier attack declaration this turn;
- an attacker that entered the battlefield this table turn and has no haste — its own, granted by a permanent the service has read that the attacker's controller controls (including the attacker's own grant when that grant includes itself; a permanent another seat controls grants nothing), or listed in `haste`;
- an attacker whose power is not a number (`*`, or absent) with no entry in `damage`;
- the two timing checks in the table above.

## Combat Damage

When the game enters `combat_damage`, the declared attack is applied and cleared. Each attacker that is not blocked and is on the battlefield at that moment deals its damage: the `damage` entry if there is one, otherwise the power of its face in play plus its `+1/+1` counters minus its `-1/-1` counters, never less than zero.

In a goldfish game:

- that damage is added to the pooled damage against the imaginary opponents;
- if the attacker is a commander, the same amount is also added to that commander's damage against its target opponent;
- blocked attackers deal nothing to opponents. An agent that wants a blocked creature's trample or other damage counted gives it in `damage` and leaves the creature out of `blocked`.

In a contested game:

- an unblocked attacker's damage is taken from the life of the seat it attacks;
- a blocked attacker that is on the battlefield deals its trample damage, if it has any, to the seat it attacks, and otherwise nothing; its `damage` entry and its power are not used;
- if the attacker is a commander, the amount it deals that seat, trample damage included, is added to that commander's damage against that seat;
- eliminations are then applied (see `game`).

The response for the call that enters `combat_damage` shows each attacker's damage and the new totals. Entering `combat_damage` with no declared attack does nothing.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Who decides blocks in a goldfish game | The agent, per attack | Never blocked; a fixed fraction blocked | Opponents are imaginary; the agent is the only party that can model them, and a goldfish game usually assumes none. |
| Who decides blocks in a contested game | Each attacked seat, through a `blocks` pending choice | The attacking seat | Blocking is the defender's decision and depends on what only it knows. |
| Combat between creatures | Stated by the attacking seat as an immediate `effect` | Computed by the service from power, toughness and keyword readings; stated by the defending seat | Too many effects change power, toughness and keywords for card data to be reliable. The attacking seat already states its creatures' damage. |
| A blocked attacker's damage to a seat in a contested game | None, except the trample damage the attacking seat states once blocks are known | Its `damage` entry, given at declaration and dealt in full whether or not it is blocked; excess power over blockers' toughness, computed by the service | An entry given before blocks cannot know them: a pump stated as `damage` reached the seat even when the attacker was then blocked, and the attacking seat had to remember to give the life back. Computing the excess needs toughness and keywords that card data does not give reliably. Trample is the attacker's to claim, as damage modifiers already are. |
| How trample damage is stated | An `attack` giving `trample` alone, in `declare_blockers` once blocks are answered | A `trample` pending choice for the attacking seat after blocks; `trample` given on the declaration; a `damage` or `life` key in the combat result | A pending choice would cost a round trip on every blocked combat, or need a trample reading to know when to ask, and would make the attacking seat answer before casting tricks once blocks are known. On the declaration the blockers are unknown. Damage in the combat result is not combat damage: it would not count as commander damage, and a seat already warned not to state damage to seats there would have to state some. |
| Whether trample damage is checked | Not checked against power, toughness or a trample reading | A rule check when the attacker has no trample reading, or when the amount exceeds its power | The attacking seat states its creatures' damage already, unchecked; trample is often granted until end of turn, so a reading check would mostly be overridden. |
| Evasion when blocks are declared | Rule checks on the `blocks` answer, overridable | Not checked; errors | An illegal block made unnoticed changes the game as much as an untapped attacker does, and readings make it cheap to catch. The readings are approximations of card data, so a refusal is overridable, as the other blocks checks are. |
| Evasion an attacker has only this turn | Stated per attacker in `evasion` on `attack`, for that declaration only | Not stateable, the blocking seat trusted to honour it; remembered across calls | The attacking seat is the one that knows of its pump, and stating it on the declaration matches `vigilance` and `haste`. A statement remembered past its combat would outlive the effect that made it. |
| Flying or reach a blocker has only this turn | No parameter; the blocking seat overrides with that reason | A `choose` parameter stating blockers' keywords | It is rare, and an override records the reason in the same call; a parameter on `choose` used by one kind of choice would add surface for little. |
| Which evasion is checked | Flying (answered by flying or reach), horsemanship, "can't be blocked" | Also menace, fear, intimidate, shadow, protection, landwalk and "can't be blocked except by …" | These three cover most evasion in Commander and are decided from keyword readings of the attacker and blocker alone. The others need colors, artifact types, counts of blockers or text forms the reader does not yet handle; they wait in Open Questions. |
| Evasion shown on the `blocks` choice | Each attacker with the evasion the service holds for it | Not shown; shown only in the refusal | The blocking seat sees what the service will check before it answers, which spares a refused call; an evasion stated in `evasion` is otherwise only in the digest of the `attack`. |
| `attack` passing a step where another seat is reminded | Stops there undeclared; the seat sends `attack` again | Declares, then waits on the reminded seat; declares and opens the attack window first | A beginning-of-combat trigger recorded after attackers are tapped gives a different game, the reason an advance stops for a reminder. The active seat's own reminder does not stop it, since choosing to attack first is its own decision. |
| `life` and `damage` in a combat result | Applied as stated, like any immediate effect | An error; dropped silently | The service cannot tell a combat result from any other immediate effect, and lifelink and damage dealt by creatures to things other than seats are stated there. Refusing or dropping the keys would block legitimate statements to guard against one mistake the player brief can warn of. |
| Attackers that change after blocks | Checked again at combat damage: gone, changed control or aimed at an eliminated seat deals nothing | Checked only before blocks | A creature stolen or destroyed after blocks would otherwise still deal its damage, and could deal it to the seat that now controls it. |
| Attacking with no opponent left | Error | Stored with no target | There is no seat for the damage to go to; the tested seat that plays on alone can still move through combat with an empty `attackers` list. |
| Seats with nothing to block with | Not asked; no blocks declared and reported | Asked anyway | A call with only one possible answer costs a round trip for nothing, as an automatic pass does. |
| Default damage | Power from card data adjusted by ±1 counters | Agent always states damage | Covers most attackers with no extra tokens; `damage` covers pumps and double strike, and `trample` what gets past blockers. |
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
1. First strike and double strike as separate damage steps. Until then the attacking seat states the total, in `damage` for an unblocked attacker and in `trample` for a blocked one.
2. Damage dealt to the agent by imaginary blockers or attackers in a goldfish game; the agent records it with a `life` delta.
3. Attacking planeswalkers and battles; the attacking seat records such damage in its combat result.
4. Evasion not checked on blocks: menace, fear, intimidate, shadow, protection, landwalk and "can't be blocked except by …" or "by …"; restrictions on the blocker itself, such as "can't block" or "can block only creatures with flying". The blocking seat honours them unchecked.
5. Evasion an attacker gains after its attack is declared and before blocks are requested cannot be stated; the blocking seat honours it unchecked.

## References

- `docs/high-level-design.md`
- `docs/intent/game/game-design.md` (damage totals, notices, naming cards, reading a card from its owner's deck)
- `docs/intent/turn/turn-design.md` (steps, returning to combat)
- `docs/intent/card-reading/card-reading-design.md` (haste, vigilance, evasion, reach)
- `docs/intent/stack/stack-design.md` (the attack window; `immediate` effects)
- `docs/intent/play/play-design.md` (pending choices)
