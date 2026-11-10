---
parent: high-level-design
prefix: READ
---

# Card Reading

## Context and Design Philosophy

The service does not know what cards do. This component holds the deliberate exceptions: four narrow readings of a card's rules text and keywords that make automatic payment, trigger reminders and attack bookkeeping possible.

1. **Mana sources**: how much mana of which colors a permanent makes, and what using it costs.
2. **Step triggers**: which steps of the turn a permanent has a beginning-of-step trigger in, and on whose turns.
3. **Haste and vigilance**: whether a permanent has either keyword itself or grants it to others.
4. **Entering tapped**: whether a permanent enters the battlefield tapped.

Every mana ability reading, keyword reading and enters-tapped reading carries a list of `assumptions`, empty when the text matched a known form exactly. Step triggers carry none.

Reading follows the tenet *Best guess, shown*. When text matches a known form only partly, the reader returns its best reading together with a plain statement of what it assumed. It returns "no reading" only when it has nothing usable. It never guesses silently.

Reading is pure: text in, reading out, no game state. Readings that depend on game state (counted amounts) are returned as a rule to be evaluated later by whoever holds the state.

## Mana Sources

A card face is read for mana abilities: abilities of the form `<cost>: Add <mana>`. A face may have several; each is read separately.

```
ManaAbility {
  produces: Fixed | Choice | AnyColor | Counted
  taps: bool                 // cost includes {T}
  mana_cost: ManaString      // mana that must be paid to use it, "" if none
  life: int                  // life lost by using it: a life payment or damage to its controller
  sacrifices: bool           // cost sacrifices the permanent itself
  other_cost: string | null  // any further cost, as written: "Remove a charge counter", "Tap an untapped creature you control"
  restriction: Restriction | null
  assumptions: [string]      // what the reader assumed, empty when the text matched a form exactly
}

Fixed    { mana: ManaString }                 // "{G}", "{C}{C}", "{W}{U}"
Choice   { options: [ManaString] }            // "{W} or {U}" -> ["{W}", "{U}"]
AnyColor { amount: int, among: "any" | "commander_identity" | [color] }
Counted  { per: Count, mana: ManaString | AnyColor }   // that much mana for each counted thing

Count =
    { kind: "permanents", match: string }     // "creature", "Elf", "land", "artifact" you control
  | { kind: "devotion", colors: [color] }
  | { kind: "cards_in_hand" }
  | { kind: "cards_in_graveyard", match: string | null }
  | { kind: "counters_on_self", counter: string }

Restriction { text: string, card_types: [string] }   // card types the mana may be spent on
```

### Forms read exactly

| Text form | Reading |
|---|---|
| `{T}: Add {G}.` | Fixed |
| `{T}: Add {C}{C}.` | Fixed, two mana |
| `{T}: Add {W} or {U}.` / `{T}: Add {R}, {G}, or {W}.` | Choice |
| `{T}: Add one mana of any color.` / `two mana of any one color` | AnyColor among any |
| `{T}: Add one mana of any color in your commander's color identity.` | AnyColor among commander_identity |
| `{1}, {T}: Add {W}{U}.` | Fixed with mana_cost `{1}` |
| `{T}, Pay 1 life: Add ...` / `{T}: Add {W}. This land deals 1 damage to you.` | the mana, with life 1 |
| `{T}, Sacrifice this artifact: Add one mana of any color.` | AnyColor with sacrifices true |
| `{T}: Add {G} for each creature you control.` | Counted permanents "creature" |
| `{T}: Add {G} for each Elf you control.` | Counted permanents "Elf" |
| `{T}: Add X mana ..., where X is your devotion to green.` | Counted devotion |
| `{T}: Add {C} for each card in your hand.` | Counted cards_in_hand |
| `... Spend this mana only to cast creature spells.` | the mana, with a Restriction of card_types ["Creature"] |
| `{T}, Remove a charge counter from this artifact: Add ...` | the mana, with other_cost "Remove a charge counter from this artifact" |

Any part of an ability's cost that is not `{T}`, mana symbols, a life payment, or sacrificing the permanent itself is carried verbatim in `other_cost`. Life lost through a separate triggered ability on the same card (`Whenever this land becomes tapped, it deals 1 damage to you`) is not part of the ability and is not included in `life`.

