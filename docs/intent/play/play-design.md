---
parent: high-level-design
prefix: PLAY
---

# Play

## Context and Design Philosophy

This is where the agent tells the service what happened. `play` plays a card; `effect` records any other change; `choose` finishes an effect that revealed hidden cards. In each the agent states the **outcome** — where things end up — and the service supplies the bookkeeping the outcome implies.

The service does not know whether the outcome is what the card would really do. It checks what card data lets it check, refuses what is structurally impossible, and trusts the rest.

## Errors and Rule Checks

Every refusal is one of two kinds.

**Errors** are structural impossibilities. They can never be overridden, and nothing is applied.

- unknown game, or a tool the game's status does not accept (see `game`);
- a card name that resolves to nothing in the zone the operation needs;
- a card chosen in `choose` that was not revealed;
- a malformed argument: an unknown delta key, an unknown `expect` key, an unparseable mana string, a destination that does not exist, a delta holding both `look` and `search`;
- a card played from outside the game whose card data cannot be obtained and for which no definition was given.

**Rule checks** are approximations from card data. A failed check refuses the call with an explanation, and nothing is applied. The agent may resubmit the same call with `override: "<reason>"`; the call is then applied and the override recorded.

- the cost is not payable;
- the land drop for the turn is used;
- a card that is not an instant and does not have flash is cast outside a main step;
- a land is played outside a main step;
- `pay` on `play` gives an explicit cost (see `payment`);
- a summoning-sick creature is named as a mana source in `pay`.

When a call fails several rule checks, the refusal lists all of them, and one `override` covers them all. Errors are reported before rule checks; a call with an error is never applied, override or not.

A call is applied completely or not at all.

Asking for a change that is already so is neither: tapping a tapped permanent, untapping an untapped one, or lowering a counter below zero is applied as far as it can be (the counter stops at zero) and the response notes it.

When "cost not payable" is overridden, nothing is tapped and nothing is spent: the card is played unpaid and the response says so. The agent taps what it means to with the delta's `tap` key in the same call.

## `play`

```
play(game_id, card, from?, to?, delta?, choices?, pay?, expect?, reason?, override?)
```

Plays `card` — a land, a spell, or the commander.

