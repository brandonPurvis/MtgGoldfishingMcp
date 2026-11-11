# Combat — Specs

Design: `combat-design.md`. Prefix: `CMBT`.

## When `attack` may be called

- [x] **CMBT-001**: When the active seat calls `attack` while the game is in `main1` or `begin_combat`, in a goldfish game or a contested game, the game shall move to `declare_attackers`, performing the automatic actions and issuing the reminders of the steps entered, and store the declaration, unless the move stops for another seat's reminder (CMBT-073).
- [x] **CMBT-002**: When `attack` moves the game through `begin_combat`, in a goldfish game or a contested game, the game shall declare the attack whether or not a reminder was issued to the active seat for `begin_combat`, and the outcome shall list any such reminder.
- [x] **CMBT-073**: When an `attack` of a contested game, moving toward `declare_attackers`, enters a step before `declare_attackers` in which a reminder is issued to a seat other than the active seat, the game shall stop in that step with no attack declared and no attacker tapped, the reminded seat becoming the seat to act as it does when an `advance` stops (TURN-051).
- [x] **CMBT-078**: When an `attack` of a contested game stops undeclared for another seat's reminder (CMBT-073), the outcome shall be `OK`, say that the attack was not declared, and say to send `attack` again with the change number to pass as `after`.
- [x] **CMBT-003**: When the active seat calls `attack` while the game is in `declare_attackers` in a goldfish game or a contested game, or in `declare_blockers` with no attack declared in a goldfish game, the game shall store the declaration without moving to another step.
- [x] **CMBT-004**: When the tested seat calls `attack` in a goldfish game while the game is in `declare_attackers` or `declare_blockers` with an attack already declared, the game shall replace the earlier declaration; attackers tapped by the earlier declaration stay tapped and are not refused for being tapped.
- [x] **CMBT-005**: If `attack` is called while the game is in `untap`, `upkeep` or `draw` and carries no `override`, in a goldfish game or a contested game, then `attack` shall fail a rule check.
- [x] **CMBT-006**: When `attack` is called while the game is in `untap`, `upkeep` or `draw` with an `override` reason, in a goldfish game or a contested game, the game shall move to `declare_attackers` as from `main1` and store the declaration.
- [x] **CMBT-007**: If `attack` is called while the game is in `combat_damage` or a later step of the turn and carries no `override`, in a goldfish game or a contested game, then `attack` shall fail a rule check.
- [x] **CMBT-008**: When `attack` is called while the game is in `combat_damage` or a later step of the turn with an `override` reason, in a goldfish game or a contested game, the game shall return to `declare_attackers` of the current turn and store the declaration.
- [x] **CMBT-009**: When `attack` is called with an empty `attackers` list, in a goldfish game or a contested game, the game shall move and check timing as for any attack and store no attack, and in a goldfish game shall clear any earlier declaration.
- [x] **CMBT-010**: When `attack` is refused, in a goldfish game or a contested game, the game shall be left exactly as it was, including its step.
- [x] **CMBT-028**: If a seat of a contested game that is not the active seat calls `attack`, then `attack` shall return an error and change nothing.
- [x] **CMBT-029**: If the active seat of a contested game calls `attack` while it is not the seat to act, because a pending choice or another seat's reminder is waiting on another seat, then `attack` shall return an error and change nothing.

## Declaring

