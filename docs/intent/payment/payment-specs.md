# Payment — Specs

Design: `payment-design.md`. Prefix: `PAY`.

## Mana strings and costs

- [x] **PAY-001**: In every game, a mana string shall be a sequence of brace-enclosed symbols drawn from `{W}`, `{U}`, `{B}`, `{R}`, `{G}`, `{C}`, `{S}`, `{X}`, a whole number, a two-color hybrid (`{W/U}`), a generic hybrid (`{2/W}`) and a Phyrexian symbol (`{W/P}`), and any other text shall be rejected as unparseable.
- [x] **PAY-002**: In every game, when paying a cost, a colored symbol shall be payable only by one mana of that color and `{C}` only by one colorless mana.
- [x] **PAY-003**: In every game, when paying a cost, a numeric symbol shall be payable by that much mana of any kind.
- [x] **PAY-004**: In every game, when paying a cost, a two-color hybrid symbol shall be payable by one mana of either color, and a generic hybrid symbol by two mana of any kind or one mana of its color.
- [x] **PAY-005**: In every game, when paying a cost containing `{S}`, the game shall pay that symbol with one mana of any kind and the outcome shall state that snow was paid as generic.

## Mana pool

- [ ] **PAY-044**: In every game, each seat shall have its own mana pool, holding the mana that seat has made and not yet spent.
- [x] **PAY-006**: In every game, when a payment is made, the game shall spend suitable mana already in the acting seat's mana pool before tapping any mana source; pool mana pays single-color and colorless symbols before hybrids, and when what is left cannot then be paid the pool and sources are searched together.
- [x] **PAY-007**: In every game, when a mana source makes more mana than a payment needs, the game shall add the surplus to the acting seat's mana pool and the outcome shall state it.
- [x] **PAY-008**: In every game, while mana in a seat's mana pool carries a spending restriction, the game shall spend it only on a card whose type line includes one of the restriction's card types, and never on the cost of an `effect`.
- [x] **PAY-042**: In every game, when a mana source adds mana to the acting seat's mana pool, that mana shall carry the source's spending restriction.
- [x] **PAY-009**: In every game, when a seat's mana pool is written as text, it shall be a mana string, `{}` when empty, with each restricted symbol followed by `*`.

## Mana sources

- [x] **PAY-010**: In every game, the game shall treat as a mana source of the acting seat any permanent on the battlefield controlled by the acting seat that has a mana ability reading, is a token whose spec gives `produces`, or is a card whose card definition gives `produces`.
- [ ] **PAY-045**: In a contested game, the game shall decide whose mana source a permanent is by its controller, not its owner: a permanent the acting seat controls but does not own is its mana source, and a permanent it owns but another seat controls is not.
- [x] **PAY-011**: In every game, when a mana source's amount is counted, the game shall evaluate the count from the game's state at the moment of payment.
- [ ] **PAY-050**: In a contested game, when a mana source's reading makes mana of any color among the commander's color identity, the game shall take those colors from the color identity of the commanders of the seat that controls the source, not of the seat that owns it.
- [ ] **PAY-051**: In a contested game, when a mana source's amount is counted, the game shall count the permanents, devotion, hand and graveyard of the seat that controls the source, not of the seat that owns it.
- [x] **PAY-012**: In every game, the auto payment system shall use a mana source only if it is untapped and its ability taps, does not sacrifice it, and has no cost other than tapping, life or mana.
- [x] **PAY-013**: In every game, the auto payment system shall not use a creature that entered the battlefield this turn as a mana source unless the creature has haste of its own or granted by another permanent's reading.
- [ ] **PAY-049**: In a contested game, when judging whether a creature that entered the battlefield this turn may be used as a mana source, the game shall count haste as granted to it only by the reading of a permanent controlled by the seat that controls the creature, never by a permanent another seat controls, whichever seat owns either.
- [x] **PAY-014**: In every game, the auto payment system shall use a mana source whose ability has a spending restriction only when the card being paid for has one of the restriction's card types, and never when the restriction lists no card types.
- [x] **PAY-015**: In every game, the auto payment system shall use a mana source whose ability costs life only when the acting seat's life after the whole payment — sources, Phyrexian symbols and `pay.life` together — would remain 1 or more.
- [x] **PAY-016**: In every game, when the auto payment system uses a mana source whose ability costs mana, the game shall pay that ability's mana cost from the acting seat's mana pool or its other mana sources within the same payment.
- [x] **PAY-017**: In every game, when a payment uses a mana source whose ability costs life, the game shall reduce the acting seat's life by that amount and the outcome shall state it.
- [ ] **PAY-046**: In a contested game, a payment shall spend mana only from the acting seat's mana pool, tap or sacrifice only permanents the acting seat controls, and take life only from the acting seat, never reaching another seat's mana pool, permanents or life.
- [ ] **PAY-047**: If a `pay.with` entry in a contested game names a permanent that another seat controls, then the call shall return an error.

## Auto payment system

