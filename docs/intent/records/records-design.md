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

A game has one set of records, whatever its number of seats: every seat's calls and changes, hidden zones included. The record of a contested game says which seat made each entry and each call. Fields that only a contested game has are left out of a goldfish game's records, so a goldfish game's records have the same shape whether or not contested games exist.

## Log

One entry for every accepted call that changed a game, from `new_game` to `end_game`, whichever seat made it. Refused calls and read-only calls (`get_state`, `get_log`) produce no log entry. A resent call that was recognised and not applied again (see `game`) produces none either.

```
LogEntry {
  seq: int                   // the game's change number after this call: 1, 2, 3 ...
  turn: int                  // turn the game was in when the call was made; 0 during mulligans
  step: Step | null          // step the game was in when the call was made; null during mulligans
  tool: string
  arguments: object          // the call's arguments as received, JSON-string objects and lists decoded;
                             //   `game_id` holds the game id (see Seat Ids in Records)
  outcome: object | null     // what the tool produced that the fields below do not carry:
                             //   new_game: opening hand (contested: every seat's, by seat number)
                             //   mulligan: new hand, cards bottomed
                             //   choose: where each revealed card went (look, search, hand);
                             //           the blocks as applied (blocks); { text } when an
                             //           ask's answer carries answer text, otherwise null
                             //           (ask); null (resolve)
                             //   attack: attackers, blocked, targets (contested: attackers and
                             //           the seat each attacks, no blocked list; an attack that
                             //           states trample damage: each named attacker's trample
                             //           damage and the seat it attacks); on the entry
                             //           that enters combat_damage: damage per attacker
                             //           (contested: with the seat it was dealt to)
                             //   advance: cards discarded
                             //   end_game: result and notes (a concession: null result, notes;
                             //           the tested seat's in a contested game: also `final`,
                             //           every seat's state as the game ended)
  card: string | null        // card played, or effect source
  from: string | null        // zone a played card came from
  delta: Delta | null        // as applied, including what the service added
  choices: Choices | null
  cast_triggers: [{ source, delta, choices }]   // a play's cast triggers, in the order listed;
                             //   empty for every other call (contested: each also holds `item`)
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

  // contested games only
  seat: int | null           // the acting seat's number; null on new_game's entry, which no seat makes
  active: int | null         // the active seat's number when the call was made
  table_turn: int
  round: int
  stacked: string | null     // id of the stack item this call put on the stack ("s4")
  resolved: [{ item, controller, source, delta, to }]   // items this call caused to resolve, in order:
                             //   item id, controller's seat number, source, the delta applied,
                             //   and where its card went (null for an ability, which has no card)
  countered: [string]        // ids of items removed by `counter`
  removed: [string]          // ids of items that left the stack unresolved because a seat was
                             //   eliminated or the game was ended, bottom of the stack first
  auto_passes: [{ seat, item | null }]  // automatic passes this call caused, in order; item is null
                             //   in an attack or end response window with an empty stack
  no_blocks: [int]           // attacked seats the service declared no blockers for
  eliminated: [{ seat, cause }]   // in the order applied; cause: "life" | "commander_damage" | "concede"
  public: [Event]            // the public form of this call's summary and events (see `game`)
  private: { [seat number]: [Event] }   // the same events as a seat may see them, for each seat
                             //   other than the acting one that may see more than `public`
}
```

Every positional field — `turn`, `step`, `active`, `table_turn`, `round` — describes the game as it stood when the call was made, before the call was applied. The keep that starts a game is therefore recorded at turn 0 with no step and no active seat, and an `advance` that passes the turn is recorded in the turn it left. In a contested game `turn` is the own turn number of the seat that was then active, as its status line showed it; `table_turn` and `round` place the entry in the game as a whole.

A `play`'s cast triggers (see `play`) are recorded in `cast_triggers`, in the order listed, each with its `source`, `delta` and `choices`. In a goldfish game each delta is recorded as applied, with what the service added, as `delta` is. In a contested game each is recorded as stated, with `item`, the id of the stack item it became; `stacked` keeps holding the spell's id, and each cast trigger's resolution is recorded in `resolved` like any ability's.

