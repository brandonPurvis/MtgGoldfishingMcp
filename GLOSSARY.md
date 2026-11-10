# MTG Goldfishing

A service that holds the state of agent-played Commander test games, so that draws are really random, bookkeeping is checked, and every play is recorded.

## Language

### The service and who uses it

**MTG Goldfishing**:
The service itself: the keeper of game state, randomness, checks and logs.
_Avoid_: Ledger, MTG Ledger

**Agent**:
The AI player that makes every decision in a game and tells the service what each card does.
_Avoid_: Player, user, client

**Player brief**:
The instructions that tell an agent how to play a goldfish game through the service's tools.
_Avoid_: Tester brief, prompt

### Decks and cards

**Loaded deck**:
A validated deck list held by the service and identified by an id derived from its contents.
_Avoid_: Deck file, deck version, registered deck

**Card data**:
What is known about a card before any game: its faces, costs, type lines, rules text and color identity.
_Avoid_: Card info, oracle data

**Face**:
One named, castable side of a card; a single-faced card has exactly one.
_Avoid_: Side, half

**Card definition**:
An agent-supplied description of a card that replaces the fetched card data for that card within one loaded deck.
_Avoid_: Card override, custom card

**Deck check**:
A rule check on a deck's construction: size, singleton, color identity, legality and commander eligibility.
_Avoid_: Deck validation, legality check

**Reading**:
What the service has worked out from a card's rules text: the mana it makes, its step triggers, its haste, vigilance or flash, and whether it enters tapped.
_Avoid_: Parse, interpretation, card logic

**Assumption**:
A plain statement of what the service guessed when a reading, or a choice made for the agent, rests on less than an exact match.
_Avoid_: Caveat, heuristic, warning

### A game

**Goldfish game**:
A Commander game played by one agent against three imaginary opponents who take no actions.
_Avoid_: Test game, simulation, solitaire

**Seed**:
The number that fixes every shuffle of a game, so that the same loaded deck and seed give the same game.
_Avoid_: Random state, salt

**Card instance**:
One physical card or token in one game, with its own instance id, zone and tapped state.
_Avoid_: Card object, game card

**Zone**:
Where a card instance is: library, hand, battlefield, graveyard, exile or the command zone.
_Avoid_: Area, pile, location

**Change number**:
The count of accepted changes to a game, shown on every response and used to recognise a call that was sent twice.
_Avoid_: Sequence id, version, revision

**Resend**:
A call that repeats the game's most recent accepted change and is answered with that change's original response instead of being applied again.
_Avoid_: Retry, duplicate, replay

**End condition**:
A state that would normally end a game, such as 120 damage dealt or a turn limit reached.
_Avoid_: Win condition, game over

**Notice**:
A standing message that an end condition has been reached, shown on every later response until the game ends.
_Avoid_: Alert, warning

### Playing

**Delta**:
The agent's statement of where things end up after a play or effect: cards moved, tapped, drawn or created, mana added, life and damage changed.
_Avoid_: Diff, patch, effect description

**Destination**:
A place a delta can send a card: a zone, the battlefield tapped, or the top or bottom of the library.
_Avoid_: Target, to-zone

**Pending choice**:
A look or search that has revealed cards and waits for the agent to say where they go.
_Avoid_: Prompt, open decision

**Refusal**:
A call the service did not apply: either an error or a failed rule check.
_Avoid_: Failure, denial

**Error**:
A refusal for something structurally impossible or malformed, which can never be overridden.
_Avoid_: Hard error, exception

**Rule check**:
A refusal based on card data that the agent can override with a stated reason.
_Avoid_: Validation, warning, soft error

**Override**:
The agent's stated reason for applying a call despite failed rule checks.
_Avoid_: Force, bypass

**Expectation**:
A value the agent believes will hold after its call, compared with the real state and reported when it differs.
_Avoid_: Assertion, check

### Mana and payment

**Mana pool**:
Mana that has been made and not yet spent; it empties when the game leaves a step.
_Avoid_: Floating mana, mana buffer

**Mana source**:
A permanent the service knows can make mana: one with a mana ability reading, or a token or card definition that says what it produces.
_Avoid_: Mana producer, rock, dork

**Commander tax**:
The {2} added to a commander's cost for each previous cast of it from the command zone.
_Avoid_: Tax cost, recast cost

**Auto payment system**:
The part of the service that chooses which mana sources pay a cost when the agent does not say, so as to leave the agent the most options afterwards.
_Avoid_: Auto-tapper, payment solver

### Turns and combat

**Step**:
One of the twelve stages of a turn, from untap to cleanup.
_Avoid_: Phase (except in card text), stage

**Step trigger**:
A beginning-of-step ability of a permanent, such as "At the beginning of your upkeep".
_Avoid_: Step-based trigger, upkeep trigger, timed trigger

**Reminder**:
The service's notice to the agent that a permanent has a step trigger in the step just entered.
_Avoid_: Trigger alert, prompt

**Land drop**:
The one land the agent may play each turn.
_Avoid_: Land play, land per turn

**Declared attack**:
The attackers, blocked attackers and damage the agent has declared for the current combat, applied on entering combat damage.
_Avoid_: Combat plan, attack declaration

### Records

**Log entry**:
The record of one accepted change to a game, with the agent's choices and reasons.
_Avoid_: History row, journal line

**Turn snapshot**:
The state of a game at the end of a turn, kept for analysis.
_Avoid_: Checkpoint, save

**Call record**:
The record of one tool call exactly as it was made and answered, refused or not.
_Avoid_: Request log, audit entry