- [x] **PAY-018**: In every game, when `play` or an `effect` with `pay` gives no `with`, `cost` or `life`, the auto payment system shall pay the computed cost from the acting seat's mana pool and available mana sources.
- [x] **PAY-019**: In every game, the auto payment system shall decide exactly whether a cost can be paid from the acting seat's mana pool and available mana sources.
- [x] **PAY-020**: In every game, if the auto payment system finds no valid payment, then the cost shall be reported as not payable, stating the cost, the amount of mana available and any color requirement that cannot be met.
- [x] **PAY-021**: In every game, when choosing among valid payments, the auto payment system shall pay each Phyrexian symbol with 2 life whenever the acting seat's life would remain 1 or more and a valid payment remains, and with mana otherwise.
- [x] **PAY-022**: In every game, when choosing among valid payments that are equal on Phyrexian symbols, the auto payment system shall choose the payment after which the greatest number of other cards could each be cast on their own from the acting seat's remaining untapped available mana sources and mana pool.
- [x] **PAY-023**: In every game, when counting other cards that could still be cast, the auto payment system shall count every non-land card in the acting seat's hand other than the card being played and every commander in the acting seat's command zone at its current commander tax, each at its mana cost with X as 0, and shall count a multi-face card if any face of it that has a mana cost could be cast, each Phyrexian symbol paid with mana.
- [x] **PAY-024**: In every game, when valid payments are equal on other cards still castable, the auto payment system shall choose the payment that leaves the greatest number of distinct colors (W, U, B, R, G) of mana available to the acting seat.
- [x] **PAY-025**: In every game, when valid payments are equal on colors still available, the auto payment system shall choose the payment that leaves the greatest total mana available to the acting seat.
- [x] **PAY-026**: In every game, when valid payments are equal on total mana still available, the auto payment system shall prefer tapping, in order: lands whose ability costs no life, lands whose ability costs life, permanents that are neither creatures nor lands, and creatures.
- [x] **PAY-027**: In every game, when valid payments are equal on every other rule, the auto payment system shall choose the payment whose mana sources' instance numbers, sorted, are lexicographically least.
- [x] **PAY-028**: In every game, the auto payment system shall produce the same payment for the same game state and cost on every run and every machine.
- [x] **PAY-029**: In every game, the auto payment system shall examine at most 20,000 valid payments in a fixed order when choosing among them, and shall use the best payment examined when that limit is reached.
- [x] **PAY-043**: In every game, the auto payment system shall prefer payments that tap no mana source the payment could do without, using another valid payment only when none such was examined.
- [x] **PAY-041**: In every game, when a permanent has more than one mana ability the auto payment system may use, the auto payment system shall consider paying with any one of them, and shall use at most one ability of a permanent in a payment.
- [ ] **PAY-048**: In every game, when mana sources named in `pay.with` offer a choice of mana and state none, the auto payment system shall try at most 64 layouts of their mana (a layout being one choice of mana ability and of mana for every named source at once), searching each layout within a 20,000-payment limit of its own, and shall use the best payment found over the layouts tried.
- [ ] **PAY-052**: In every game, the auto payment system shall try the layouts of named mana sources in a fixed order: the sources in the order `pay.with` lists them, each source's choices in the order of its mana abilities and of each ability's options as read, the last-listed source's choice changing first.
- [ ] **PAY-053**: In every game, if the named mana sources have more than 64 layouts and none of the first 64 pays the cost, then the cost shall be reported as not payable, even when a later layout would pay it.

## Agent-directed payment

- [x] **PAY-030**: In every game, when `pay.with` names mana sources, the game shall use those sources first, tapping each and sacrificing each whose ability sacrifices it, add their mana to the acting seat's mana pool, and have the auto payment system pay any remainder of the cost; pool mana and the named sources' mana shall be spent together, colorless and single-color mana going to generic symbols first.
- [x] **PAY-031**: In every game, when a `pay.with` entry states the mana a source makes, the game shall add exactly that mana for that source.
- [x] **PAY-032**: In every game, when a `pay.with` entry names a mana source that offers a choice and states no mana, the game shall pick the option by the auto payment system's rules.
- [x] **PAY-033**: In every game, if a `pay.with` entry names a permanent that has no mana reading and states no mana, then the call shall return an error asking for the mana it makes.
- [x] **PAY-034**: In every game, if a `pay.with` entry names a permanent that is already tapped, then the call shall return an error.
- [x] **PAY-035**: In every game, if a `pay.with` entry names a creature that entered the battlefield this turn and has no haste, then the call shall fail a rule check.
- [x] **PAY-036**: In every game, when `pay.cost` is given to `play`, the game shall pay that cost in place of the whole computed cost, including commander tax, X and extra costs, with any X in it replaced by `choices.x`.
- [x] **PAY-037**: In every game, if `pay.cost` is given to `play` and the call carries no `override`, then the call shall fail a rule check.
- [x] **PAY-040**: In every game, when `pay.cost` is given to `effect`, the game shall pay that cost, with X replaced by `choices.x` and `choices.extra_cost` added, without a rule check on account of it.
- [x] **PAY-038**: In every game, when `pay.life` is given, the game shall reduce the acting seat's life by that amount in addition to the rest of the payment.

## Reporting

- [x] **PAY-039**: In every game, when a payment is made, the outcome shall state the cost paid, the mana sources tapped, the mana sources sacrificed, life paid, mana taken from the acting seat's mana pool, and surplus left in it.
