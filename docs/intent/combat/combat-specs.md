# Combat — Specs

Design: `combat-design.md`. Prefix: `CMBT`.

## When `attack` may be called

- [ ] **CMBT-001**: When `attack` is called while the game is in `main1` or `begin_combat`, the game shall move to `declare_attackers`, performing the automatic actions and issuing the reminders of the steps entered, and store the declaration.
- [ ] **CMBT-002**: When `attack` moves the game through `begin_combat`, the game shall declare the attack whether or not a reminder was issued for `begin_combat`, and the outcome shall list any such reminder.
- [ ] **CMBT-003**: When `attack` is called while the game is in `declare_attackers` with no attack declared, the game shall store the declaration.
- [ ] **CMBT-004**: When `attack` is called while the game is in `declare_attackers` or `declare_blockers` with an attack already declared, the game shall replace the earlier declaration.
- [ ] **CMBT-005**: If `attack` is called while the game is in `untap`, `upkeep` or `draw` and carries no `override`, then `attack` shall fail a rule check.
- [ ] **CMBT-006**: When `attack` is called while the game is in `untap`, `upkeep` or `draw` with an `override` reason, the game shall move to `declare_attackers` as from `main1` and store the declaration.
- [ ] **CMBT-007**: If `attack` is called while the game is in `combat_damage` or a later step of the turn and carries no `override`, then `attack` shall fail a rule check.
- [ ] **CMBT-008**: When `attack` is called while the game is in `combat_damage` or a later step of the turn with an `override` reason, the game shall return to `declare_attackers` of the current turn and store the declaration.
- [ ] **CMBT-009**: When `attack` is called with an empty `attackers` list, the game shall store no attack and clear any earlier declaration.
- [ ] **CMBT-010**: When `attack` is refused, the game shall be left exactly as it was, including its step.

## Declaring

- [ ] **CMBT-011**: When an attack is declared, the game shall tap each attacker that has no vigilance of its own, none granted by another permanent's reading, and is not listed in `vigilance`.
- [ ] **CMBT-012**: When an attack is declared, the game shall leave untapped each attacker that has vigilance of its own, granted by another permanent's reading, or listed in `vigilance`.
- [ ] **CMBT-013**: The game shall apply the `vigilance` and `haste` arguments of an `attack` call to that declaration only.

## Refusals

- [ ] **CMBT-014**: If `attack` names an attacker that is not on the battlefield, then `attack` shall return an error.
- [ ] **CMBT-015**: If `blocked`, `damage`, `vigilance` or `haste` names something that is not among the attackers, then `attack` shall return an error.
- [ ] **CMBT-016**: If `commander_target` is outside 0 to 2, or is a map naming something that is not an attacking commander, then `attack` shall return an error.
- [ ] **CMBT-017**: If an attacker's type line, or for a token its types, does not include `Creature`, then `attack` shall fail a rule check.
- [ ] **CMBT-018**: If an attacker is tapped other than by an earlier attack declaration in the same turn, then `attack` shall fail a rule check.
- [ ] **CMBT-019**: If an attacker entered the battlefield this turn and has no haste of its own, none granted by another permanent's reading, and is not listed in `haste`, then `attack` shall fail a rule check.
- [ ] **CMBT-020**: If an unblocked attacker's power is not a number and `damage` has no entry for it, then `attack` shall fail a rule check.
- [ ] **CMBT-021**: When `attack` fails one or more rule checks and carries an `override` reason, the game shall store the declaration and the outcome shall name the overridden checks.

## Combat damage

- [ ] **CMBT-022**: When the game enters `combat_damage` with a declared attack, each attacker that is not blocked and is on the battlefield at that moment shall deal its `damage` entry if it has one, and otherwise the power of its face in play plus its `+1/+1` counters minus its `-1/-1` counters, never less than zero.
- [ ] **CMBT-023**: When combat damage is dealt, the game shall add each attacker's damage to `damage_dealt`.
- [ ] **CMBT-024**: When an attacking commander deals combat damage, the game shall also add that damage to that commander's damage against its `commander_target` opponent, which is opponent 0 when none is given.
- [ ] **CMBT-025**: When the game enters `combat_damage`, attackers listed in `blocked` shall deal no damage to opponents.
- [ ] **CMBT-026**: When combat damage has been applied, the game shall clear the declared attack, and the outcome shall list each attacker's damage and the new damage totals.
- [ ] **CMBT-027**: When the game enters `combat_damage` with no declared attack, the game shall change no damage total.
