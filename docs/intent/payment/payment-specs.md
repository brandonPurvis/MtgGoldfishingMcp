# Payment — Specs

Design: `payment-design.md`. Prefix: `PAY`.

## Mana strings and costs

- [ ] **PAY-001**: A mana string shall be a sequence of brace-enclosed symbols drawn from `{W}`, `{U}`, `{B}`, `{R}`, `{G}`, `{C}`, `{S}`, `{X}`, a whole number, a two-color hybrid (`{W/U}`), a generic hybrid (`{2/W}`) and a Phyrexian symbol (`{W/P}`), and any other text shall be rejected as unparseable.
- [ ] **PAY-002**: When paying a cost, a colored symbol shall be payable only by one mana of that color and `{C}` only by one colorless mana.
- [ ] **PAY-003**: When paying a cost, a numeric symbol shall be payable by that much mana of any kind.
- [ ] **PAY-004**: When paying a cost, a two-color hybrid symbol shall be payable by one mana of either color, and a generic hybrid symbol by two mana of any kind or one mana of its color.
- [ ] **PAY-005**: When paying a cost containing `{S}`, the game shall pay that symbol with one mana of any kind and the outcome shall state that snow was paid as generic.

## Mana pool

- [ ] **PAY-006**: When a payment is made, the game shall spend suitable mana already in the mana pool before tapping any mana source.
- [ ] **PAY-007**: When a mana source makes more mana than a payment needs, the game shall add the surplus to the mana pool and the outcome shall state it.
- [ ] **PAY-008**: While mana in the mana pool carries a spending restriction, the game shall spend it only on a card whose type line includes one of the restriction's card types, and never on the cost of an `effect`.
- [ ] **PAY-009**: When the mana pool is written as text, it shall be a mana string, `{}` when empty, with each restricted symbol followed by `*`.

## Mana sources

- [ ] **PAY-010**: The game shall treat as a mana source any permanent on the battlefield that has a mana ability reading, a token whose spec gives `produces`, or a card whose card definition gives `produces`.
- [ ] **PAY-011**: When a mana source's amount is counted, the game shall evaluate the count from the game's state at the moment of payment.
- [ ] **PAY-012**: The auto payment system shall use a mana source only if it is untapped, its ability taps, does not sacrifice it and has no other cost.
- [ ] **PAY-013**: The auto payment system shall not use a creature that entered the battlefield this turn as a mana source unless the creature has haste of its own or granted by another permanent's reading.
- [ ] **PAY-014**: The auto payment system shall use a mana source whose ability has a spending restriction only when the card being paid for has one of the restriction's card types, and never when the restriction lists no card types.
- [ ] **PAY-015**: The auto payment system shall use a mana source whose ability costs life only when the agent's life would remain 1 or more.
- [ ] **PAY-016**: When the auto payment system uses a mana source whose ability costs mana, the game shall pay that ability's mana cost from the mana pool or other mana sources within the same payment.
- [ ] **PAY-017**: When a payment uses a mana source whose ability costs life, the game shall reduce the agent's life by that amount and the outcome shall state it.

## Auto payment system

- [ ] **PAY-018**: When `play` or an `effect` with `pay` gives no `with`, `cost` or `life`, the auto payment system shall pay the computed cost from the mana pool and available mana sources.
- [ ] **PAY-019**: The auto payment system shall decide exactly whether a cost can be paid from the mana pool and available mana sources.
- [ ] **PAY-020**: If the auto payment system finds no valid payment, then the cost shall be reported as not payable, stating the cost, the amount of mana available and any color requirement that cannot be met.
- [ ] **PAY-021**: When choosing among valid payments, the auto payment system shall pay each Phyrexian symbol with 2 life whenever the agent's life would remain 1 or more, and with mana otherwise.
- [ ] **PAY-022**: When choosing among valid payments that are equal on Phyrexian symbols, the auto payment system shall choose the payment after which the greatest number of other cards could each be cast on their own from the remaining untapped available mana sources and mana pool.
- [ ] **PAY-023**: When counting other cards that could still be cast, the auto payment system shall count every non-land card in hand other than the card being played and every commander in the command zone at its current commander tax, each at its mana cost with X as 0, and shall count a multi-face card if any face of it that has a mana cost could be cast.
- [ ] **PAY-024**: When valid payments are equal on other cards still castable, the auto payment system shall choose the payment that leaves the greatest number of distinct colors of mana available.
- [ ] **PAY-025**: When valid payments are equal on colors still available, the auto payment system shall choose the payment that leaves the greatest total mana available.
- [ ] **PAY-026**: When valid payments are equal on total mana still available, the auto payment system shall prefer tapping, in order: lands whose ability costs no life, lands whose ability costs life, permanents that are neither creatures nor lands, and creatures.
- [ ] **PAY-027**: When valid payments are equal on every other rule, the auto payment system shall choose the payment using the mana sources with the lowest instance ids.
- [ ] **PAY-028**: The auto payment system shall produce the same payment for the same game state and cost on every run and every machine.
- [ ] **PAY-029**: The auto payment system shall examine at most 20,000 valid payments in a fixed order when choosing among them, and shall use the best payment examined when that limit is reached.

## Agent-directed payment

- [ ] **PAY-030**: When `pay.with` names mana sources, the game shall use those sources first, tapping each and sacrificing each whose ability sacrifices it, add their mana to the mana pool, and have the auto payment system pay any remainder of the cost.
- [ ] **PAY-031**: When a `pay.with` entry states the mana a source makes, the game shall add exactly that mana for that source.
- [ ] **PAY-032**: When a `pay.with` entry names a mana source that offers a choice and states no mana, the game shall pick the option by the auto payment system's rules.
- [ ] **PAY-033**: If a `pay.with` entry names a permanent that has no mana reading and states no mana, then the call shall return an error asking for the mana it makes.
- [ ] **PAY-034**: If a `pay.with` entry names a permanent that is already tapped, then the call shall return an error.
- [ ] **PAY-035**: If a `pay.with` entry names a creature that entered the battlefield this turn and has no haste, then the call shall fail a rule check.
- [ ] **PAY-036**: When `pay.cost` is given, the game shall pay that cost in place of the whole computed cost, including commander tax, X and extra costs.
- [ ] **PAY-037**: If `pay.cost` is given and the call carries no `override`, then the call shall fail a rule check.
- [ ] **PAY-038**: When `pay.life` is given, the game shall reduce the agent's life by that amount as part of the payment.

## Reporting

- [ ] **PAY-039**: When a payment is made, the outcome shall state the cost paid, the mana sources tapped, the mana sources sacrificed, life paid, mana taken from the mana pool, and surplus left in the mana pool.
