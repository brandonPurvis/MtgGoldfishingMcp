---
parent: high-level-design
prefix: PLAY
---

# Play

## Context and Design Philosophy

This is where a seat tells the service what happened. `play` plays a card; `effect` records any other change; `choose` answers a pending choice. In each the agent states the **outcome** — where things end up — and the service supplies the bookkeeping the outcome implies.

The service does not know whether the outcome is what the card would really do. It checks what card data lets it check, refuses what is structurally impossible, and trusts the rest.

Every call is made by one seat, the **acting seat** (see `game`). A delta changes the acting seat's own cards and life, and may reach other seats only where this design says so. In a goldfish game the acting seat is the only seat, and every play and effect is applied at once. In a contested game a spell or an ability goes on the stack with its delta, and the delta is applied when the item resolves (see `stack`); what this design says about applying a delta then holds at resolution. The call that puts the item on the stack checks the delta's shape, its seat numbers and its `counter` entries; the cards it names are looked for only when it is applied.

## Errors and Rule Checks

Every refusal is one of two kinds.

**Errors** are structural impossibilities. They can never be overridden, and nothing is applied.

- unknown game or seat, or a call the seat may not make now (see `game`);
- a card name that resolves to nothing in the zone the operation needs;
- a card chosen in `choose` that was not revealed;
- a malformed argument: an unknown delta key, an unknown `expect` key, an unparseable mana string, a destination that does not exist, a delta holding more than one of `look`, `search` and `look_at_hand`;
- a delta that reaches another seat's hand or library (see Reaching other seats);
- a seat number that is not in the game, or names an eliminated seat;
- a delta key only a contested game has (`counter`, `control`, `ask`, `look_at_hand`, `life` or `damage` given per seat) used in a goldfish game, or `damage` given as a single number in a contested game;
- `counter` naming something not on the stack;
- a card played from outside the game whose card data cannot be obtained and for which no definition was given;
- `cast_triggers` on a `play` of a land, or a cast trigger that is malformed (see Cast triggers);
- answer text given to a pending choice that is not an `ask`, or answer text longer than 200 characters (see Pending Choices).

**Rule checks** are approximations from card data. A failed check refuses the call with an explanation, and nothing is applied. The agent may resubmit the same call with `override: "<reason>"`; the call is then applied and the override recorded.

- the cost is not payable;
- the land drop for the turn is used;
- a card that is not an instant and does not have flash is cast other than in a main step of the caster's own turn with the stack empty;
- a land is played other than in a main step of the player's own turn with the stack empty;
- `pay` on `play` gives an explicit cost (see `payment`);
- a summoning-sick creature is named as a mana source in `pay`.

When a call fails several rule checks, the refusal lists all of them, and one `override` covers them all. Errors are reported before rule checks; a call with an error is never applied, override or not.

A call is applied completely or not at all.

Asking for a change that is already so is neither: tapping a tapped permanent, untapping an untapped one, or lowering a counter below zero is applied as far as it can be (the counter stops at zero) and the response notes it.

When "cost not payable" is overridden, nothing is tapped and nothing is spent: the card is played unpaid and the response says so. The agent taps what it means to with the delta's `tap` key in the same call.

## `play`

```
play(game_id, card, from?, to?, delta?, choices?, pay?, cast_triggers?, expect?, reason?, override?)
```

Plays `card` — a land, a spell, or the commander.

