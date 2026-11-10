# MTG Goldfishing

A service that holds the state of agent-played Commander test games, so that draws are really random, bookkeeping is checked, and every play is recorded.

## Language

**MTG Goldfishing**:
The service itself: the keeper of game state, randomness, checks and logs.
_Avoid_: Ledger, MTG Ledger

**Agent**:
The AI player that makes every decision in a game and tells the service what each card does.
_Avoid_: Player, user, client

**Goldfish game**:
A Commander game played by one agent against three imaginary opponents who take no actions.
_Avoid_: Test game, simulation, solitaire

**Loaded deck**:
A validated deck list held by the service and identified by an id derived from its contents.
_Avoid_: Deck file, deck version, registered deck

**Card definition**:
An agent-supplied description of a card that replaces the fetched card data for that card within one loaded deck.
_Avoid_: Card override, custom card

**Auto payment system**:
The part of the service that chooses which mana sources pay a cost when the agent does not say, so as to leave the agent the most options afterwards.
_Avoid_: Auto-tapper, payment solver

**Mana source**:
A permanent whose rules text the service has read as able to make a known amount and color of mana by tapping.
_Avoid_: Mana producer, rock, dork

**Reading**:
What the service has worked out from a card's rules text: the mana it makes, its step triggers, its haste or vigilance, and whether it enters tapped.
_Avoid_: Parse, interpretation, card logic

**Rule check**:
A refusal based on card data that the agent can override with a stated reason.
_Avoid_: Validation, warning, soft error

**Change number**:
The count of accepted changes to a game, shown on every response and used to recognise a call that was sent twice.
_Avoid_: Sequence id, version, revision

**Player brief**:
The instructions that tell an agent how to play a goldfish game through the service's tools.
_Avoid_: Tester brief, prompt