For a call whose item goes on the stack, `delta` and `paid` record what was stated and paid when the call was applied, `stacked` holds the new item's id, and the item's resolution is recorded in `resolved` on the entry of whichever call caused it, with the delta that was actually applied (the restated one when its controller restated it). An item that leaves the stack unresolved is recorded by id on the entry of the call that caused it: in `countered` when a delta's `counter` named it, in `removed` when a seat's elimination or the tested seat's `end_game` took it off.

`auto_passes` holds only automatic passes in response windows. A seat the service declared no blockers for, because it controlled no untapped creature when blocks were requested, is listed in `no_blocks`: the two are different decisions made for a seat, and an attack window with an empty stack would otherwise make them look alike.

A seat eliminated by a call is listed in `eliminated` with one cause. When it meets both the life and the commander damage condition after the same call, the cause recorded is `life`.

### Public and private events

`public` holds the public form of the call's summary and events, in the order they happened. Every entry a seat makes has at least one public event, the public form of its summary, so no accepted change is invisible to the other seats.

Some events show one seat more than their public form, because they move a card into, between or out of that seat's own hand or library (see `game`): a card it drew when another seat's `advance` began its turn, or cards it drew when its own spell resolved on another seat's `pass`. Every other seat sees a count; the seat itself may see the names. For each such seat other than the acting one, `private` holds, under its seat number, the call's whole list of events in the form that seat may see, in the same order as `public`. A seat with no key in `private` sees the call exactly as `public` shows it. The acting seat has no key: it is told what its call did by the call's own response. Both forms are produced by the domain's filter (see `game`) when the entry is built, and a digest (see `application`) takes one of the two lists as stored.

A contested game's `new_game` is made by whoever starts the game, before any seat acts. Its entry has a null `seat`, holds every seat's opening hand in `outcome`, and has no public or private events: it is in no seat's digest.

An opposing seat's `end_game` concedes and ends nothing. Its entry's `outcome` holds a null result and the seat's notes; the `result` word it passed stays in `arguments`, the seat is listed in `eliminated` with cause `concede`, and the game's own result stays null until the tested seat ends the game.

`reason` is the agent's own explanation of the play and is what makes a log useful for analysis; it is stored verbatim (but see Seat Ids in Records).

The answer text of an `ask` answer (see `play`) is public, so besides its `outcome` it is in the entry's `public` events, and from there in every other seat's digest. It is stored as the game holds it, whitespace runs as single spaces, while `arguments` keeps `text` as received.

### Every seat's state at the end of a contested game

A contested game's turn snapshots each describe one seat, the active one, so the turn in which the game ends records only that seat's board. When the tested seat's `end_game` ends a contested game, its entry's `outcome` therefore also holds `final`: one object per seat, in seat number order (which is turn order), describing each seat as the game stands once the end has been applied — every pending choice, the open window and the stack already discarded. The caller states none of it.

```
final: [{
  seat: int
  life: int
  eliminated: bool
  hand: [name]
  battlefield: [{ name, tapped, counters }]   // the permanents the seat controls, whichever seat
                                             //   owns them, each read from its owner's deck
  graveyard: [name]
  commander_damage_taken: { [seat number]: { [commander name]: int } }
                             // every other seat, eliminated seats included: each commander of
                             //   that seat's deck and the combat damage it has dealt this seat,
                             //   zeros included; an empty map for a deck with no commander
}]
```

The zones are the ones a turn snapshot records for its seat, each card named and listed as a snapshot of that seat would name and list it, without the figures that judge one turn (`payable`, mana available and spent, the land drop). A spell that was on the stack when the game ended is in none of them; its stack item's id is in the entry's `removed`. An eliminated seat is listed like any other, as it now is: its cards have left the game, so its hand, battlefield and graveyard are empty, while its life is the life it was eliminated at and its commander damage taken is what it had taken by then.

`final` is held in `outcome` alone. It is not an event, so it is in neither `public` nor `private` and in no seat's digest, and the `end_game` response does not show it; like every record, it is read through `get_log`, which shows any seat the whole record. A goldfish game's `end_game` entry has no `final`: every snapshot of a goldfish game already describes its one seat. A concession has none either, since the game goes on.