**Where it comes from.** `from` names the zone: `hand`, `command`, `graveyard`, `exile`, `library`, or `outside`. When omitted, the card is looked for in hand and then in the command zone. `library` finds the card by name anywhere in the library without revealing or disturbing anything else. `outside` brings in a card that is not part of the game: a new instance is created from card data resolved by name before the call is applied (see `card-data`), or from a `definition` given inside `choices` (same shape as a deck's card definition). Readings are made for it as for any card. If the name is not found, or card data is unavailable, and no definition was given, the call is an error that asks for one.

**Which face.** If `card` names one face of a multi-face card, that face is the one played and its cost, type line and power are the ones used. A face with no mana cost of its own costs nothing, and the response notes that.

**Lands.** If the played face is a land, there is no cost and a land drop is used. This is true from any zone.

**Entering tapped.** A permanent that is played enters tapped when its enters-tapped reading says so (see `card-reading`), and untapped otherwise. When the reading rests on an assumption, the response states it. The same applies to permanents arriving by `fetch` or `move` to `battlefield`; the `battlefield_tapped` destination always taps.

**Spells.** Otherwise the cost is the face's mana cost with each `{X}` replaced by `choices.x`, plus `choices.extra_cost`, plus commander tax when the card is cast from the command zone ({2} for each previous cast of that commander from the command zone). The cost is paid as `payment` describes. Casting from the command zone increases that commander's cast count.

**Where it ends up.** `to` names the destination. When omitted: a permanent goes to the battlefield, with its `entered_turn` set; an instant or sorcery goes to the graveyard.

**Then the delta is applied** (below).

## `effect`

```
effect(game_id, source, delta, choices?, pay?, expect?, reason?, override?)
```

Records any change not caused by playing a card: an activated ability, a trigger, sacrificing a Treasure, an imagined opponent's removal spell. `source` says what is responsible. It is free text; when it names a permanent the agent controls, the call counts as answering that permanent's reminder for the current step (see `records`). `pay`, when given, pays a cost exactly as for `play`; when omitted nothing is paid. The cost is paid before the delta is applied, so mana added by the same call's delta cannot pay it.

## Delta

Every key is optional.

```
Delta {
  untap:    [name]
  tap:      [name]
  mana:     ManaString                    // added to the pool
  tokens:   [TokenSpec]
  counters: { [name]: { [kind]: int } }   // signed changes; a kind reaching 0 is removed
  move:     { [destination]: [name] }     // cards in hand or a public zone
  commander_stays: bool                   // let a commander go to the graveyard or exile
  discard:  [name]                        // hand → graveyard
  fetch:    { [destination]: [name] }     // library → destination, by name
  draw:     int
  life:     int                           // signed change to the agent's life
  damage:   int                           // noncombat damage to opponents, pooled
  shuffle:  bool
  look:     { n, from: "top" | "bottom", rest: Destination }
  search:   { filter?: string }
}

Destination = "hand" | "battlefield" | "battlefield_tapped" | "graveyard"
            | "exile" | "command" | "library_top" | "library_bottom"

TokenSpec {
  name: string
  count: int                 // default 1
  types: string              // "Artifact — Treasure", "Creature — Elf Warrior"
  pt: string | null          // "1/1"
  produces: ManaString | [ManaString] | null   // what it taps for
  sacrifice_to_produce: bool // true for Treasure-like tokens
  tapped: bool
}
```

Keys are applied in the order listed above, whatever order the agent wrote them in. A card that needs a different order (draw, then put a card back, then shuffle) is recorded as a `play` followed by one or more `effect` calls.

Details that are not obvious from the shape:

- **`move`** finds each named card among the hand and the public zones — battlefield, graveyard, exile, command — in that order, and the response says which zone it came from. It never takes cards from the library; that is `fetch`.
- **`fetch`** takes cards from the library by name. A name not in the library is an error. The cards are taken out, the library is shuffled, and only then are any cards destined for `library_top` or `library_bottom` put back, so a card fetched to the top of the library stays on top.
- **`draw`** shows exactly the cards drawn.
- **`damage`** adds to `damage_dealt`. An effect that hits each opponent for 2 is `damage: 6`.
- **`look`** and **`search`** create a pending choice instead of completing; they are applied last, so the rest of the delta has already happened.

### Bookkeeping the service adds

- **Shuffle** after any `fetch`, and after a `search` is resolved.
- **Commander zone change**: a commander that would go to the graveyard or to exile goes to the command zone instead, and the response says so. This holds wherever the move comes from: a delta, a `choose`, a discard. When the delta sets `commander_stays`, the commander goes to the graveyard or exile as written. A commander moved to hand or library goes where it is sent.
- **Tokens** that leave the battlefield cease to exist.
- **Battlefield arrival**: anything arriving on the battlefield gets `entered_turn` set to the current turn; `battlefield_tapped` also taps it.
- **Leaving the battlefield** clears a card's tapped state and counters.
- **Land drops**: only `play` uses a land drop. Lands put onto the battlefield by `fetch` or `move` do not.
- **Notices**: end conditions are re-examined after every applied call (see `game`).

## Choices

What a player would announce while casting.

```
Choices {
  x: int                     // value of X; multiplies into the cost
  extra_cost: ManaString     // kicker, buyback, and similar; added to the cost
  modes: [string]            // recorded only
  targets: [string]          // recorded only
  notes: string              // any other choice; recorded only
  definition: CardDefinition // only for play from "outside"
}
```

The service checks that `x` and `extra_cost` are payable. Modes and targets are recorded and never judged. A card whose cost contains `{X}` played without `choices.x` is treated as X = 0, and the response says so.

## Pending Choices

`look` and `search` reveal cards the agent could not otherwise see, then wait for the agent to decide.

```
PendingChoice {
  choice_id: string
  source: string             // the card or source that caused it
  kind: "look" | "search"
  revealed: [{ id, name }]
  rest: Destination | "library"
}
```

- **`look`** reveals the top or bottom `n` cards of the library, in order starting from the end looked at: the top card first for `top`, the bottom card first for `bottom`. If the library has fewer than `n`, it reveals what there is. `rest` is required.
- **`search`** reveals the cards of the library sorted by name, so the order of the library is not disclosed. `filter` limits what is shown to cards whose name or type line contains the filter text, ignoring case. Its `rest` is always `"library"`.

A `look` or `search` that reveals no cards creates no pending choice: the call completes as `OK` and says there was nothing to reveal. A `search` still shuffles the library.

While a choice is pending the game's status is `pending_choice` (see `game`).

```
choose(game_id, choice_id, selections, rest_order?)
```

`selections` maps destinations to revealed card names. For a `look`, every revealed card not selected goes to the `rest` destination: in `rest_order` if given, otherwise in the order revealed. For a `search`, unselected cards stay in the library and the library is shuffled before any selected cards are put on its top or bottom. Cards selected to `library_top` end up with the first-named card on top, above any `rest` cards that also go to the top.

A wrong `choice_id` or a name that was not revealed is an error. Selecting nothing is allowed.

## Expect

`play` and `effect` may include `expect`: values the agent believes will be true once the call has been applied. The service compares each with the real state and adds a warning line for each mismatch. The call is applied either way; a mismatch is never a refusal.

Allowed keys: `hand`, `lands`, `untapped_lands`, `life`, `pool`, `library`, `tax`, `damage_dealt`, `step`. `tax` is the tax on the next cast of the commander (the higher, with two commanders). `pool` is compared as a set of mana symbols, ignoring their order and any spending restriction. Any other key is an error that lists the allowed keys. For a call that creates a pending choice, `expect` is evaluated when the choice is created.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| How the agent describes a card's effect | A declarative delta of outcomes | A sequence of primitive commands | One short call per card; the agent thinks "Plains onto the battlefield tapped, Forest to hand", not six steps. |
| Order of delta keys | Fixed and documented | Order as written | JSON objects do not reliably carry order through every client; a fixed order is predictable. Unusual orders split into two calls. |
| Refusals | Two kinds: errors never overridable, rule checks always overridable | A single kind; per-check configuration | The service is certain about structure and only approximately right about rules. Tenet *It's the agent's simulation*. |
| Several failed checks | Reported together, one override | One at a time | Avoids a chain of refusals for one play. |
| Casting from other zones | `from` on `play`, any zone including outside the game | Model as a `move` then an unpaid `effect` | Flashback, escape, foretell, impulse draws and wishes are everyday Commander plays and deserve the same cost checks as a cast from hand. |
| Where a played card ends up | Default by type, `to` to say otherwise | Always the default, corrected by a second call | Flashback spells are exiled, auras may fizzle; one parameter is cheaper than a correcting call. |
| Land drop from other zones | Playing a land always uses a land drop | Only from hand | The rules count a land played from the graveyard as the turn's land play. |
| Missing X | Treated as 0 and stated | Error | Tenet *Best guess, shown*. |
| Overridden unpayable cost | Nothing is tapped; played unpaid | Tap everything available as a part payment | The agent overrides because it knows something the service does not; it says what to tap. |
| Keeping a commander out of the command zone | Its own delta flag | Reuse `override` | `override` waives rule checks; tying an unrelated outcome to it would change where a commander goes whenever a call was overridden for another reason. |
| What `search` shows | The whole library sorted by name, optionally filtered | Require `fetch` by name always | Sometimes the agent needs to see what is left. Sorting hides the order. |
| `expect` mismatches | Warnings | Refusals | The call reflects what the agent meant to do; the mismatch tells it its picture has drifted, which is the purpose. |

## Open Questions & Future Decisions

### Deferred
1. A `mill` key (top *n* cards of the library to the graveyard, shown). Until then it is a `look` with `rest: "graveyard"` and an empty `choose`.
2. Attachments (which aura or equipment is on which permanent) are not tracked.
3. Copies of spells and permanents: a copy of a permanent is a token described by the agent; a copy of a spell is an `effect`.
4. Turning a permanent to its other face after it has entered (transform, flip). Until then the agent gives combat damage for such a permanent in `attack`.

## References

- `docs/high-level-design.md`
- `docs/intent/game/game-design.md` (zones, name resolution, status)
- `docs/intent/payment/payment-design.md`
- `docs/intent/records/records-design.md`