- [x] **CMBT-011**: When an attack is declared, in a goldfish game or a contested game, the game shall tap each attacker that has no vigilance of its own, none granted by the reading of a permanent controlled by the seat that controls the attacker (never by a permanent another seat controls), including the attacker's own grant when it includes itself, and is not listed in `vigilance`.
- [x] **CMBT-012**: When an attack is declared, in a goldfish game or a contested game, the game shall leave untapped each attacker that has vigilance of its own, granted by a permanent's reading, including the attacker's own grant when it includes itself, or listed in `vigilance`.
- [x] **CMBT-013**: The game, goldfish or contested, shall apply the `vigilance` and `haste` arguments of an `attack` call to that declaration only.
- [ ] **CMBT-080**: When `attack` in a contested game declares attackers and gives `evasion`, the game shall hold each evasion listed for an attacker (`flying`, `horsemanship` or `unblockable`, one value or a list) as that attacker's for that declaration only, in addition to any evasion the game reads for it.
- [x] **CMBT-030**: When `attack` in a contested game gives `targets` as one seat number, every attacker shall attack that seat.
- [x] **CMBT-031**: When `attack` in a contested game gives `targets` as a map from attacker to seat number, each attacker shall attack the seat mapped to it, and different attackers may attack different seats in one declaration.
- [x] **CMBT-032**: When `attack` in a contested game gives no target for an attacker and the attacking seat has exactly one opponent still in the game, that attacker shall attack that opponent.
- [x] **CMBT-034**: When blocks are about to be requested in a contested game, the game shall remove from the declared attack every attacker that has left the battlefield since it was declared.
- [x] **CMBT-035**: When blocks are about to be requested in a contested game, the game shall remove from the declared attack every attacker whose controller has changed since it was declared.
- [x] **CMBT-036**: When blocks are about to be requested in a contested game, the game shall remove from the declared attack every attacker whose target seat has been eliminated.
- [x] **CMBT-074**: When a contested game enters `combat_damage`, an attacker whose controller has changed since it was declared shall deal no combat damage.
- [x] **CMBT-075**: When a contested game enters `combat_damage`, an attacker whose target seat has been eliminated shall deal no combat damage.

## Blocks in a contested game

- [x] **CMBT-037**: When the active seat of a contested game advances into `declare_blockers` with an attack declared, each attacked seat still in the game that controls an untapped creature shall receive a pending choice of kind `blocks` showing the attackers attacking it, the choices created in turn order starting from the seat after the active seat.
- [x] **CMBT-038**: When an advance of a contested game enters `declare_blockers` and creates a `blocks` pending choice, the advance shall stop in `declare_blockers` even when `to` names a later step.
- [x] **CMBT-039**: When a seat answers a `blocks` pending choice in a contested game with `choose` and a `blocks` map from blocker to attacker, the game shall record each attacker named in the map as blocked.
- [x] **CMBT-040**: When a seat answers a `blocks` pending choice in a contested game, the game shall accept several blockers naming the same attacker.
- [x] **CMBT-041**: When a seat answers a `blocks` pending choice in a contested game with an empty `blocks` map, the game shall record no blocks for that seat.
- [x] **CMBT-042**: If a `blocks` answer in a contested game names a blocker that the answering seat does not control on the battlefield, then `choose` shall return an error and change nothing.
- [x] **CMBT-043**: If a `blocks` answer in a contested game names an attacker that is not attacking the answering seat, then `choose` shall return an error and change nothing.
- [x] **CMBT-044**: If a `blocks` answer in a contested game names the same blocker twice, then `choose` shall return an error and change nothing.
- [x] **CMBT-045**: If a `blocks` answer in a contested game names a blocker that is tapped and carries no `override`, then `choose` shall fail a rule check and change nothing.
- [x] **CMBT-046**: If a `blocks` answer in a contested game names a blocker whose type line, or for a token its types, does not include `Creature` and carries no `override`, then `choose` shall fail a rule check and change nothing.
- [x] **CMBT-047**: When an attacked seat of a contested game controls no untapped creature at the time blocks are requested, the game shall give it no `blocks` pending choice, declare no blocks for it, and report in the outcome that it did so, naming the seat.
- [x] **CMBT-048**: When every `blocks` pending choice of a combat in a contested game has been answered, the active seat shall be the seat to act again.
- [x] **CMBT-049**: In a contested game, a `blocks` pending choice shall show an attacked seat only the attackers attacking that seat, and shall accept blocks only against those attackers.
- [ ] **CMBT-081**: In a contested game, a `blocks` pending choice shall show, for each attacker it lists, every evasion the game holds for that attacker under CMBT-087, whether read or listed in `evasion`, as the game holds it at the moment the choice or its listing is shown.
- [ ] **CMBT-082**: When a seat of a contested game answers a `blocks` pending choice naming a blocker against an attacker, that attacker shall stay blocked until combat damage is applied, even if every creature blocking it leaves the battlefield.

## Evasion on blocks in a contested game