## Reminders

Each reminder issued (see `turn`) is recorded on the log entry of the call that entered the step, with the seat it was issued to in a contested game. A reminder is **answered** when, later in the same turn — in a contested game, the same table turn — an `effect` call from that seat is accepted whose `source` names the reminded permanent. Otherwise it is **unanswered**. Acceptance is what counts: the reminder exists to catch a forgotten trigger, so it is answered once the seat has recorded the trigger, whether the stack item that `effect` made later resolves, is countered or is removed. A `pass` declines a reminder and does not answer it, but does not close it either: an `effect` naming the permanent later in the same table turn still answers it. `source` names a permanent when, ignoring case, it equals the permanent's card name, the name of its face in play, or its instance id. One such `effect` answers the reminders of every permanent it names, so two copies of a card are answered together unless an instance id is used. A cast trigger stated with `play` answers no reminder, whatever its `source` names: a reminder is for a step trigger, which is recorded with `effect`. Whether each reminder was answered is worked out when records are read and when the turn's snapshot is written.

## Turn Snapshots

Written when the game enters `cleanup`, after any discard. When a game is ended during a turn that has no snapshot yet, one is written for that turn at that moment, so the turn in which a game is won is always recorded. A turn has at most one snapshot. A game ended during mulligans has none: no turn has begun, and there is no active seat to describe. In a contested game every seat's turn has its snapshot, describing the active seat, and snapshots are numbered by table turn; one written because the tested seat ended the game describes whichever seat is active at that moment. A turn that ends because its active seat was eliminated (see `turn`) never enters `cleanup`; its snapshot is written when the turn ends, once the stack is empty, and describes that seat as it then is: its hand, battlefield and graveyard are empty and it has no lands, because the cards it owned have left the game, and its life is what it was when it was eliminated.

