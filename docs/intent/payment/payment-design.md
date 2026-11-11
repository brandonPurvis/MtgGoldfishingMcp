---
parent: high-level-design
prefix: PAY
---

# Payment

## Context and Design Philosophy

Paying for a spell is the most frequent piece of bookkeeping in a game and the easiest for an agent to get wrong. This component holds the mana pools and decides whether and how a cost is paid.

Every payment is made by the acting seat (see `play`), from its own mana pool, with the mana sources it controls, and with its own life. Nothing in this design reaches another seat: whatever this design calls "the agent" is the acting seat, and "the hand", "the command zone" and "the sources" are that seat's.

When the agent does not say how to pay, the **auto payment system** chooses. Its aim is not merely a valid payment but the valid payment that **leaves the agent the most options afterwards**. With three Plains and two Forests, a card costing {1}{W}{W}, and a {G}{W} card still in hand, it taps two Plains and a Forest, not three Plains, so the second card can still be cast.

The auto payment system chooses how to pay. It never chooses what to play.

## Mana Strings and Costs

A mana string is a sequence of symbols in braces.

| Symbol | Meaning in a cost | Meaning as mana produced |
|---|---|---|
| `{W}` `{U}` `{B}` `{R}` `{G}` | one mana of that color | one mana of that color |
| `{C}` | one colorless mana specifically | one colorless mana |
| `{3}` | that much mana of any kind | that much colorless mana |
| `{X}` | replaced by the announced X before paying | — |
| `{W/U}` | either color | — |
| `{2/W}` | two mana of any kind, or one white | — |
| `{W/P}` | one white mana, or 2 life | — |
| `{S}` | one mana of any kind | — |

`{S}` (snow) is paid as generic mana and the response says so, since the service does not track which sources are snow.

## The Mana Pool

Each seat has its own pool, holding mana that has been made and not yet spent. Mana enters it from a delta's `mana` key and from sources that make more than a payment needed. Every seat's pool empties when the game leaves a step (see `turn`).

```
ManaPool = [ { symbol: W|U|B|R|G|C, restriction: Restriction | null } ]
```

Mana in the pool may carry a spending restriction, inherited from the source that made it. Restricted mana is only spent on a card whose type line includes one of the restriction's card types; it is never spent on the cost of an `effect`, which has no card type. In text the pool is written as a mana string, `{}` when empty, with each restricted symbol followed by `*` (`{G}{G}*`).

Any payment spends suitable mana already in the pool before tapping anything, and spends it so that a cost the pool and sources could pay together stays payable: pool mana goes to the narrowest requirements first (a single color or colorless before a hybrid), and when what is left still cannot be paid, the pool and the sources are considered together.

## Mana Sources

A **mana source** is a permanent on the battlefield, controlled by the acting seat, with at least one mana ability reading (see `card-reading`), or a token whose `TokenSpec` gives `produces`, or a card whose definition gives `produces`. A source is read from its owner's deck, whichever seat controls it (see `game`): its mana abilities, its type line, and the haste that lets a creature that entered this turn be used, so a permanent taken from another seat makes the mana it made for its owner. A source's counted amounts are evaluated from game state at the moment of payment, each counted permanent likewise read from its own owner's deck. Whatever a reading says of "you" means the seat that controls the source: its permanents, devotion, hand and graveyard are the ones counted, and "your commander's color identity" is that of its commanders, even when the source came from another seat's deck. A permanent with several mana abilities may be used through any one of them in a payment, never through more than one, since each taps it.

A source is **available** to the auto payment system when all of these hold:

- it is untapped;
- its ability taps, does not sacrifice it, and has no cost other than tapping, life or mana;
- if its ability costs life, the agent's life after the whole payment — sources, Phyrexian symbols and `pay.life` together — would stay at 1 or more;
- if it is a creature, it did not enter the battlefield this turn, or it has haste (its own, or granted by the reading of another permanent the same seat controls: a grant reads `creatures you control`, so one seat's permanent never gives haste to another seat's creature);
- if its ability has a restriction, the card being paid for qualifies, and the restriction's card types are known;
- its ability has a reading, with or without assumptions.

