# MTG Goldfishing

A service that holds the state of agent-played Commander test games, so that draws are really random, bookkeeping is checked, and every play is recorded.

## Language

### The service and who uses it

**MTG Goldfishing**:
The service itself: the keeper of game state, randomness, checks and logs.
_Avoid_: Ledger, MTG Ledger

**Agent**:
The AI that makes every decision for the seat or seats it plays and tells the service what each card does.
_Avoid_: Player, user, client

**Player brief**:
The instructions that tell an agent how to play a seat through the service's tools.
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

**Slash separator**:
In a requested card name, a `//`, or a `/` that is not part of one, with the spaces around it, read as the boundary between two face names of one card.
_Avoid_: Slash reading, split name

**Card definition**:
An agent-supplied description of a card that replaces the fetched card data for that card within one loaded deck.
_Avoid_: Card override, custom card

**Deck check**:
A rule check on a deck's construction: size, singleton, color identity, legality and commander eligibility.
_Avoid_: Deck validation, legality check

**Reading**:
What the service has worked out from a card's rules text: the mana it makes, its step triggers, its haste, vigilance, evasion, reach or flash, and whether it enters tapped.
_Avoid_: Parse, interpretation, card logic

**Assumption**:
A plain statement of what the service guessed when a reading, or a choice made for the agent, rests on less than an exact match.
_Avoid_: Caveat, heuristic, warning

### A game

**Goldfish game**:
A Commander game with no opposing seats, in which the tested seat plays against three imaginary opponents.
_Avoid_: Test game, simulation, solitaire

**Contested game**:
A Commander game between the tested seat and one to three opposing seats, with no imaginary opponents.
_Avoid_: Multiplayer game, versus game, match

**Seat**:
One player's place in a game, with its own zones, life, mana pool, land drop and commander tax, played by an agent.
_Avoid_: Player, side, opponent slot

**Table**:
What all the seats of a game share: its seed, turn order, active seat, step, stack, change number, notices and result.
_Avoid_: Board, lobby

**Tested seat**:
The seat whose deck the game is judging; every game has exactly one.
_Avoid_: Hero, home seat, main seat

**Opposing seat**:
A seat backed by a loaded deck that plays against the tested seat in a contested game.
_Avoid_: Opponent deck, enemy, AI opponent

**Imaginary opponent**:
One of the three opponents of a goldfish game, which can be dealt damage but has no cards and takes no actions.
_Avoid_: Dummy, phantom opponent

**Seat id**:
The unguessable id naming one seat of one game; a call made with it acts as that seat and sees what that seat may see.
_Avoid_: Player token, seat key

**Seat number**:
A seat's place in turn order, from 1, by which calls and responses name seats to one another.
_Avoid_: Seat index, player number

**Seed**:
The number that fixes every shuffle of a game and the order of its seats, so that the same loaded decks and seed give the same game.
_Avoid_: Random state, salt

**Card instance**:
One physical card or token in one game, with its own instance id, zone and tapped state.
_Avoid_: Card object, game card

**Owner**:
The seat whose deck a card instance came from, or whose effect created a token.
_Avoid_: Deck holder

**Controller**:
The seat that currently controls a permanent or an item on the stack; its owner unless an effect has changed it.
_Avoid_: Holder, user

**Zone**:
Where a card instance is: library, hand, battlefield, graveyard, exile, the command zone, or, in a contested game, the stack.
_Avoid_: Area, pile, location

**Hidden zone**:
A seat's hand or library, whose cards no other seat may see; no seat sees the order of any library.
_Avoid_: Private zone, secret zone

**Active seat**:
The seat whose turn it is.
_Avoid_: Current player, active player, turn owner

**Seat to act**:
A seat whose call the game is waiting on before it can go on.
_Avoid_: Priority holder, awaited seat, current player

**Round**:
One turn for each seat still in the game.
_Avoid_: Cycle, go-around

**Table turn**:
The count of turns taken by all the seats of a game together. A seat's own count of the turns it has taken is what `T<n>` shows.
_Avoid_: Global turn, game turn, absolute turn