`Count.match` is a single word compared, ignoring case, against the words of a permanent's type line (for a token, its `types`).

A basic land type on the type line (`Forest`, `Island`, `Plains`, `Swamp`, `Mountain`) is read as the corresponding `{T}: Add` ability even when the rules text is empty.

### Best guesses

When an ability's text continues past a form the reader knows, or is conditioned, the reader keeps the part it understood and records an assumption:

- A condition on activation (`Activate only if you control an Island`) → read as always usable; assumption "ignores activation condition".
- A conditional upgrade (`Add {G}. If you control a creature with power 5 or greater, add {G}{G} instead`) → the unconditional amount; assumption "ignores conditional bonus".
- A restriction the reader cannot map to card types (`Spend this mana only to cast spells with flashback`) → Restriction with empty `card_types`; assumption "restriction not understood". An empty `card_types` means the auto payment system does not use the source.
- An ability that adds mana whose amount or colors cannot be read, on a card whose `produced_colors` are known → one mana of those colors, a choice among them when there are several; assumption "amount assumed to be one".
- A choice of colors the reader cannot bound (`one mana of any color that a land you control could produce`, `any type a land an opponent controls could produce`) → AnyColor among any; assumption "assumes any color".
- `in any combination of colors` → AnyColor of the stated amount; assumption "assumes one color for the whole amount".

### No reading

An ability gets no reading when it adds mana but neither taps nor sacrifices the permanent (mana filters such as `{1}: Add {R}`), when it is a triggered ability rather than an activated one (`Whenever you tap a land for mana, add ...`), or when no mana symbols or counts can be extracted from it and the card has no `produced_colors`. An ability without a reading is reported as **unread** only on a card whose `produced_colors` are known; on a card without them it is left out of the report, since nothing says the card makes mana at all.

### Reporting

A card with several mana abilities is reported per ability: it can appear both as read and, for another ability, as unread.

For a set of cards the reader produces lists a caller can show: mana abilities read exactly, mana abilities read with assumptions (each with its assumptions), unread mana abilities, cards with step triggers, cards that have or grant haste or vigilance, and cards that enter tapped or are assumed to enter untapped.

## Step Triggers

A face is scanned for beginning-of-step phrases. Each match yields a step trigger reading: the step it belongs to, and **whose** turns it happens on.

```
StepTrigger { step: Step, whose: "controller" | "each" | "opponents" }
```

| Phrase contains | Step | Whose |
|---|---|---|
| `At the beginning of your upkeep` | upkeep | controller |
| `of each upkeep`, `of each player's upkeep` | upkeep | each |
| `of each opponent's upkeep` | upkeep | opponents |
| `At the beginning of your draw step` | draw | controller |
| `of each player's draw step` | draw | each |
| `of each opponent's draw step` | draw | opponents |
| `At the beginning of your precombat main phase`, `of your first main phase` | main1 | controller |
| `At the beginning of combat on your turn` | begin_combat | controller |
| `of each combat` | begin_combat | each |
| `At the beginning of your postcombat main phase`, `of your second main phase` | main2 | controller |
| `At the beginning of your end step` | end | controller |
| `of each end step`, `of each player's end step`, `of the end step` | end | each |
| `of each opponent's end step` | end | opponents |

The table is the whole list. A phrase that names opponents or other players in any other wording (`At the beginning of combat on each opponent's turn`, `of each other player's upkeep`) yields no reading; its controller records the trigger unprompted, as it records an event trigger.

Which readings produce a reminder on a given turn is decided by `turn`: a goldfish game has only the controller's turns, so an `opponents` reading never produces one there. Delayed triggers created by other effects ("at the beginning of the next end step" inside a spell's text) are matched the same way as static ones: `the next` step reads as `each`, like `the end step`, since the text does not say whose turn it will be, and `your next` step reads as `controller`. The reminder is harmless when it does not apply. A face with several triggers in the same step and of the same `whose` yields that pair once.

## Haste and Vigilance

For each of the two keywords a face gets one of:

- **own**: the keyword stands as an ability of the card itself: on a line of its own or in a comma-separated keyword line.
- **grants**: a static ability gives the keyword to creatures the controller has, in one of the forms `Creatures you control have <keyword>`, `Other creatures you control have <keyword>`, `<Subtype> creatures you control have <keyword>`, `<plural subtype> you control have <keyword>`, including when the keyword is one item in a longer list (`get +1/+1 and have vigilance`). A grant records whether it includes the card itself and which subtype, if any, it is limited to. A plural subtype (`Goblins you control have haste`, `Allies you control have vigilance`) is recorded in its singular form (`Goblin`, `Ally`). Only standing grants are read: text that gives the keyword for a limited time (`gain haste until end of turn`, `gains haste this turn`), whether on a spell or inside an activated or triggered ability, is not a grant.
- **none**.

A keyword the card has only under a condition (`has haste as long as you control a Mountain`) is read as **own**, with the assumption "assumes its condition is met". The condition may itself speak of the turn (`As long as you've cast a noncreature spell this turn, this creature has vigilance`); that is still a standing ability under a condition, not a keyword given for a limited time. A grant under a condition is read as a grant with the same assumption.

Keywords conferred through attachment (`Equipped creature has haste`, `Enchanted creature has vigilance`) are not read, because the service does not track what is attached to what.

Flash is read the same way as an own keyword, for the timing check in `play`.

## Entering Tapped

A face gets one of:

- **tapped**: the text says without condition that the permanent enters tapped (`This land enters tapped.`, `<Name> enters the battlefield tapped.`). A rider saying it does not untap (`This land enters tapped and doesn't untap during your untap step.`) is not a condition on entering tapped.
- **untapped, assumed**: the text says it enters tapped subject to a condition or a choice (`enters tapped unless you control two or more other lands`, `you may pay 2 life. If you don't, it enters tapped`). It is read as entering untapped, with the assumption "assumes it enters untapped: <the condition as written>".
- **untapped**: the text says nothing about entering tapped.

The reading applies to any permanent, not only lands.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| How mana amounts are known | Read from rules text by pattern | Scryfall `produced_mana` alone; agent declares every source | Scryfall gives colors without amounts. Agent declaration puts back the bookkeeping the service exists to remove. |
| Partial matches | Best reading plus stated assumptions | Refuse anything not matched exactly | Tenet *Best guess, shown*: a shown assumption can be corrected by the agent with a card definition; a refusal makes the agent do the work by hand every time. |
| Sources that sacrifice themselves or carry another cost | Read, flagged `sacrifices` or `other_cost` | Not read | The reading is reliable; whether to use it automatically is a payment decision, not a reading decision. |
| Conditional enters-tapped text | Read as entering untapped, with the condition shown | Read as entering tapped | A player usually arranges to meet the condition; the shown assumption lets the agent tap the land itself when it does not. |
| Counted amounts | Returned as a rule, evaluated by the holder of game state | Reader takes game state | Keeps reading pure and testable from text alone. |
| Own versus granted keyword | Decided from text position, not Scryfall's keyword list | Trust the keyword list | The list includes keywords a card grants to others, so it cannot tell a hasty creature from one that gives haste. |
| Attachment-conferred keywords | Not read | Track attachments | Attachment tracking is rules-engine territory; the agent states haste or vigilance in the `attack` call instead. |
| Whose turns a step trigger happens on | Read as controller, each, or opponents | Read the step only; ignore opponents-only phrases | In a contested game other seats' turns exist, and a trigger on each opponent's upkeep is the controller's to record during another seat's turn. |

## Open Questions & Future Decisions

### Deferred
1. Mana filters and mana-doubling triggers get no reading; the agent adds their mana with an `effect` call.
2. Step triggers in zones other than the battlefield (a card that triggers from the graveyard at upkeep) are readable, but which zones are scanned is decided by `turn`.
3. Additional `Count` kinds are added as cards that need them are encountered.
4. Opponent-only step phrases beyond upkeep, draw step and end step, and wordings such as `each other player's`.

## References

- `docs/high-level-design.md` (tenet *Best guess, shown*)
- `docs/intent/card-data/card-data-design.md` (card model)
- `docs/intent/payment/payment-design.md` (how readings are used)