Sources that sacrifice themselves — Treasure tokens, Lotus Petal — and sources whose ability carries another cost — removing a counter, tapping another creature — are never used by the auto payment system, because using them gives something up and whether to do so is the agent's decision. The agent names them in `pay`. The service does not pay the other cost; the agent records it in the delta.

A source whose ability itself costs mana (a signet's `{1}, {T}: Add {W}{U}`) is available; using it requires that its own cost be paid from the pool or other sources as part of the same payment.

## The Auto Payment System

Given a cost and the game state, it considers every way of paying the cost from the pool and available sources, and picks one by these rules in order. Each rule only breaks ties left by the one before. Payments that tap no source they could do without are preferred, and another valid payment is used only when none such was examined: surplus mana left in the pool counts as mana still available, so a payment that taps an extra source would otherwise tie with one that does not.

1. **Life for Phyrexian symbols.** Each Phyrexian symbol is paid with 2 life whenever the agent's life would stay at 1 or more and a valid payment remains; otherwise with mana. When paying every Phyrexian symbol with life leaves no valid payment, fewer are paid with life, as many as still allow one.
2. **Most other cards still castable.** Count the cards that could each be cast, one at a time, from what would remain: every non-land card in hand other than the one being played, and each commander in the command zone at its current tax, each taken at its plain mana cost with X as 0 and its Phyrexian symbols paid with mana. A multi-face card counts if any of its faces that has a mana cost could be cast. The payment leaving the highest count wins.
3. **Most colors still available.** Count the distinct colors (W, U, B, R, G) of mana the remaining sources and pool could make.
4. **Most mana still available.** Total mana the remaining sources and pool could make. This also means a two-mana source is not spent on a one-mana cost when a one-mana source would do.
5. **Cheapest kind of source.** Prefer tapping, in order: lands that cost nothing to use; lands that cost life to use; non-creature, non-land permanents; creatures. A land's kind is judged by the ability used, so a land tapped through a free ability counts as free. Creatures come last so they stay free to attack.
6. **Lowest instance ids**: the payment whose sources' instance numbers, sorted, are lexicographically least, so the choice is deterministic.

"What would remain" is the untapped available sources after the payment plus mana left in the pool. Only cards currently in hand and the command zone are considered; the service does not guess at cards not yet drawn.

When a source makes more mana than needed, the surplus goes to the pool and the response says so.

If no valid payment exists, the cost is **not payable**: a rule check (see `play`). The refusal states the cost, how much mana is available, and which color requirement cannot be met.

Whether a cost is payable at all is always decided exactly. Choosing *among* valid payments is exhaustive in principle: identical sources are treated as interchangeable to keep the search small, payments are examined in a fixed order, and at most 20,000 are examined; past that, the best found so far is used. The limit is a count, never a time, so the same game state always produces the same payment on any machine. When named sources offer a choice (see below), the search runs once for each **layout** of their mana: one choice of ability and of mana for every named source at once. A source whose one mana may be any of several colors offers no choice of layout, since that one mana can pay any of its colors; layouts come from a choice between a source's abilities and from mana that must all be one color, such as three mana of any one color. Layouts are taken in a fixed order — the sources as `pay.with` lists them, each source's choices as its abilities and their options were read, the last-listed source's choice changing first — and at most 64 are tried, each within a 20,000-payment limit of its own; the best payment found over them is used. Three named sources that each make three mana of any one color already have 125 layouts, so when none of the first 64 pays, the cost is reported not payable though a later layout might pay it, and the agent states the mana of some of the sources.

## Agent-Directed Payment

```
pay: { with?: [name | { source: name, mana: ManaString }], cost?: ManaString, life?: int }
```

- **`with`** names sources to use. They are used first — tapped, and sacrificed if their ability says so — and their mana is added to the pool; the auto payment system then pays any remainder, spending the pool and the named sources' mana together, colorless and single-color mana going to generic symbols first. Naming a sacrifice source here is how a Treasure pays for a spell. An entry may state the mana the source makes this time (`{ "source": "Mana Vault", "mana": "{C}{C}{C}" }`); the stated mana is used as given, through the source's mana ability that can make it when there is one, which is how the agent picks a color from a multi-color source and how it uses a permanent the service has not read as a mana source. For a named source that offers a choice and has no stated mana, the service picks the option, and with several mana abilities the ability, that best serves the cost by the rules above. A named permanent that has no mana reading and no stated mana is an error asking for the mana; a named permanent that is already tapped is an error. A named creature that is summoning-sick is a rule check.
- **`cost`** on `play` replaces the whole cost the service computed, including commander tax, X and extra costs; any X in it is replaced by `choices.x`. It exists for cost reducers and alternative costs. Because the service cannot verify it, giving `cost` to `play` is a rule check: the call must carry an `override` reason. On `effect`, which has no computed cost, `cost` is simply the cost of the ability being recorded and is not a rule check.
- **`life`** pays that much life in addition to the rest of the payment, for costs the service cannot read from the mana cost.

`pay` omitted entirely means, for `play`: pay the computed cost automatically; for `effect`: pay nothing.

## What the Response Shows

Every payment reports the cost paid, the sources tapped or sacrificed, life paid, mana taken from the pool, and surplus left in it.

```
OK Cast Cultivate. Paid {2}{G}: tapped Forest, Forest, Island.
```

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Objective of automatic payment | Preserve the most later plays, by an ordered list of tie-breakers | Any valid payment; keep the most colors only | A valid but careless payment strands cards in hand, and the agent then either plays worse than the deck allows or spends calls directing every payment. |
| What "later plays" counts | Cards in hand and commanders in the command zone, one at a time | Sets of cards castable together; cards that might be drawn | One-at-a-time is computable, explainable, and matches the question a player asks ("can I still cast this?"). |
| Phyrexian symbols | Life whenever life stays positive and a valid payment remains | Mana by default; life whenever life stays positive, even when that leaves the cost unpayable | Life is rarely the constraint in a goldfish game; mana is. Paying life keeps the most options, but never at the price of a payable cost. |
| Spending the pool | Narrowest requirements first; the pool and sources together when what is left cannot be paid | In cost order | Spending in cost order can give the pool's only white mana to a hybrid and leave a white symbol no source can pay. |
| Whose pool and sources | The acting seat's alone, whoever owns the sources | A shared pool; sources by owner | Mana belongs to the player who made it, and a permanent's abilities are its controller's to use. |
| Permanents with several mana abilities | Any one ability per payment | The first usable ability only | A painland's colored ability would never be used, and a payable cost would be refused. |
| Life-costing lands | A tie-breaker below free lands, above artifacts and creatures | Avoided unless necessary; used freely | They may be tapped when that keeps more cards castable, but are not preferred over an equivalent free land. |
| Sacrifice sources and sources with another cost | Never automatic | Automatic when nothing else can pay | Giving something up is a decision, not bookkeeping. |
| A named permanent the service has not read as a mana source | Accepted when the agent states its mana | Error | A mana reading is an approximation; tenet *It's the agent's simulation*. |
| Summoning-sick creatures | Not used automatically; a rule check when named | Error when named | The service may not know the creature was given haste; the agent can override. |
| Named sources plus remainder | Named sources first, auto payment for the rest | Named sources must cover the whole cost | The agent can say "use the Treasure" without also listing five lands. |
| Explicit cost | Allowed with a required override reason | Trusted silently; not allowed | The service cannot verify a reduced or alternative cost; the override keeps a record of why. |
| More than 64 layouts of named sources | The first 64 in a fixed order; not payable when none of them pays | Every layout; a payment limit shared across layouts | Layouts multiply with each named source, and the agent who named the sources can state their mana in the same call. A fixed count keeps the payment the same on every machine. |
| Search bound | A fixed count of payments examined, best found so far | Unbounded exhaustive; a time limit | A response must come back promptly even on a very wide board; a time limit would make the payment depend on the machine and break reproducibility. |

## Open Questions & Future Decisions

### Deferred
1. Convoke, delve, improvise and other costs paid with things other than mana: the agent gives an explicit `cost` and records the rest in the delta.
2. Mana that persists between steps or turns.
3. Costs for the "most other cards still castable" rule beyond plain mana cost (alternative costs, known cost reducers).

## References

- `docs/high-level-design.md` (goal 4; tenet *Best guess, shown*)
- `docs/intent/card-reading/card-reading-design.md` (mana ability readings)
- `docs/intent/play/play-design.md` (where costs come from; rule checks)