**Elimination**:
A seat leaving a contested game, at 0 life, at 21 damage from one commander, or by conceding; it takes no more turns and the cards it owns leave the game.
_Avoid_: Death, knockout, loss

**Change number**:
The count of accepted changes to a game, shown on every response and used to recognise a call that was sent twice.
_Avoid_: Sequence id, version, revision

**Resend**:
A call that repeats the sending seat's most recent accepted change and is answered with that change's original response instead of being applied again.
_Avoid_: Retry, duplicate, replay

**End condition**:
A state that would normally end a game, such as 120 damage dealt, the tested seat or all its opponents eliminated, or a turn limit reached.
_Avoid_: Win condition, game over

**Notice**:
A standing message that an end condition has been reached, shown on every later response until the game ends.
_Avoid_: Alert, warning

### Playing

**Delta**:
The agent's statement of where things end up after a play or effect: cards moved, tapped, drawn or created, control changed, mana added, life and damage changed.
_Avoid_: Diff, patch, effect description

**Destination**:
A place a delta can send a card: a zone, the battlefield tapped, or the top or bottom of the library.
_Avoid_: Target, to-zone

**Pending choice**:
A decision the game waits on from one seat: where cards revealed by a look or search go, or what another seat's effect requires of it, such as blockers, a discard or a sacrifice.
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

### Between seats

**Stack**:
The plays and effects of a contested game that have been made but not yet resolved, newest on top, each holding the delta its controller stated.
_Avoid_: Queue, chain, pending plays

**Stack item**:
One play or effect on the stack, with its controller and the delta that controller stated.
_Avoid_: Stack entry, spell object

**Cast trigger**:
A triggered ability of the casting seat's own that triggers on its casting a spell, stated by that seat together with the spell and resolving before it.
_Avoid_: Cast window, on-cast ability

**Resolve**:
To apply the delta of the newest item on the stack, once every other seat has passed on it.
_Avoid_: Execute, commit

**Response window**:
A point at which the seats of a contested game are asked, one at a time in turn order, whether they respond before the game goes on.
_Avoid_: Priority window, response phase

**Pass**:
A seat's answer to a response window that it does nothing.
_Avoid_: Skip, decline

**Automatic pass**:
A pass the service makes for a seat that has no untapped permanents.
_Avoid_: Auto-skip, implicit pass

**Digest**:
The short account, at the start of a seat's response, of the other seats' public events, and of what their calls did to the reading seat's own hidden zones, since that seat's digest baseline.
_Avoid_: Feed, recap, catch-up

**Digest baseline**:
The change number up to which a seat has been shown the other seats' changes: that of its last response that carried a digest.
_Avoid_: Read marker, cursor

**Public form**:
What every seat may see of an event: cards that stay hidden are shown as a count, and cards in public view, or that were in public view, by name.
_Avoid_: Redacted event, censored event

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
The service's notice to a seat that a permanent it controls has a step trigger in the step just entered.
_Avoid_: Trigger alert, prompt

**Land drop**:
The one land a seat may play on each of its turns.
_Avoid_: Land play, land per turn

**Declared attack**:
The attackers, what each one attacks, which are blocked, and the damage, evasion and trample damage the attacking seat has stated for the current combat, applied on entering combat damage.
_Avoid_: Combat plan, attack declaration

**Evasion**:
An attacker's ability that limits which creatures may block it. The service checks flying (blockable only by a creature with flying or reach), horsemanship (only by a creature with horsemanship) and "can't be blocked" (by no creature).
_Avoid_: Unblockability, evasiveness

**Trample damage**:
In a contested game, the combat damage a blocked attacker deals the seat it attacks, stated by the attacking seat once blocks are known; a blocked attacker with none deals that seat nothing.
_Avoid_: Excess damage, damage through

### Records

**Log entry**:
The record of one accepted change to a game, with the acting seat's choices and reasons.
_Avoid_: History row, journal line

**Turn snapshot**:
The state of a game at the end of a turn, kept for analysis.
_Avoid_: Checkpoint, save

**Call record**:
The record of one tool call as it was made and answered, refused or not, with any opposing seat's seat id left out.
_Avoid_: Request log, audit entry