- [ ] **CMBT-083**: If a `blocks` answer in a contested game names, against an attacker that has flying, a blocker that has neither flying nor reach, and carries no `override`, then `choose` shall fail a rule check and change nothing.
- [ ] **CMBT-084**: If a `blocks` answer in a contested game names, against an attacker that has horsemanship, a blocker that does not have horsemanship, and carries no `override`, then `choose` shall fail a rule check and change nothing.
- [ ] **CMBT-085**: If a `blocks` answer in a contested game names any blocker against an attacker that can't be blocked, and carries no `override`, then `choose` shall fail a rule check and change nothing.
- [ ] **CMBT-086**: When a `blocks` answer in a contested game names a blocker that has flying, reach, or both against an attacker that has flying, the game shall fail no flying check for that block.
- [ ] **CMBT-087**: In a contested game, when judging a `blocks` answer, an attacker shall have flying, horsemanship or "can't be blocked" when it has it of its own, when it is granted by the reading of a permanent controlled by the seat that controls the attacker (never by a permanent another seat controls), including the attacker's own grant when it includes itself, or when the `attack` that declared it listed that evasion for it in `evasion`; a grant limited to a subtype reaches only an attacker whose type line, or for a token its types, includes that subtype.
- [ ] **CMBT-088**: In a contested game, when judging a `blocks` answer, a blocker shall have flying, reach or horsemanship when it has it of its own, or when it is granted by the reading of a permanent controlled by the answering seat (never by a permanent another seat controls), including the blocker's own grant when it includes itself; a grant limited to a subtype reaches only a blocker whose type line, or for a token its types, includes that subtype.
- [ ] **CMBT-089**: In a contested game, when judging a `blocks` answer, the game shall read each attacker, each blocker, and every permanent that could grant a keyword to an attacker or a blocker as GAME-171 reads a card instance (a card from its owner's deck, whichever seat controls it; a token or an instance with card data of its own from that data), as they stand when the answer is given.
- [ ] **CMBT-090**: When a `blocks` answer in a contested game fails an evasion check, the refusal shall name, for each failed block, the blocker, the attacker and the evasion, and say where the game holds that evasion from: read, with any assumption of the reading; listed by the attacking seat in `evasion`; or both.
- [ ] **CMBT-091**: When a `blocks` answer in a contested game fails one or more evasion checks and carries an `override` reason, the game shall record the blocks as given and the outcome shall name the overridden checks.
- [ ] **CMBT-092**: In a contested game, the game shall judge evasion only when a `blocks` answer is given, and shall leave the blocks it has recorded unchanged when an attacker later gains or loses an evasion.

## The result of combat between creatures

- [x] **CMBT-050**: In a contested game, the game shall not move, destroy or mark damage on any creature as a result of combat on its own: what happens to attacking and blocking creatures is only what a seat's delta states.
- [x] **CMBT-051**: When the attacking seat of a contested game states the result of combat between creatures with an `effect` that has `immediate` true, the game shall apply it as any other immediate `effect`, with nothing marking it as a combat result: every key of its delta, `life` and `damage` included, is applied at once as stated, to any seat's permanents and life that a delta may reach, without comparing it with the creatures' power or toughness.
- [x] **CMBT-052**: When a contested game enters `combat_damage`, the game shall deal the declared attack's combat damage to seats in full whatever any earlier `effect` stated, neither reducing it by nor matching it against the `life` or `damage` key of an immediate `effect`.

## Refusals

- [x] **CMBT-014**: If `attack` names an attacker that is not on the battlefield, in a goldfish game or a contested game, then `attack` shall return an error.
- [x] **CMBT-015**: If `blocked`, `damage`, `vigilance` or `haste` names something that is not among the attackers, in a goldfish game or a contested game, then `attack` shall return an error.
- [x] **CMBT-016**: If `commander_target` in a goldfish game is outside 0 to 2, or is a map naming something that is not an attacking commander, then `attack` shall return an error.
- [x] **CMBT-017**: If an attacker's type line, or for a token its types, does not include `Creature`, in a goldfish game or a contested game, then `attack` shall fail a rule check.
- [x] **CMBT-018**: If an attacker is tapped other than by an earlier attack declaration in the same turn, in a goldfish game or a contested game, then `attack` shall fail a rule check.
- [x] **CMBT-079**: In a contested game, when judging an attacker's haste and vigilance, the game shall read the attacker and every permanent that could grant it either keyword from each one's owner's deck, whichever seat controls it.
- [x] **CMBT-019**: If an attacker entered the battlefield during the current table turn (its `entered_turn` equals the table turn number, the count of turns begun by all seats) and has no haste of its own, none granted by the reading of a permanent controlled by the seat that controls the attacker (never by a permanent another seat controls), including the attacker's own grant when it includes itself, and is not listed in `haste`, in a goldfish game or a contested game, then `attack` shall fail a rule check.
- [x] **CMBT-020**: If an attacker in a goldfish game that is not listed in `blocked` has a power that is not a number and `damage` has no entry for it, then `attack` shall fail a rule check.
- [x] **CMBT-021**: When `attack` fails one or more rule checks and carries an `override` reason, in a goldfish game or a contested game, the game shall store the declaration and the outcome shall name the overridden checks.
- [x] **CMBT-053**: If `attack` names an attacker that is not on the battlefield but is in another zone, in a goldfish game or a contested game, then the error shall name the zone that card is in, except that for a card in another seat's hand or library it shall say only what GAME-156 and GAME-157 allow (nothing for a name; a hidden zone of that seat, not which, for an instance id).
- [x] **CMBT-054**: If `attack` in a contested game gives `blocked`, then `attack` shall return an error and change nothing.
- [x] **CMBT-055**: If `attack` in a contested game gives `commander_target`, then `attack` shall return an error and change nothing.
- [x] **CMBT-056**: If `attack` in a goldfish game gives `targets`, then `attack` shall return an error and change nothing.
- [x] **CMBT-057**: If `targets` in a contested game names something that is not among the attackers, then `attack` shall return an error and change nothing.
- [x] **CMBT-058**: If `targets` in a contested game gives the attacking seat's own seat number, a seat number that is not in the game, or the seat number of an eliminated seat, then `attack` shall return an error and change nothing.
- [x] **CMBT-059**: If `attack` in a contested game leaves an attacker without a target while the attacking seat has more than one opponent still in the game, then `attack` shall return an error and change nothing.
- [x] **CMBT-076**: If `attack` in a contested game names one or more attackers while the attacking seat has no opponent still in the game, then `attack` shall return an error and change nothing.
- [ ] **CMBT-093**: If `evasion` in a contested game names something that is not among the attackers, then `attack` shall return an error and change nothing.
- [ ] **CMBT-094**: If an `evasion` entry in a contested game is not `flying`, `horsemanship` or `unblockable`, or a non-empty list of distinct such values, then `attack` shall return an error and change nothing.
- [ ] **CMBT-095**: If `attack` in a goldfish game gives `evasion`, then `attack` shall return an error and change nothing.
- [ ] **CMBT-096**: If `attack` gives neither `attackers` nor `trample`, in a goldfish game or a contested game, an empty `attackers` list counting as given, then `attack` shall return an error and change nothing.
- [x] **CMBT-060**: If an attacker in a contested game has a power that is not a number and `damage` has no entry for it, then `attack` shall fail a rule check, whether or not the attacker is later blocked.

## Combat damage

- [x] **CMBT-022**: When the game enters `combat_damage` with a declared attack, in a goldfish game or a contested game, each attacker that is not blocked and is on the battlefield at that moment shall deal its `damage` entry if it has one, and otherwise the power of its face in play plus its `+1/+1` counters minus its `-1/-1` counters, never less than zero.
- [x] **CMBT-023**: When combat damage is dealt in a goldfish game, the game shall add each attacker's damage to the pooled damage against the imaginary opponents (`damage_dealt`).
- [x] **CMBT-024**: When an attacking commander deals combat damage in a goldfish game, the game shall also add that damage to that commander's damage against its `commander_target` imaginary opponent, which is opponent 0 when none is given; a single number given for `commander_target` applies to every attacking commander.
- [x] **CMBT-025**: When a goldfish game enters `combat_damage`, attackers listed in `blocked` shall deal no damage to the imaginary opponents.
- [x] **CMBT-026**: When combat damage has been applied, in a goldfish game or a contested game, the game shall clear the declared attack, and the outcome shall list each attacker's damage and the new damage totals.
- [x] **CMBT-027**: When the game enters `combat_damage` with no declared attack, in a goldfish game or a contested game, the game shall change no damage total and no life total.
- [x] **CMBT-061**: When an attacker deals combat damage in a contested game, the game shall subtract that damage from the life of the seat the attacker attacks and from no other seat's.
- [x] **CMBT-062**: When an attacking commander deals combat damage in a contested game, the game shall also add that damage to that commander's damage against the seat it attacks, kept per commander per seat.
- [ ] **CMBT-063**: When a contested game enters `combat_damage`, an attacker that was blocked, has trample damage stated for it with `attack` and `trample`, and is on the battlefield at that moment shall deal exactly that trample damage to the seat it attacks, whatever its power and its `damage` entry.
- [ ] **CMBT-077**: When a contested game enters `combat_damage`, an attacker that was blocked and is no longer on the battlefield shall deal no damage to the seat it attacks, whether or not it has trample damage stated for it or a `damage` entry.
- [ ] **CMBT-064**: When a contested game enters `combat_damage`, an attacker that was blocked and has no trample damage stated for it shall deal no damage to the seat it attacks, whether or not it has a `damage` entry.
- [ ] **CMBT-097**: When an attacking commander that was blocked deals trample damage in a contested game, the game shall add that damage to that commander's damage against the seat it attacks, as for any other combat damage it deals.
- [x] **CMBT-065**: When combat damage has been applied in a contested game, the game shall apply eliminations (a seat at 0 life or less, or dealt 21 or more by one commander) before the call's outcome is returned.
- [x] **CMBT-066**: When combat damage has been applied in a contested game, the outcome shall show each attacker's damage, the seat it was dealt to, and each damaged seat's new life total and commander damage.
- [x] **CMBT-067**: In a contested game, the game shall keep no pooled damage total and deal no combat damage to imaginary opponents.
- [x] **CMBT-068**: If `attack` in a contested game names an attacker that the attacking seat does not control, then `attack` shall return an error and change nothing.
- [x] **CMBT-069**: If the active seat of a contested game calls `attack` when an attack with at least one attacker has already been declared for the current combat, then `attack` shall return an error and change nothing, whatever its `attackers` list holds, unless the call gives `trample` and is accepted under CMBT-098.
- [x] **CMBT-070**: When `attack` with an empty `attackers` list is accepted in a contested game, the game shall open no response window, and a later `attack` in the same combat shall be accepted as that combat's first declaration.
- [x] **CMBT-071**: When an overridden `attack` returns a contested game to `declare_attackers` for an additional combat, the game shall accept it as the first declaration of a new combat.
- [x] **CMBT-072**: If the active seat of a contested game calls `attack` while the game is in `declare_blockers`, then `attack` shall return an error and change nothing, unless the call gives `trample` and is accepted under CMBT-098.

## Trample damage in a contested game

- [ ] **CMBT-098**: When the active seat of a contested game calls `attack` giving `trample` while it is the seat to act, no response window is open, the stack is empty, and the game is in `declare_blockers` with an attack of at least one attacker declared and every `blocks` pending choice of that combat answered, the game shall record each entry of `trample` as the trample damage of the attacker it names.
- [ ] **CMBT-099**: When an `attack` giving `trample` is accepted in a contested game and names an attacker that already has trample damage stated in the same combat, the game shall replace that attacker's trample damage with the new entry, and shall leave unchanged the trample damage of every attacker the call does not name.
- [ ] **CMBT-100**: When an `attack` giving `trample` is accepted in a contested game, the game shall tap nothing, open no response window, stay in `declare_blockers` and leave the active seat the seat to act.
- [ ] **CMBT-101**: When an `attack` giving `trample` is accepted in a contested game, the outcome shall list each attacker the call names with its trample damage and the seat number it attacks, as a public event shown alike to every seat.
- [ ] **CMBT-102**: In a contested game, the game shall not compare trample damage stated with `attack` and `trample` against the attacker's power, its blockers' toughness or any reading of trample, and shall raise no rule check on its account.
- [ ] **CMBT-103**: If `attack` in a goldfish game gives `trample`, then `attack` shall return an error and change nothing.
- [ ] **CMBT-104**: If `attack` in a contested game gives `trample` together with any of `attackers` (an empty list included), `targets`, `damage`, `vigilance`, `haste` or `evasion`, then `attack` shall return an error and change nothing.
- [ ] **CMBT-105**: If `attack` in a contested game gives `trample` while the game is not in `declare_blockers` with an attack of at least one attacker declared, then `attack` shall return an error and change nothing.
- [ ] **CMBT-106**: If `trample` in a contested game names something that is not among the attackers of the declared attack, then `attack` shall return an error and change nothing.
- [ ] **CMBT-107**: If `trample` in a contested game names an attacker that is not blocked, then `attack` shall return an error and change nothing.
- [ ] **CMBT-108**: If a `trample` entry in a contested game is not a whole number of zero or more, then `attack` shall return an error and change nothing.
