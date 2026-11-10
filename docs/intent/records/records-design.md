---
parent: high-level-design
prefix: REC
---

# Records

## Context and Design Philosophy

The service's findings are worth only what its records are worth. Three kinds of record are kept, for two different readers.

- The **log** and the **turn snapshots** are for whoever analyses the *deck*: what was played, in what order, with what reasoning, and what the board looked like each turn.
- The **call record** is for whoever studies the *service*: every tool call exactly as it was made and answered, including the ones that were refused.

Records are data for an outside process. The service does not compute statistics from them.

## Log

One entry for every accepted call that changed a game, from `new_game` to `end_game`. Refused calls and read-only calls (`get_state`, `get_log`) produce no log entry. A resent call that was recognised and not applied again (see `game`) produces none either.

```
LogEntry {
  seq: int                   // the game's change number after this call: 1, 2, 3 ...
  turn: int                  // 0 during mulligans
  step: Step | null          // step the game was in when the call was made; null during mulligans
  tool: string
  arguments: object          // the call's arguments as received
  outcome: object | null     // what the tool produced that the fields below do not carry:
                             //   new_game: opening hand        mulligan: new hand, cards bottomed
                             //   choose: where each revealed card went
                             //   attack: attackers, blocked, targets; on the entry that enters
                             //           combat_damage: damage per attacker
                             //   advance: cards discarded       end_game: result and notes
  card: string | null        // card played, or effect source
  from: string | null        // zone a played card came from
  delta: Delta | null        // as applied, including what the service added
  choices: Choices | null
  paid: { cost, sources: [name], life, from_pool, surplus } | null
  drawn: [name]
  steps: [Step]              // steps entered by this call
  reason: string | null
  override: string | null
  overridden_checks: [string]
  expect_mismatches: [string]
  reminders: [{ card, step }]
  assumptions: [string]      // best guesses the service made in applying the call
  notices: [string]          // notices first raised by this call
}
```

`reason` is the agent's own explanation of the play and is what makes a log useful for analysis; it is stored verbatim.

## Reminders

Each reminder issued (see `turn`) is recorded on the log entry of the call that entered the step. A reminder is **answered** when, later in the same turn, an `effect` call is accepted whose `source` names the reminded permanent. Otherwise it is **unanswered**. `source` names a permanent when, ignoring case, it equals the permanent's card name, the name of its face in play, or its instance id. One such `effect` answers the reminders of every permanent it names, so two copies of a card are answered together unless an instance id is used. Whether each reminder was answered is worked out when records are read and when the turn's snapshot is written.

## Turn Snapshots

Written when the game enters `cleanup`, after any discard. When a game is ended during a turn that has no snapshot yet, one is written for that turn at that moment, so the turn in which a game is won is always recorded. A turn has at most one snapshot.

```
TurnSnapshot {
  turn: int
  hand: [{ name, payable: bool }]
  battlefield: [{ name, tapped, counters }]
  graveyard: [name]
  lands: int
  mana_available: int        // mana the agent's sources could make at the start of this turn
  mana_spent: int            // mana paid this turn, all payments
  land_drop_made: bool
  life: int
  damage_dealt: int
  commander_damage: { [commander]: [int, int, int] }
  unanswered_reminders: [{ card, step }]
}
```

`payable` asks whether the plain mana cost of the card's first face, with X as 0, could be paid if every mana source the auto payment system may use on its own were untapped (see `payment`). It says whether a card left in hand was castable in principle this turn, which is what an analysis of clunky hands needs. Lands are always `payable`.

`mana_available` is the most mana those same sources could make, counted on entering the turn's first main step, with counted amounts evaluated then. `mana_spent` is the number of mana symbols paid across the turn's payments, from sources or the pool; life paid is not counted.

## Call Record

One record for every tool call the service receives, whatever its outcome and whether or not it names a valid game.

```
CallRecord {
  id: int
  time: timestamp
  game_id: string | null     // as supplied, whether or not such a game exists
  tool: string
  arguments: object          // as received
  status: "OK" | "REJECTED" | "ERROR" | "CHOICE"
  response: string           // exactly what was returned
  is_override: bool          // the call carried an override
  change: int | null         // the game's change number after the call
}
```

For `load_deck` the `cards` argument is stored as received. For a successful `get_log` the `response` holds a one-line note of the export's size, not its content.

## `get_log`

```
get_log(game_id, since?, include_snapshots?, include_calls?)
```

Returns JSON, unlike every other tool, because its reader is a program.

```
{
  "game": { "game_id", "deck_id", "seed", "turn_limit", "draw_first_turn",
            "status", "turn", "change", "result": { "outcome", "notes" } | null },
  "entries": [LogEntry],
  "snapshots": [TurnSnapshot],
  "calls": [CallRecord]
}
```

`since` returns only entries with a sequence number greater than it, calls whose `change` is greater than it, and snapshots written by those entries. `include_snapshots` defaults to true. `include_calls` defaults to false. `get_log` is accepted in every game status.

A `get_log` call that cannot be answered — an unknown game, a malformed argument — is answered like any other tool's error, in the text format (see `tools`), not as JSON.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Two record streams | A log of accepted changes and a separate record of all calls | One stream with a status field | The two readers want different things: deck analysis should not wade through refusals, and a study of the tool surface needs them all. |
| Log format returned | JSON | The compact text format used elsewhere | The reader is a program. |
| When reminders are judged answered | At read and snapshot time, from the entries | Stored on the reminder as it happens | The answer is a fact about later entries; deriving it avoids rewriting an earlier entry. |
| Window for answering a reminder | The rest of the same turn | The same step only | A reminder met while `attack` passes through the beginning of combat could never be answered within its step; an agent that resolves a trigger a step late has still resolved it. |
| One log sequence for entries and calls | The game's change number | Separate counters; timestamps | One number orders everything about a game and is the number the agent already sees. |
| Snapshot timing | At cleanup | At the start of each turn | The end of the turn is when "what was left unused" is known. |
| `payable` definition | Payable with all sources untapped | Payable with what was untapped at cleanup | The question is whether the card was stuck, not whether mana was left over. |
| Statistics | None computed | Summary figures per game | Non-goal; analysis is done elsewhere from these records. |

## Open Questions & Future Decisions

### Deferred
1. A way to list games (by deck, by status) so an analysis process can find them without being told each id.
2. Paging for very long logs beyond `since`.

## References

- `docs/high-level-design.md` (goal 8)
- `docs/intent/storage/storage-design.md`
- `docs/intent/turn/turn-design.md` (reminders)