**Where it comes from.** `from` names the zone: `hand`, `command`, `graveyard`, `exile`, `library`, or `outside`. When omitted, the card is looked for in hand and then in the command zone. The acting seat plays from its own zones; from a public zone it may also play a card another seat owns, when the agent names it (by instance id, or by name when the acting seat has no such card). `library` finds the card by name anywhere in the library without revealing or disturbing anything else. `outside` brings in a card that is not part of the game: a new instance is created from card data resolved by name before the call is applied (see `card-data`), or from a `definition` given inside `choices` (same shape as a deck's card definition). Readings are made for it as for any card. If the name is not found, or card data is unavailable, and no definition was given, the call is an error that asks for one.

**Which face.** If `card` names one face of a multi-face card, that face is the one played and its cost, type line and power are the ones used. A face with no mana cost of its own costs nothing, and the response notes that.

**Lands.** If the played face is a land, there is no cost and a land drop is used. This is true from any zone.

**Entering tapped.** A permanent that is played enters tapped when its enters-tapped reading says so (see `card-reading`), and untapped otherwise. When the reading rests on an assumption, the response states it. The same applies to permanents arriving by `fetch` or `move` to `battlefield`; the `battlefield_tapped` destination always taps.

**Spells.** Otherwise the cost is the face's mana cost with each `{X}` replaced by `choices.x`, plus `choices.extra_cost`, plus commander tax when the card is cast from the command zone ({2} for each previous cast of that commander from the command zone). The cost is paid as `payment` describes. Casting from the command zone increases that commander's cast count. The count belongs to the commander, not to the seat casting it: a seat that casts another seat's commander from the command zone pays that commander's tax and raises it for the next cast, its owner's included.

**Where it ends up.** `to` names the destination. When omitted: a permanent goes to the battlefield under the acting seat's control, with its `entered_turn` set; an instant or sorcery goes to its owner's graveyard.

**Then the delta is applied** (below). In a contested game a spell is paid for and put on the stack, and its destination and delta wait for it to resolve (see `stack`); a land is applied at once.

### Cast triggers

A **cast trigger** is a triggered ability of the casting seat's own that triggers on its casting the spell: "whenever you cast an instant, copy it", "when you cast this spell, draw a card". The service never looks for one in card text; the casting seat states each one with the `play` that casts the spell, so that it resolves before the spell even when no other seat can respond (see `stack`).

```
CastTrigger {
  source: string             // what triggered, free text as for `effect`
  delta: Delta               // what the trigger does
  choices: Choices | null    // recorded as for `effect`
}
```

`cast_triggers` is a list of these, in the order they resolve: the first listed resolves first. An entry has `source` and `delta`, may have `choices`, and holds nothing else. A cast trigger's `choices` are recorded only: with no cost to multiply or add to and no card to define, its `x`, `extra_cost` and `definition` do nothing. A call with `expect` that puts cast triggers on the stack compares its expected values once the last of them is on, before any resolves. A cast trigger has no cost of its own: a trigger that asks for a payment as it resolves states what is tapped in its delta, as an overridden unpayable cost does. Each cast trigger's delta is checked as an `effect`'s would be when the call is made — in a contested game, as for any delta that goes on the stack — and an error in any of them refuses the whole call. An omitted or empty `cast_triggers` changes nothing. A land is not cast, so `cast_triggers` on a `play` whose played face is a land is an error; a trigger on playing a land is recorded with `effect`.

Only the casting seat's own cast triggers are stated this way, the spell's own "when you cast this spell" among them. Another seat's trigger on the same cast ("whenever an opponent casts a spell") is that seat's to record, with `effect`, in the first window it is asked in after the cast (see `stack`).

In a contested game each cast trigger is put on the stack as an ability above the spell (see `stack`). In a goldfish game, which has no stack, the call applies them in the order a contested game would resolve them when no seat responds: the cost is paid, the spell's card leaves the zone it was played from, each cast trigger's delta is applied in the order listed, the spell's card found by none of them, and then the card goes to its destination and the spell's delta is applied. A goldfish game holds at most one pending choice, created by the last part of a call, so a cast trigger's delta there may not hold `look` or `search`; such a trigger is recorded with `effect` after the `play`.

## `effect`

```
effect(game_id, source, delta, choices?, pay?, expect?, immediate?, reason?, override?)
```

Records any change not caused by playing a card: an activated ability, a trigger, sacrificing a Treasure, an imaginary opponent's removal spell in a goldfish game. In a contested game it puts an ability on the stack, unless `immediate` is true: then it is applied at once, for mana abilities, special actions, the result of combat between creatures, and corrections (see `stack`). In a goldfish game `immediate` changes nothing. `source` says what is responsible. It is free text; when it names a reminded permanent by the rule in `records` (its card name, the name of its face in play when reminded, or its instance id, ignoring case, whether or not the permanent is still on the battlefield), the call answers that permanent's reminders for the current turn. `pay`, when given, pays a cost exactly as for `play`; when omitted nothing is paid. The cost is paid before the delta is applied, so mana added by the same call's delta cannot pay it.

## Delta

Every key is optional.

```
Delta {
  counter:  [item]                        // contested: stack items to counter, by id or spell name
  untap:    [name]
  tap:      [name]
  mana:     ManaString                    // added to the acting seat's pool
  tokens:   [TokenSpec]
  counters: { [name]: { [kind]: int } }   // signed changes; a kind reaching 0 is removed
  control:  { [seat number]: [name] }     // contested: permanents that seat now controls
  move:     { [destination]: [name] }     // cards in the acting seat's hand, a public zone, or countered on the stack
  commander_stays: bool                   // let a commander go to the graveyard or exile
  discard:  [name]                        // the acting seat's hand → its graveyard
  fetch:    { [destination]: [name] }     // the acting seat's library → destination, by name
  draw:     int                           // the acting seat draws
  life:     int | { [seat number]: int }  // signed change: the acting seat's life, or per seat (contested)
  damage:   int | { [seat number]: int }  // noncombat damage: pooled to imaginary opponents (goldfish), or per seat (contested)
  shuffle:  bool                          // the acting seat's library
  ask:      [{ seats: [seat number] | "opponents", text: string }]   // contested: decisions other seats owe
  look_at_hand: seat number               // contested: see another seat's hand
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

Keys are applied in the order listed above, whatever order the agent wrote them in; `ask`, `look_at_hand`, `look` and `search` create pending choices and come last. A card that needs a different order (draw, then put a card back, then shuffle) is recorded as a `play` followed by one or more `effect` calls.

Details that are not obvious from the shape:

- **`move`** finds each named card among the acting seat's hand and the public zones of every seat — battlefield, graveyard, exile, command — in that order, and the response says which zone it came from. The zones are searched one after another, each across every seat before the next zone is tried, and within a zone the acting seat's cards come first (see `game`); so a removal spell that names a card finds an opponent's copy on the battlefield before the acting seat's own copy in its graveyard. It never takes cards from a library; that is `fetch`. A card goes to its **owner's** hand, graveyard, exile, library or command zone, whoever moves it; to the battlefield it goes under the acting seat's control. A card moved to the battlefield from the battlefield leaves and arrives again: its counters and tapped state are cleared, its `entered_turn` is set, and the acting seat controls it, whoever did before; a later `effect` with `control` gives it to another seat. A spell's card on the stack can be moved only by the delta that counters its item: for such a delta a name means the countered card first, and for any other delta `move` does not look on the stack, so a name shared with a spell on the stack moves the card in hand or in a public zone, and a name or instance id found only on the stack is an error.
- **`fetch`** takes cards from the library by name. A name not in the library is an error. The cards are taken out, the library is shuffled, and only then are any cards destined for `library_top` or `library_bottom` put back, so a card fetched to the top of the library stays on top. Each list fetched to the library is placed top to bottom, its first-named card topmost.
- **`draw`** shows exactly the cards drawn.
- **`damage`** in a goldfish game adds to the pooled damage against the imaginary opponents; an effect that hits each opponent for 2 is `damage: 6`. In a contested game it is a map from seat number to damage, and each amount is taken from that seat's life; it never counts as commander damage.
- **`life`** as a number changes the acting seat's life; as a map, each named seat's.
- **`control`** gives control of each named permanent to the seat named, until it leaves the battlefield or that seat is eliminated. It names permanents on the battlefield, by name or instance id; a card anywhere else is an error. A permanent that changes controller counts as newly arrived for its new controller: its `entered_turn` is set to the table turn, so a creature taken this turn fails the summoning-sickness checks of `attack` and `payment` unless the agent says it has haste, and its tapped state and counters stay as they are. Naming the seat that already controls a permanent changes nothing and is noted.
- **`counter`** removes each named item from the stack without applying its delta (see `stack`).
- **`ask`** creates one pending choice for each named seat (`"opponents"` names every other seat still in the game), carrying `text`: what the effect requires of that seat ("sacrifice a creature", "discard two cards"). Entries are taken in the order listed, and the seats of one entry in turn order from the seat after the acting seat. An entry has `seats` and `text` and nothing else. `seats` may include the acting seat itself, which then answers last of that entry, for an effect whose own part depends on what the others chose. Each seat answers with its own delta (see Pending Choices).
- **`look_at_hand`** creates a pending choice for the acting seat that reveals the named seat's hand, for effects that look at a hand and may take from it. It takes one seat number, of a seat other than the acting seat. The hand is shown as it is when the choice is created; in a delta that also has `ask`, the choice is created only after every `ask` of that delta has been answered, so it never shows a card an answer has already discarded.
- **`look`** and **`search`** create a pending choice instead of completing; they are applied last, so the rest of the delta has already happened.

### Bookkeeping the service adds

- **Shuffle** after any `fetch`, and after a `search` is resolved.
- **Commander zone change**: a commander that would go to the graveyard or to exile goes to its owner's command zone instead, and the response says so. This holds wherever the move comes from: a delta, a `choose`, a discard. When the delta sets `commander_stays`, the commander goes to the graveyard or exile as written. A commander moved to hand or library goes where it is sent.
- **Tokens** that leave the battlefield cease to exist.
- **Battlefield arrival**: anything arriving on the battlefield gets `entered_turn` set to the table turn, the game's count of turns taken by all seats (in a goldfish game, the turn number); `battlefield_tapped` also taps it.
- **Leaving the battlefield** clears a card's tapped state and counters, and returns it to its owner's control.
- **Tokens** are owned and controlled by the seat whose delta creates them.
- **Land drops**: only `play` uses a land drop. Lands put onto the battlefield by `fetch` or `move` do not.
- **Notices and eliminations**: end conditions are re-examined after every applied call, and in a contested game every seat is checked for elimination each time one delta has been applied in full — never between the keys of a delta, so a seat at 0 life partway through a delta and above 0 at its end stays in the game (see `game`).

## Reaching Other Seats

In a contested game a delta may reach another seat in these ways only:

- `tap`, `untap`, `counters` and `control` on that seat's permanents on the battlefield, and `move` on its cards in any public zone;
- `counter` on its items on the stack;
- `life` and `damage` per seat;
- `ask`, for anything that seat must decide or that touches its hand or library (a discard, a sacrifice, a draw);
- `look_at_hand`, to see its hand.

A name is never looked for in another seat's hand or library. In `move`, `discard`, `fetch` or `tap`, a name that matches nothing where the operation looks is the same error whether or not another seat holds such a card, since a different error would say what is in that seat's hand; in a contested game the error adds that other seats' hands and libraries are reached through `ask`. An instance id of a card in another seat's hand or library is an error saying that the card is in a hidden zone of that seat, named by seat number, and that such zones are reached through `ask`, without saying which of the two zones the card is in; an instance id's owner and its absence from every public zone are already in view (see `game`).

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

A pending choice is a decision the game waits on from one seat. `look` and `search` reveal cards the acting seat could not otherwise see; `ask` and `look_at_hand` are decisions between seats in a contested game; `stack` and `combat` add their own kinds.

```
PendingChoice {
  choice_id: string
  seat: seat number          // the seat that answers it
  source: string             // the card or source that caused it
  kind: "look" | "search" | "hand" | "ask" | "resolve" | "blocks"
  revealed: [{ id, name }]   // look, search, hand
  rest: Destination | "library" | "hand"
  from: "top" | "bottom"     // the end a look revealed from
  asked_by: seat number      // ask: the seat whose effect asks; hand: the looking seat
  hand_of: seat number       // hand: the seat whose hand is shown
  text: string               // ask: what is required
}
```

Pending choices are answered one at a time, in the order they were created; while one waits, its seat is the seat to act (see `game`). In a goldfish game at most one is pending, and it is always a `look` or a `search`.

When a seat is eliminated, the pending choices addressed to it are discarded. An `ask` its effect addressed to another seat still waits and is answered by that seat, because the effect has already resolved. A `hand` choice showing the eliminated seat's hand is discarded, because the cards it shows have left the game (see `game`).

- **`look`** reveals the top or bottom `n` cards of the library, in order starting from the end looked at: the top card first for `top`, the bottom card first for `bottom`. `from` defaults to `top`. If the library has fewer than `n`, it reveals what there is. `rest` is required.
- **`search`** reveals the cards of the library sorted by name, so the order of the library is not disclosed. `filter` limits what is shown to cards whose name, or any face's name or type line, contains the filter text, ignoring case. Its `rest` is always `"library"`.

A `look` or `search` that reveals no cards creates no pending choice: the call completes as `OK` and says there was nothing to reveal. A `search` still shuffles the library.

While a choice is pending the game's status is `pending_choice` (see `game`).

```
choose(game_id, choice_id, selections?, rest_order?, delta?, text?, restate?, blocks?)
```

Each kind is answered with its own argument; any other argument given is an error.

| Kind | Answered with |
|---|---|
| `look`, `search` | `selections`, and for `look` optionally `rest_order` |
| `hand` | `selections`, and optionally `delta` holding only `control` |
| `ask` | `delta`: the answering seat's own delta, applied at once; it may not create a pending choice; and optionally `text`, the answer text |
| `resolve` | `restate`, or nothing (see `stack`) |
| `blocks` | `blocks` (see `combat`) |

`selections` maps destinations to revealed card names. For a `look`, every revealed card not selected goes to the `rest` destination: in `rest_order` if given, listed top to bottom; otherwise cards returned to the end of the library they were looked at from keep their order there, and cards sent anywhere else go in the order revealed. For a `search`, unselected cards stay in the library and the library is shuffled before any selected cards are put on its top or bottom. Cards selected to `library_top` end up with the first-named card on top, above any `rest` cards that also go to the top.

For a `hand` choice, revealed cards not selected stay in the hand they were shown from, and a selected card goes to its owner's zones: its owner's graveyard, exile, library or hand. Selected to the battlefield, it enters under its owner's control, unless the answer's `delta` gives it to another seat with `control`, as when the looking seat puts the card onto the battlefield under its own control. That `delta` may hold `control` alone, naming only cards selected to the battlefield; anything else in it is an error.

The service does not judge an `ask` answer against its `text`; the answering seat is trusted, as every seat is. Its delta may hold any key except those that create a pending choice, with the reach any delta of that seat has, and it may be omitted or empty when the seat has nothing to do.

Some effects ask a seat for words rather than a change: name a card, guess, choose a number, choose a color. The answer to an `ask` may carry **answer text** in `text` saying what the seat named, guessed or chose ("Lightning Bolt", "7"), with or without a delta. Naming and guessing are announced at the table in Magic, so the answer text is public: every seat is shown it with the answer (see `game`), and it is recorded. The service never judges it, never compares it with the asking `text` or with the answer's delta, and never applies it: what follows from the named card is stated by the seats' deltas, the answering seat's own or the asking seat's later ones. The answer text is held with surrounding whitespace removed and every run of whitespace inside it, line breaks included, as one space, so that it reads on one line; text that is empty once so held counts as no answer text. Held text longer than 200 characters is an error: it would be repeated in every other seat's digest, and no card name or guess needs more.

Answer text is accepted only for an `ask`. Every other kind is answered by structured arguments that say the whole answer — cards selected, blocks, a restated delta — and a second, free-text channel beside them would carry nothing the service or the other seats could rely on.

A wrong `choice_id`, a choice addressed to another seat, or a name that was not revealed is an error. Selecting nothing is allowed.

## Expect

`play` and `effect` may include `expect`: values the agent believes will be true once the call has been applied. The service compares each with the real state and adds a warning line for each mismatch. The call is applied either way; a mismatch is never a refusal.

Allowed keys: `hand`, `lands`, `untapped_lands`, `life`, `pool`, `library`, `tax`, `damage_dealt`, `step`. Each refers to the acting seat; `lands` and `untapped_lands` count the lands it controls, whoever owns them. `damage_dealt` exists only in a goldfish game; in a contested game it is an error. `tax` is the tax on the next cast of the commander (the higher, with two commanders). `pool` is compared as a multiset of mana symbols, ignoring their order and any spending restriction. Any other key is an error that lists the allowed keys. For a call that creates a pending choice, `expect` is evaluated when the choice is created. For a call whose item goes on the stack, `expect` is evaluated when the call is applied, not at resolution.

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
| Reaching other seats' hidden zones | Only through `ask` and `look_at_hand` | Any delta may move cards from another seat's hand or library | The acting seat cannot know another seat's hidden cards, and choosing them is that seat's decision. |
| Decisions another seat owes | `ask`, answered by that seat's own delta | Structured kinds per effect (sacrifice, discard, draw) | One shape covers every such effect; the service would only be checking what it does not understand. |
| Where moved cards go | Their owner's zones | The acting seat's zones | A card always goes to its owner's graveyard, hand, library or exile in Magic, and records follow the owner. |
| A card taken from another seat's hand to the battlefield | Enters under its owner's control unless the answer's `control` says otherwise | Enters under the looking seat's control | Most effects that take a card from a hand discard or exile it, and one that puts it onto the battlefield does not always give it to the looking seat; the owner is the default every other move uses, and one key states the exception. |
| Search order of `move` across seats | Zone by zone, each zone across every seat, the acting seat first within a zone | Seat by seat, all of the acting seat's zones before any other seat's | Removal names a permanent far more often than a card in a graveyard; seat-first would exile the acting seat's own graveyard copy in place of the opponent's permanent in a mirror match. |
| A name that might be in another seat's hand or library | Never looked for there; one not-found error either way | A distinct error when another seat holds the card | A distinct error would tell the acting seat what is in that hand or library. |
| A permanent that changes controller | Counts as arrived this turn; tapped state and counters kept | `entered_turn` unchanged | A creature taken this turn cannot attack or tap for mana in Magic unless it has haste; the rule checks then say so, and the agent that knows better lists it in `haste` or overrides. |
| A `move` to the battlefield of a card already there | It leaves and arrives again under the acting seat's control | No change; re-entry under its owner's control | A blink is a move like any other, and every move to the battlefield enters under the acting seat's control; one rule, corrected by `control` when the card says otherwise. |
| The hand shown when a delta both asks and looks | Read after the asks are answered | Read when the delta is applied | A hand read early would show cards the answers have already discarded, and choosing one would have no meaning. |
| The acting seat named in its own `ask` | Allowed, answered last | Error | Nothing structural forbids it, and an effect whose own part follows the others' choices needs it. Tenet *It's the agent's simulation*. |
| Tax on another seat's commander cast from the command zone | The commander's own count sets the tax and rises | No tax and no count for a seat that does not own it | Commander tax is defined per commander; a second count per casting seat would be a rule with no card behind it. |
| `damage` in a contested game | A map from seat number | A single number split by the service | There is no pool to split: each seat's life is its own, and splitting would be a decision. |
| Timing check across turns | Sorcery speed means the caster's own main step with an empty stack | Any main step | In a contested game it is often another seat's main step; casting a sorcery then is the error the check exists to catch. |
| How a seat states its cast triggers | A `cast_triggers` list on the `play` that casts the spell | A window in which the caster is asked first after casting; a separate `effect` after the `play`; the service reading "whenever you cast" in card text | A window for the caster would cost a call on every spell, most of which have no cast trigger. A later `effect` arrives too late in a contested game, where a spell nobody can answer resolves within the `play`. Reading card text for triggers is a non-goal: the controller states its triggers. |
| What a cast trigger carries | `source`, `delta` and optionally `choices`, the shape of an ability `effect` puts on the stack | Also `pay`; also `immediate` | One shape for every held ability. Cast triggers rarely cost anything, and the few that ask for a payment as they resolve state what is tapped in their delta; a cost paid with the spell's would make one call pay two costs from one auto payment. A trigger is never immediate: resolving before the spell is its point. |
| Order of several cast triggers | The first listed resolves first | The first listed goes on the stack first and resolves last | An agent lists what happens in the order it happens; that reading also serves a goldfish game, which has no stack to picture. |
| Cast triggers in a goldfish game | Accepted, applied before the spell's card is moved and its delta applied | An error, as for keys only a contested game has; applied after the spell | One call means the same in both kinds of game, and the order matches what a contested game resolves when no seat responds. A cast trigger is not a matter between seats, so it has no reason to be contested-only. |
| A goldfish cast trigger that would reveal cards | An error; recorded with `effect` after the `play` | A pending choice created partway through the call, the rest waiting | A goldfish game holds at most one pending choice, always created last; a call that stops halfway would need a stack the goldfish game does not have. |
| Free text on an answer | `text` on the answer to an `ask` only, public, never judged | On every kind of answer; private to the asking seat; a structured "named card" field | Only an `ask`'s requirement is free text the service cannot structure. Naming a card or a guess is announced at the table. A named card checked against card data would be the service judging an answer, which it does for no `ask`. |
| Long or multi-line answer text | Whitespace runs held as one space; over 200 characters an error | Truncated when shown; no limit | Every other seat reads the text in its digest; truncation would hide part of an answer the asking seat must check, and a line break would split one digest line in two. |

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
- `docs/intent/stack/stack-design.md` (when a delta is applied in a contested game; the `resolve` choice)
- `docs/intent/combat/combat-design.md` (the `blocks` choice)
- `docs/intent/records/records-design.md`