A snapshot reads each permanent of the described seat from its owner's deck, whichever seat controls it (see `game`): the name it gives a permanent taken from another seat, whether that permanent counts among its lands, and what it adds to the mana that judges `payable` and `mana_available` are what that permanent is for its owner.

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

  // contested games only; damage_dealt and the three-number commander_damage are left out
  seat: int                  // the active seat, which the snapshot describes
  table_turn: int
  round: int
  lives: { [seat number]: int }   // every seat; an eliminated seat keeps the life it was eliminated at
  eliminated: [int]          // seat numbers, ascending
  commander_damage: { [commander name]: { [seat number]: int } }   // the described seat's commanders;
                             //   an entry for every other seat, zeros and eliminated seats included
  unanswered_reminders: [{ card, step, seat }]   // every seat's, issued during this table turn
}
```

In a contested game seats other than the active one are reminded too, during the active seat's turn. A reminder is judged within the table turn it was issued in, so the snapshot of that table turn lists every seat's unanswered reminders, each naming the seat it was issued to.

`payable` asks whether the plain mana cost of the card's first face, with X as 0 and each Phyrexian symbol paid with mana, could be paid if every mana source the auto payment system may use on its own were untapped (see `payment`). It says whether a card left in hand was castable in principle this turn, which is what an analysis of clunky hands needs. Lands are always `payable`.

`mana_available` is the most mana those same sources could make, counted on entering the turn's first main step, with counted amounts evaluated then; tapped state and summoning sickness are ignored. `mana_spent` is the amount of mana paid across the turn's payments, from sources or the pool: a generic symbol counts as its number, and a generic hybrid symbol paid as generic counts as two. Life paid is not counted.

## Call Record

One record for every tool call the service receives, whatever its outcome and whether or not it names a valid game.

```
CallRecord {
  id: int
  time: timestamp
  game_id: string | null     // the game the supplied id names; as supplied when it names none
  seat: int | null           // contested games only: the number of the seat the supplied id names,
                             //   whatever the call's outcome; null for new_game
  tool: string
  arguments: object          // as received, JSON-string objects and lists decoded;
                             //   `game_id` holds the game id (see Seat Ids in Records)
  status: "OK" | "REJECTED" | "ERROR" | "CHOICE"
  response: string           // what was returned (see Seat Ids in Records for new_game)
  is_override: bool          // the call carried an override
  change: int | null         // the game's change number after the call
}
```

Arguments are stored as received, with any object or list parameter that was given as a JSON string decoded where it decodes to the parameter's shape; this holds for a call whose arguments could not be shaped as for any other. For `load_deck` the `cards` argument is stored as received. For a successful `get_log` the `response` holds a one-line note of the export's size, not its content.

## `get_log`

```
get_log(game_id, since?, seat?, tools?, include_snapshots?, include_calls?)
```

Returns JSON, unlike every other tool, because its reader is a program. Any seat may call it at any time, and every seat receives the whole record, hidden zones included: the service hides in its views, not in its records. The rule that a response to a seat shows only what that seat may see (see `game`) governs every other tool and does not apply to `get_log`.

```
{
  "game": { "game_id", "deck_id", "seed", "turn_limit", "draw_first_turn",
            "status", "turn", "change", "result": { "outcome", "notes" } | null,
            // contested games only:
            "table_turn", "round",
            "seats": [{ "number", "deck_id", "tested", "starting_life", "life", "eliminated" }] },
  "entries": [LogEntry],
  "snapshots": [TurnSnapshot],
  "calls": [CallRecord]
}
```

In a contested game the header's `turn` is the tested seat's own turn count, the number its status line shows, so that a deck's turn numbers read the same in both kinds of game; `table_turn` beside it is the table turn number.

`since` returns only entries with a sequence number greater than it, calls whose `change` is greater than it, and snapshots written by those entries. `include_snapshots` defaults to true. `include_calls` defaults to false. `get_log` is accepted in every game status.

Because a refused or read-only call carries the change number it was made at, a reader that polls with `since` set to the change number it last saw does not receive calls made at that same change number; a full read includes them.

### Filters

The record of a long contested game is large, and a reader often wants one part of it. Two filters narrow the export besides `since`:

- `seat` (contested games only) names the seat whose records to keep, whichever seat calls — the calling seat is the one its seat id names — and keeps the log entries and call records whose `seat` is that seat number — the calls that seat made — and the snapshots whose `seat` is that seat number, the snapshots of its turns. The `new_game` entry and call record, which no seat makes, are kept by no `seat`. Entries other seats made are left out even when they changed that seat: what a call did to another seat (a resolution, an automatic pass, an attack on it, a card it drew) is recorded on the entry of the call that caused it, and a reader following one seat's fortunes reads the whole log.
- `tools` keeps the log entries and call records whose `tool` is one of the tool names listed, each name given exactly as the tool is called. A snapshot belongs to no tool, so `tools` keeps or drops none; `include_snapshots: false` leaves snapshots out.

Filters combine: a record is kept only when every filter given keeps it, `since` included, so a snapshot is kept under `since` and `seat` when the entry that wrote it is numbered after `since` and the snapshot describes that seat. A filter applies to the sections the call includes and never to the `game` object, which is always whole. A kept record is exported exactly as an unfiltered export gives it: every field, its `public` and `private` events, and whether each reminder was answered, judged over every entry of the game.

A filter only leaves records out. `seat` is not that seat's view of the game: an entry it keeps holds the other seats' hidden zones as every entry does, and the seat ids of opposing seats were redacted when the record was stored (see Seat Ids in Records), so no filter can show more than the whole record shows.

A filter that cannot be applied is an error, answered like every `get_log` error in the text format: `seat` in a goldfish game, whose records name no seat; a `seat` that is not one of the game's seat numbers, the error listing them; a `tools` that names something that is not one of the service's tools, the error naming each such name and listing the tools; and an empty `tools`. A filter that matches nothing is not an error: `since` at or past the game's change number, or a `seat` that has made no call, gives empty sections.

## Seat Ids in Records

A seat id is the whole of a seat's access control, and `get_log` is open to every seat. So no record ever contains an opposing seat's seat id, and every record names seats by number.

- The `game_id` argument of a call made with an opposing seat's seat id is stored, in the call record and in the log entry, as the game id; the record's `seat` says which seat called.
- The stored response of a contested game's `new_game`, which lists every seat's seat id for whoever starts the game, has each opposing seat's seat id replaced by the redaction mark `[redacted]`. The response returned to the caller is not changed.
- An agent that holds several seat ids may write one where it does not belong: in a `reason`, in `notes`, in another argument. Wherever an opposing seat's seat id of the game occurs inside a string of a call record or log entry of that game — any argument value at any depth, the response text — that occurrence is replaced by `[redacted]` and the rest of the string is kept. A seat id is `g` and ten random characters, so the replacement cannot touch ordinary text.

The tested seat's seat id is the game id and is stored as such. An id that names no game or seat is stored as supplied.

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
| A turn ended by its active seat's elimination | Snapshot when the turn ends | No snapshot | Every table turn then has a snapshot, and the lives and eliminations it records show how the turn ended. |
| `payable` definition | Payable with all sources untapped | Payable with what was untapped at cleanup | The question is whether the card was stuck, not whether mana was left over. |
| Statistics | None computed | Summary figures per game | Non-goal; analysis is done elsewhere from these records. |
| Records of a contested game | One log for the game, every entry and call naming its seat | A log per seat | Analysis of the tested deck needs what the opposition did, in order; one change number already orders every seat's calls. |
| Seat ids in call records | An opposing seat's seat id is never stored: the `game_id` argument becomes the game id beside the seat number, and the stored `new_game` response is redacted | Store every call verbatim | `get_log` is open to every seat, and a verbatim record would hand each seat every other seat's id, and with it the power to act as that seat and see its hand. |
| Who made a contested game's `new_game` | No seat: a null `seat` on its entry and call record | The tested seat | The game is started by its caller, who may be an orchestrator playing no seat; the entry holds every seat's opening hand and belongs in no seat's digest. |
| The header's `turn` in a contested game | The tested seat's own turn count, with `table_turn` beside it | The table turn number | The record judges the tested deck; its turn numbers then mean the same as in a goldfish game. |
| Contested-only fields in a goldfish game | Left out | Present with fixed values | A goldfish game's records keep the shape readers already rely on. |
| Reading the log during a contested game | Any seat, whole record | Refused to seats until the game ends; filtered to the seat's view | The service hides in its views and does not police agents (tenet *It's the agent's simulation*). |
| Where a resolution is recorded | On the entry of the call that caused it | On the entry that put the item on the stack | Entries are append-only; the resolution happens later and is part of what that later call did. |
| Public events on each entry | Stored with the entry | Computed when a digest is built | The digest is then built from records alone, after any restart, without replaying calls. |
| What a seat is shown of its own hidden zones when another seat's call changed them | A `private` event list per such seat, stored beside `public` | Public events only, the seat calling `get_state` to learn what it drew | A seat's turn begins inside the previous seat's `advance`, and its spells resolve on other seats' passes; with counts alone every seat would call `get_state` each turn to learn its own draws. |
| A seat id written into free text | Redacted wherever it occurs in a stored string | Only the `game_id` argument and the `new_game` response are rewritten; the call is refused | The promise that no record holds an opposing seat's seat id must not depend on what an agent types; refusing would police the agent for a slip the record can simply not keep. |
| Stack items removed by an elimination or the end of the game | Listed by id in `removed` | Listed in `countered`; not recorded | A reader following an item from `stacked` finds on one entry why it never resolved; `countered` keeps meaning that a seat's delta countered it. |
| Seats the service declared no blockers for | Their own field, `no_blocks` | Entries of `auto_passes` | An automatic pass and a no-block are different decisions made for a seat, and in an attack window with an empty stack the two would be indistinguishable. |
| A `pass` on a reminder followed by an `effect` | The later `effect` answers the reminder | The `pass` is final | The reminder asks whether the trigger was recorded in its table turn; a seat that records it late has recorded it. |
| An `effect` answering a reminder whose item is countered | Answered on acceptance | Answered only when the item resolves | The reminder detects a forgotten trigger, not a trigger that failed. |
| Other seats' reminders in a snapshot | Every seat's unanswered reminders of the table turn, each naming its seat | The active seat's only; carried to the reminded seat's next snapshot | Reminders are judged per table turn and snapshots are keyed by table turn; the tested seat's missed triggers on other seats' turns are what an analysis looks for. |
| A game ended during mulligans | No snapshot | A snapshot at table turn 0 | No turn has begun and no seat is active; the log entries already hold every hand. |
| Where a `play`'s cast triggers are recorded | Their own `cast_triggers` list on the `play`'s entry, empty on every other entry | Folded into `delta`; one entry per cast trigger; only in `arguments` | A spell's delta and its triggers' deltas are applied at different moments and may be restated apart; a log entry records one accepted call; `arguments` hold what was received, not what was applied. |
| Where an `ask`'s answer text is recorded | The entry's `outcome` and its public events | Only in `arguments` | `outcome` holds what an answer did that no other field carries, and the public events are what the other seats are shown; `arguments` are kept as received, before the text is held on one line. |
| Positional fields of an entry | The game before the call | The game after the call | A call is recorded where it was made; what it moved the game to is in `steps` and the next entry. |
| Where every seat's state at the end of a contested game is recorded | `final` in the outcome of the tested seat's `end_game` entry | One end-of-game snapshot per seat; one end-of-game snapshot listing every seat; stated by the caller in `notes` | A snapshot per seat would key snapshots by seat as well as table turn, a migration of every stored snapshot, and break "one snapshot per table turn"; an end-of-game snapshot is written only when the turn has none, so a game ended in `cleanup` or during mulligans would lose the boards; every contested game that ends has exactly one such entry, which needs no change to storage. The service already holds the state, so the caller restating it could only add mistakes. |
| An eliminated seat in `final` | Listed, as it now is: empty zones, the life it was eliminated at | Left out; its board as it was when it was eliminated | One object per seat in turn order lets a reader index seats without checking for gaps; the cards it owned have left the game, and its last board is in the snapshot of its last turn and the events of the entry that eliminated it. |
| A permanent in `final` | The snapshot's `{ name, tapped, counters }` | Adding its owner and instance id | A reader reads a board the same way in every record; a change of control is in the entries' deltas. |
| `final` in a goldfish game | None | `final` on every game's `end_game` entry | Every goldfish snapshot describes its one seat, and a goldfish game's records keep the shape readers rely on. |
| What `seat` keeps | Records of calls the seat made, and the snapshots of its turns | Also entries that changed the seat; that seat's view, its `private` events in place of `public` | "Made by" is one field compared; "changed" has no single definition (a resolution, an automatic pass, an attack, a draw) and would grow with every new field. A view would make a filter show less than the record, and `get_log` hides nothing from any seat. |
| How entries are selected by kind | `tools`, matching the entry's `tool` | A new entry kind field; event types | The tool is already what names what an entry records, on entries and call records alike; event types would select inside entries rather than entries. |
| `tools` and snapshots | Snapshots kept or dropped as without `tools` | Only snapshots written by kept entries; no snapshots | A snapshot belongs to a turn, not to the call that happened to end it; `include_snapshots` already leaves them out. |
| A filter naming no tool or no seat of the game | Error | Accepted, matching nothing | A misspelt tool name or a wrong seat number would otherwise read as "nothing happened" (tenet *Pushback over fidelity*). |
| Taking in a long log | Filters on `get_log` | A summary mode (life, commander damage and cards cast per turn); writing the export to a file path the caller names | A summary is statistics, which the service does not compute (see the HLD's non-goals); the service and the agent may not share a disk, and a file a hosted service writes would be on its own (tenet *Build for local, don't block hosted*). |

## Open Questions & Future Decisions

### Deferred
1. A way to list games (by deck, by status) so an analysis process can find them without being told each id.
2. Paging for very long logs beyond `since`.
3. A call-record cursor for `get_log`, so incremental readers also receive refused and read-only calls made at the change number they last saw.

## References

- `docs/high-level-design.md` (goal 8)
- `docs/intent/storage/storage-design.md`
- `docs/intent/turn/turn-design.md` (reminders)
