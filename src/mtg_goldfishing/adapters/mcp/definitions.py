"""The tools as an agent sees them: names, parameters and descriptions.

Each description states, in order: what the tool is for in one sentence; what the service
does automatically as a result; each parameter's meaning with one example value; and what
can be overridden. The shape of a delta is described once, under `play`; `effect` refers
to it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from mtg_goldfishing.adapters.mcp.parameters import Kind, Parameter

GAME_ID_EXAMPLE = "gq7k2m9x4pz"


@dataclass(frozen=True)
class ToolDefinition:
    """One tool: its name, the parts of its description, and its parameters in order."""

    name: str
    purpose: str
    automatic: str
    parameters: tuple[Parameter, ...]
    overridable: str

    def __post_init__(self) -> None:
        names = [parameter.name for parameter in self.parameters]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.name} names a parameter twice")

    @property
    def description(self) -> str:
        lines = [self.purpose, "", f"Automatically: {self.automatic}", "", "Parameters:"]
        lines.extend(_parameter_line(parameter) for parameter in self.parameters)
        lines.extend(["", f"Override: {self.overridable}"])
        return "\n".join(lines)

    @property
    def input_schema(self) -> dict[str, object]:
        """A schema for clients: the parameters in order with their JSON types.

        Nothing on the server validates against it; the adapter shapes arguments itself so
        that a call of the wrong shape is still answered in the response format.
        """
        return {
            "type": "object",
            "properties": {parameter.name: parameter.schema for parameter in self.parameters},
            "required": [parameter.name for parameter in self.parameters if parameter.required],
        }


def _parameter_line(parameter: Parameter) -> str:
    required = " (required)" if parameter.required else ""
    example = json.dumps(parameter.example, ensure_ascii=False)
    return f"- {parameter.name}{required}: {parameter.meaning} Example: {example}"


# @spec TOOL-031
def _game_id() -> Parameter:
    return Parameter(
        "game_id",
        Kind.TEXT,
        "The game id `new_game` returned. Contested games: your seat's seat id, the id"
        " `new_game` gave your seat (the tested seat's is the game id).",
        GAME_ID_EXAMPLE,
        required=True,
    )


def _after() -> Parameter:
    return Parameter(
        "after",
        Kind.WHOLE_NUMBER,
        "The change number at the end of the last status line you saw (`#41`). A call sent"
        " twice is then applied once, and a stale picture of the game is refused.",
        41,
    )


def _override(example: str) -> Parameter:
    return Parameter(
        "override",
        Kind.TEXT,
        "Your reason for applying the call although rule checks failed; it is recorded.",
        example,
    )


def _reason(example: str) -> Parameter:
    return Parameter(
        "reason",
        Kind.TEXT,
        "Why you made this choice, when it was not obvious; recorded in the log.",
        example,
    )


def _expect() -> Parameter:
    return Parameter(
        "expect",
        Kind.OBJECT,
        "Values you believe hold once the call is applied; each mismatch adds a warning line"
        " and the call is applied anyway. Keys: hand, lands, untapped_lands, life, pool,"
        " library, tax, damage_dealt, step.",
        {"untapped_lands": 2, "hand": 4},
    )


def _choices(example: object) -> Parameter:
    return Parameter(
        "choices",
        Kind.OBJECT,
        "What you announce while casting: x (the value of X), extra_cost (a mana string for"
        " kicker and the like, added to the cost), modes, targets and notes (recorded, never"
        " judged), definition (a card definition, for a card played from outside).",
        example,
    )


DELTA_SHAPE = (
    "Where things end up: an object whose keys are all optional and are applied in this"
    " order, whatever order you write them in. untap: [names]. tap: [names]. mana: a mana"
    ' string added to the mana pool ("{G}{G}"). tokens: [{name, count (default 1), types'
    ' ("Artifact — Treasure"), pt ("1/1" or null), produces (a mana string or a list of'
    " them, what it taps for), sacrifice_to_produce, tapped}]. counters: {name: {kind:"
    " signed change}}; a kind reaching 0 is removed. move: {destination: [names]}, cards"
    " from the hand or a public zone. commander_stays: true lets a commander go to the"
    " graveyard or exile instead of the command zone. discard: [names], hand to graveyard."
    " fetch: {destination: [names]}, cards taken from the library by name. draw: a number"
    " of cards. life: a signed change to your life. damage: noncombat damage to the"
    ' opponents, pooled (2 to each opponent is 6). shuffle: true. look: {n, from: "top"'
    ' or "bottom", rest: destination}, which reveals cards for a pending choice. search:'
    " {filter?}, which reveals the library sorted by name for a pending choice. A"
    " destination is hand, battlefield, battlefield_tapped, graveyard, exile, command,"
    " library_top or library_bottom. A card is named by its name, a face's name or an"
    " instance id; a name given twice means two cards. Contested games: a delta may tap,"
    " untap, put counters on and move other seats' cards in public zones, but never reach"
    " another seat's hand or library. control: {seat number: [names]}, permanents that seat"
    " now controls (applied after counters). life: {seat number: signed change} for any"
    " seat. damage: {seat number: damage}, never a single number. ask: [{seats: [seat"
    ' numbers] or "opponents", text}], what other seats must decide (a discard, a'
    " sacrifice); each answers with its own delta (applied after shuffle). look_at_hand: a"
    " seat number, which reveals that seat's hand to you for a pending choice. counter:"
    " [stack item ids or spell names], items on the stack countered."
)

PAY_SHAPE = (
    "How to pay: {with?: [a source's name, or {source, mana} to say what it makes this"
    " time], cost?: a mana string replacing the whole cost, life?: life paid as part of the"
    " cost}. Sources in `with` are used first and the auto payment system pays the rest;"
    " name a Treasure or other source that is sacrificed or costs more than tapping here,"
    " since the auto payment system never uses one."
)


LOAD_DECK = ToolDefinition(
    name="load_deck",
    purpose="Load a Commander deck list once and get a deck id to start games with.",
    automatic=(
        "Looks up every card's card data by exact name, applies your card definitions, runs"
        " the deck checks (size, singleton, color identity, legality, commander"
        " eligibility) and keeps the loaded deck. The response gives the deck id and what"
        " the service read from the cards: mana sources, step triggers, haste, vigilance and"
        " cards that enter tapped, with any assumption it made. The same list always gives"
        " the same deck id, and loading it again changes nothing."
    ),
    parameters=(
        Parameter(
            "cards",
            Kind.TEXT,
            "The deck list as text, one `<count> <name>` per line; lines starting with # or"
            " // are ignored and printing details such as `(C21) 263` are dropped.",
            "1 Sol Ring\n1 Cultivate\n36 Forest",
            required=True,
        ),
        Parameter(
            "commander",
            Kind.TEXT_OR_LIST,
            "The commander's name, or a list of two names for a pair of commanders.",
            "Atraxa, Praetors' Voice",
            required=True,
        ),
        Parameter(
            "definitions",
            Kind.LIST,
            "Card definitions, each replacing the fetched card data of one card in this deck"
            " field by field: name (required), face, mana_cost, type_line, oracle_text,"
            " power, toughness, color_identity, keywords, produces (what it taps for),"
            " enters_tapped. A card Scryfall does not know needs a type_line.",
            [{"name": "Mana Vault", "produces": "{C}{C}{C}"}],
        ),
        Parameter(
            "refresh",
            Kind.FLAG,
            "True to fetch card data again for every card instead of using the cache.",
            True,
        ),
        _override("testing a 99-card build on purpose"),
    ),
    overridable=(
        "Failed deck checks can be overridden with `override`. An unparseable line, a"
        " card name that cannot be resolved, or a missing commander is an error, which"
        " cannot."
    ),
)

NEW_GAME = ToolDefinition(
    name="new_game",
    purpose="Start a goldfish game on a loaded deck: shuffles and deals seven.",
    automatic=(
        "Puts the commander in the command zone, shuffles the rest into the library using"
        " the seed, and deals seven cards. The response gives the game id, the seed and the"
        " opening hand; the game then waits for `mulligan`."
    ),
    parameters=(
        Parameter(
            "deck_id",
            Kind.TEXT,
            "The deck id `load_deck` returned.",
            "df862a58edc",
            required=True,
        ),
        Parameter(
            "seed",
            Kind.WHOLE_NUMBER,
            "The number that fixes every shuffle: the same deck and seed give the same game."
            " The service chooses one and shows it when omitted.",
            1234,
        ),
        Parameter(
            "turn_limit",
            Kind.WHOLE_NUMBER,
            "The turn whose start raises a turn-limit notice; it never stops the game.",
            10,
        ),
        Parameter(
            "draw_first_turn",
            Kind.FLAG,
            "False to skip the draw on turn 1; true by default.",
            False,
        ),
        Parameter(
            "starting_life",
            Kind.WHOLE_NUMBER_OR_LIST,
            "Starting life of every seat; 40 by default. Contested games: a list gives the"
            " tested seat's and then each opposing seat's in `opponents` order.",
            40,
        ),
        Parameter(
            "opponents",
            Kind.LIST,
            "Contested games: the deck ids of one to three opposing seats, in order; a deck"
            " may appear more than once, and may be `deck_id` itself. The response then lists"
            " each seat in turn order with its seat number and seat id, which that seat's"
            " agent passes as `game_id`, and shows no hand. The seed also draws the turn order"
            " and `turn_limit` counts rounds.",
            ["d4fa52cf065"],
        ),
        Parameter(
            "position",
            Kind.WHOLE_NUMBER,
            "Contested games: the tested seat's place in turn order, from 1; the other seats"
            " are ordered by the seed. Omitted, the seed orders every seat.",
            1,
        ),
    ),
    overridable="Nothing; an unknown deck id is an error.",
)

MULLIGAN = ToolDefinition(
    name="mulligan",
    purpose="Keep the opening hand or take a mulligan.",
    automatic=(
        "With keep false, shuffles the hand into the library and deals seven new cards."
        " With keep true, puts the `bottom` cards on the bottom of the library in the order"
        " given (one card for each mulligan after the first, which is free), then starts the"
        " game and takes it through untap, upkeep and draw to turn 1's first main step,"
        " drawing a card unless the game was started without a first-turn draw. Contested"
        " games: each seat keeps or mulligans its own hand, and turn 1 begins once every seat"
        " has kept."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "keep",
            Kind.FLAG,
            "True to keep the hand, false to take a mulligan.",
            True,
        ),
        Parameter(
            "bottom",
            Kind.LIST,
            "When keeping after two or more mulligans, the cards from your hand to put on"
            " the bottom of the library, in order.",
            ["Island"],
        ),
        _override("the deck plays a free extra mulligan"),
        _after(),
    ),
    overridable=(
        "Keeping with the wrong number of `bottom` cards is a rule check that `override`"
        " passes. A `bottom` card not in your hand, or `bottom` with keep false, is an"
        " error."
    ),
)

# @spec TOOL-075, TOOL-098
GET_STATE = ToolDefinition(
    name="get_state",
    purpose=(
        "List the hand, battlefield and other zones when the status line is not enough,"
        " or give cards' rules text."
    ),
    automatic=(
        "Changes nothing. The summary lists the hand, the battlefield (each permanent with"
        " its instance id, tapped state, counters, the mana it makes, haste or vigilance and"
        " its step triggers), the graveyard, the command zone and notices; full adds exile,"
        " the number of cards in the library, each commander's casts and damage, and this"
        " turn's payments. The library's order is never shown. With `card`, the response"
        " gives the rules text of the cards named in place of the listing. Accepted in every"
        " game status. Contested games: shows every seat's battlefield, graveyard and command"
        " zone with its life and its hand and library sizes, the stack and who is asked; of"
        " the hands, only yours. It ends with the pending choices your seat owes, with the"
        " cards each reveals to you or what it asks of you."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "detail",
            Kind.TEXT,
            '"summary" (the default) or "full".',
            "full",
        ),
        Parameter(
            "card",
            Kind.TEXT_OR_LIST,
            "A card name or instance id, or a list of them: the response gives each card's"
            " rules text (each face's name, mana cost, type line, rules text, and power and"
            " toughness) in place of the listing, or a token's description. Only cards you"
            " may see are answered; ask for a card in your library by name. Not given"
            " together with detail.",
            ["Sol Ring", "c12"],
        ),
    ),
    overridable="Nothing; it changes nothing.",
)

# @spec TOOL-081, TOOL-082
PLAY = ToolDefinition(
    name="play",
    purpose="Play a land or cast a spell, stating what it does.",
    automatic=(
        "Finds the card (in your hand, then the command zone, unless `from` says otherwise)."
        " A land uses the turn's land drop. A spell's cost — its mana cost with X, any"
        " extra cost and commander tax — is paid by the auto payment system unless `pay`"
        " says how, and the response shows what was tapped. The card then goes to its"
        " destination: a permanent to the battlefield (tapped if it enters tapped), an"
        " instant or sorcery to the graveyard. The delta is applied last. A spell's"
        " `cast_triggers` are applied once its cost is paid, in the order listed, before the"
        " card moves; one that would look or search is recorded with `effect` after the play."
        " The library is shuffled after a fetch, a commander bound for the graveyard or exile"
        " goes to the command zone, and a token that leaves the battlefield ceases to exist."
        " Contested games: a spell goes on the stack with its cost paid, and resolves once"
        " every other seat has passed: only then does the card move and the delta apply. Its"
        " cast triggers go on the stack above the spell before any seat is asked, the first"
        " listed on top, so they resolve first; state them in the play itself, because a spell"
        " no other seat can answer resolves within the call, and a later effect would come"
        " after it. A land does not use the stack."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "card",
            Kind.TEXT,
            "The card to play: its name, a face's name, or an instance id.",
            "Cultivate",
            required=True,
        ),
        Parameter(
            "from",
            Kind.TEXT,
            "The zone it is played from: hand, command, graveyard, exile, library (found by"
            " name, nothing else disturbed) or outside (a card not in the game, looked up by"
            " name).",
            "graveyard",
        ),
        Parameter(
            "to",
            Kind.TEXT,
            "A destination for the card instead of its usual one, such as exile for a"
            " flashback spell.",
            "exile",
        ),
        Parameter(
            "delta",
            Kind.OBJECT,
            DELTA_SHAPE,
            {"fetch": {"battlefield_tapped": ["Plains"], "hand": ["Forest"]}},
        ),
        _choices({"x": 3}),
        Parameter(
            "pay",
            Kind.OBJECT,
            PAY_SHAPE,
            {"with": [{"source": "Birds of Paradise", "mana": "{U}"}]},
        ),
        Parameter(
            "cast_triggers",
            Kind.LIST,
            'Your own triggers on casting this spell ("whenever you cast an instant, copy it",'
            ' "when you cast this spell, draw a card"), each {source, delta, choices?}: source'
            " names what triggered, delta is what it does in the delta shape, and choices are"
            " recorded only. They resolve before the spell, in the order listed, the first"
            " listed first. A land is not cast and takes none; record a trigger on playing a"
            " land with effect.",
            [{"source": "Archmage Emeritus", "delta": {"draw": 1}}],
        ),
        _expect(),
        _reason("holding up Counterspell mana"),
        _override("Goblin Electromancer reduces the cost by {1}"),
        _after(),
    ),
    overridable=(
        "Rule checks — the cost is not payable, the land drop is used, a land or a card"
        " without flash is played outside a main step, `pay` gives its own cost, a"
        " summoning-sick creature is named in `pay` — are passed with `override`. An"
        " overridden unpayable cost is played unpaid, so tap what you used with the delta's"
        " tap. Errors — a card not in the zone named, an unknown delta key, a malformed mana"
        " string — cannot be overridden."
    ),
)

# @spec TOOL-069
EFFECT = ToolDefinition(
    name="effect",
    purpose="Record anything that happens without playing a card.",
    automatic=(
        "Pays `pay` if given (nothing is paid otherwise), then applies the delta with the"
        " same bookkeeping as `play`: the library is shuffled after a fetch, a commander"
        " bound for the graveyard or exile goes to the command zone, and a token that leaves"
        " the battlefield ceases to exist. When `source` names one of your permanents, the"
        " call answers that permanent's reminder. Contested games: the effect goes on the"
        " stack with its cost paid, and its delta is applied when it resolves, unless"
        " immediate."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "source",
            Kind.TEXT,
            "What is responsible: an ability, a trigger, an imagined opponent's spell.",
            "Phyrexian Arena",
            required=True,
        ),
        Parameter(
            "delta",
            Kind.OBJECT,
            "Where things end up, in the delta shape described under play.",
            {"draw": 1, "life": -1},
            required=True,
        ),
        _choices({"targets": ["opponent 2"]}),
        Parameter(
            "pay",
            Kind.OBJECT,
            "The ability's cost, in the pay shape described under play; here `cost` is"
            " simply the ability's cost and needs no override. Paid before the delta, so"
            " mana the delta adds cannot pay it.",
            {"cost": "{2}", "with": ["Sol Ring"]},
        ),
        _expect(),
        _reason("cracking the Treasure now to hold up removal"),
        _override("Concordant Crossroads gives the creature haste"),
        _after(),
        Parameter(
            "immediate",
            Kind.FLAG,
            "Contested games: true for an effect that is applied at once, such as the result"
            " of combat between creatures stated by the attacking seat once the game is in"
            " combat_damage. A combat result gives only what happens to the creatures: the"
            " service deals the declared attack's damage to seats on entering combat_damage,"
            " so a life or damage entry for that damage would be applied in addition to it.",
            True,
        ),
    ),
    overridable=(
        "Rule checks on paying — an unpayable cost, a summoning-sick creature named in"
        " `pay` — are passed with `override`. Errors — a card not where the delta looks for"
        " it, a malformed delta — cannot be overridden."
    ),
)

# @spec TOOL-077, TOOL-083
CHOOSE = ToolDefinition(
    name="choose",
    purpose="Finish a look or search by saying where the revealed cards go.",
    automatic=(
        "For a look, every revealed card you do not select goes to the look's rest"
        " destination, in `rest_order` or else in the order revealed. For a search,"
        " unselected cards stay in the library and it is shuffled before selected cards go"
        " to its top or bottom. Cards selected to library_top end with the first one named"
        " on top. Contested games: a choice addressed to your seat is answered by its kind —"
        " a look at another seat's hand with selections (the cards go to their owner's"
        " zones, the rest stay in that hand), an ask with your own delta, applied at once,"
        " and optionally `text`, the answer text (the card named, the guess, the number),"
        " which every seat is shown and which is recorded and never judged; it holds at most"
        " 200 characters and is accepted for no other kind of choice; blocks with blocks, and"
        " a resolve choice (a spell or ability that waited while"
        " something resolved above it, or whose stated delta can no longer be applied) with"
        " nothing to let it resolve as held, or with restate to say what it does now."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "choice_id",
            Kind.TEXT,
            "The choice id shown with the revealed cards.",
            "x1",
            required=True,
        ),
        Parameter(
            "selections",
            Kind.OBJECT,
            "Destinations mapped to revealed cards; {} selects nothing.",
            {"hand": ["Sol Ring"], "library_bottom": ["Island"]},
        ),
        Parameter(
            "rest_order",
            Kind.LIST,
            "For a look, the order in which the unselected cards go to the rest destination.",
            ["Forest", "Ponder"],
        ),
        _after(),
        Parameter(
            "delta",
            Kind.OBJECT,
            "Contested games: your answer to an ask, in the delta shape described under play,"
            " without ask, look_at_hand, look or search; omitted when you have nothing to do."
            " For a look at a hand, only control, for selected cards put onto the battlefield"
            " under a seat other than their owner.",
            {"discard": ["Island"]},
        ),
        Parameter(
            "text",
            Kind.TEXT,
            "Contested games: for an ask, the answer text: the card you name, your guess or"
            " your number, shown to every seat; at most 200 characters.",
            "Lightning Bolt",
        ),
        Parameter(
            "blocks",
            Kind.OBJECT,
            "Contested games: each of your blocking creatures mapped to the attacker it"
            " blocks; {} declares no blocks.",
            {"Llanowar Elves": "Grizzly Bears"},
        ),
        Parameter(
            "restate",
            Kind.OBJECT,
            "Contested games: for a resolve choice, the delta and destination the item"
            " resolves with in place of the held ones; one left out keeps the held value.",
            {"delta": {}, "to": "graveyard"},
        ),
        Parameter(
            "override",
            Kind.TEXT,
            "Contested games: your reason for declaring blocks although rule checks failed; it"
            " is recorded.",
            "the blocker untapped in response",
        ),
    ),
    overridable=(
        "Nothing; a wrong choice id or a card that was not revealed is an error. Contested"
        " games: a blocks answer fails a rule check that `override` passes when a blocker is"
        " tapped or is not a creature, or when the attacker's flying, horsemanship or can't be"
        " blocked forbids the block (flying lets only a creature with flying or reach block,"
        " horsemanship only a creature with horsemanship); a blocker that has flying or reach"
        " only for this turn blocks with an override giving that reason. An argument the"
        " choice's kind is not answered with is an error."
    ),
)

# @spec TOOL-070, TOOL-071, TOOL-076
ATTACK = ToolDefinition(
    name="attack",
    purpose="Declare attackers and which are blocked.",
    automatic=(
        "From the first main step or beginning of combat, moves the game on to declare"
        " attackers, listing beginning-of-combat reminders on the way. Taps each attacker"
        " that has no vigilance and keeps the declared attack. When `advance` enters the"
        " combat damage step, each unblocked attacker deals its power adjusted by its +1/+1"
        " and -1/-1 counters (or its `damage` entry) to the opponents, and an attacking"
        " commander's damage also counts as commander damage to its target opponent. An"
        " empty `attackers` clears the declared attack. Contested games: declaring attackers"
        " opens a window in which the other seats may respond; an attack may stop before"
        " attackers are declared, at a step where another seat has a reminder, and then"
        " nothing is declared or tapped: send attack again once your seat is the seat to act."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "attackers",
            Kind.LIST,
            "The attacking creatures by name or instance id; a name given twice is two creatures."
            " Contested games: not given in an attack that states trample damage.",
            ["Grizzly Bears", "Atraxa, Praetors' Voice"],
        ),
        Parameter(
            "blocked",
            Kind.LIST,
            "The attackers you decide the imaginary opponents block; they deal no damage.",
            ["Grizzly Bears"],
        ),
        Parameter(
            "commander_target",
            Kind.WHOLE_NUMBER_OR_OBJECT,
            "Which opponent (0, 1 or 2) an attacking commander attacks, 0 by default; with"
            " two attacking commanders, one number for both or {commander: number}.",
            1,
        ),
        Parameter(
            "damage",
            Kind.OBJECT,
            "Attackers mapped to the damage each deals instead of its power, for pumps,"
            " double strike or trample. Contested games: dealt only by an attacker that is not"
            " blocked; a blocked attacker's damage past its blockers is stated in trample.",
            {"Tarmogoyf": 5},
        ),
        Parameter(
            "vigilance",
            Kind.LIST,
            "Attackers with vigilance the service has not read; for this attack only.",
            ["Serra Angel"],
        ),
        Parameter(
            "haste",
            Kind.LIST,
            "Attackers with haste the service has not read; for this attack only.",
            ["Grizzly Bears"],
        ),
        _reason("holding back Birds of Paradise for mana"),
        _override("Craterhoof Behemoth gave everything haste"),
        _after(),
        Parameter(
            "targets",
            Kind.WHOLE_NUMBER_OR_OBJECT,
            "Contested games: the seat each attacker attacks, one seat number for all or"
            " {attacker: seat number}; needed with more than one opponent. Each attacked seat"
            " then declares its own blocks, so blocked and commander_target are not given.",
            {"Grizzly Bears": 2, "Shivan Dragon": 3},
        ),
        Parameter(
            "evasion",
            Kind.OBJECT,
            "Contested games: attackers mapped to the evasion each has beyond what the service"
            " has read, for this declaration only: flying, horsemanship or can't be blocked"
            " (unblockable), or a list of them, such as flying a spell gave it this turn. A"
            " block the attacker's evasion forbids is refused as a rule check.",
            {"Grizzly Bears": "flying"},
        ),
        Parameter(
            "trample",
            Kind.OBJECT,
            "Contested games: A blocked attacker deals no combat damage to the seat it attacks,"
            " its damage entry included, unless you state its trample damage here, once blocks"
            " are known and before combat damage, in an attack that gives trample and no"
            " attackers: each blocked attacker mapped to the combat damage it deals past its"
            " blockers. A later statement replaces the attackers it names; 0 takes one back.",
            {"Shivan Dragon": 3},
        ),
    ),
    overridable=(
        "Rule checks — an attacker that is not a creature, is tapped, or entered this turn"
        " without haste; a power that is not a number with no `damage` entry; attacking"
        " before the first main step, or after combat damage (an additional combat) — are"
        " passed with `override`. An attacker not on the battlefield, or a `blocked`,"
        " `damage`, `vigilance` or `haste` entry that is not among the attackers, is an"
        " error. Contested games: an `evasion` entry that is not among the attackers or not an"
        " evasion is an error; so is `trample` given with a declaration's arguments, before"
        " every blocks choice is answered, or for an attacker that is not blocked."
    ),
)

ADVANCE = ToolDefinition(
    name="advance",
    purpose="Move to the next step, or forward to a named step.",
    automatic=(
        "Does each step's automatic actions on the way: untaps in untap, draws in draw,"
        " deals the declared attack's damage in combat damage, discards and writes the turn"
        " snapshot in cleanup, and empties the mana pool on leaving every step. Stops early,"
        " with an OK response that says why, on entering a step where one of your permanents"
        " has a step trigger (a reminder: resolve it with `effect`, or pass it), or before"
        " cleanup with more than seven cards in hand. Send `advance` again to continue."
        " Contested games: also stops on entering end, where the other seats may respond, and"
        " where another seat has a reminder; it never goes past your cleanup, and the next"
        " seat's turn then goes on to its first main step."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "to",
            Kind.TEXT,
            "The step to move forward to, through its next occurrence (next turn's when the"
            " game is already in it): untap, upkeep, draw, main1, begin_combat,"
            " declare_attackers, declare_blockers, combat_damage, end_combat, main2, end,"
            " cleanup. Omitted, the game moves one step.",
            "main1",
        ),
        Parameter(
            "discard",
            Kind.LIST,
            "Cards in your hand to discard on entering cleanup: exactly as many as you hold"
            " over seven.",
            ["Island", "Forest"],
        ),
        _override("Reliquary Tower: no maximum hand size"),
        _after(),
    ),
    overridable=(
        "Entering cleanup with more than seven cards in hand and no `discard`, or a"
        " `discard` of the wrong number, is a rule check that `override` passes. An unknown"
        " step, a `discard` card not in your hand, or `discard` on an advance that does not"
        " enter cleanup is an error."
    ),
)

# @spec TOOL-032
PASS = ToolDefinition(
    name="pass",
    purpose="Decline to respond when your seat is asked (contested games).",
    automatic=(
        "Counts your seat as having passed and asks the next seat in turn order; once every"
        " other seat has passed in succession, the top item on the stack resolves, or an"
        " attack or end-step window closes. When the game waits on your seat for a reminder"
        " of a step trigger on another seat's turn, declines to record those triggers now."
    ),
    parameters=(_game_id(), _after()),
    overridable=(
        "Nothing. A pass in a goldfish game, from a seat that is not asked, from a seat that"
        " owes a pending choice, or from the active seat with no window open, is an error."
    ),
)

# @spec APP-072, APP-090, TOOL-099
WAIT = ToolDefinition(
    name="wait",
    purpose="Wait until your seat has something to do, then say what it is (contested games).",
    automatic=(
        "Changes nothing. Returns at once when your seat is the seat to act, has been"
        " eliminated, or the game has ended; otherwise holds the call until another seat's"
        " change makes it so, or the timeout passes, and then says who the game is still"
        " waiting on and for how long. Like every response to a seat, it begins with what"
        " the other seats did since your last call. In a goldfish game your seat is always"
        " the seat to act, so it returns at once. Contested games: an answer that says your"
        " seat is still waiting means only that the seat to act has not yet acted; call wait"
        " again."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "timeout",
            Kind.NUMBER,
            "Seconds to wait, from 1 to 60; 30 when omitted.",
            30,
        ),
    ),
    overridable="Nothing; it changes nothing. A timeout outside 1 to 60 is an error.",
)

END_GAME = ToolDefinition(
    name="end_game",
    purpose="End the game with a result and verdict.",
    automatic=(
        "Discards any pending choice and declared attack, writes the turn snapshot if this"
        " turn has none, and ends the game; afterwards only `get_state` and `get_log` are"
        " accepted. Contested games: only the tested seat ends the game; an opposing seat's"
        " end_game concedes, which eliminates it, and the game goes on."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "result",
            Kind.TEXT,
            "win, loss or stalled.",
            "win",
            required=True,
        ),
        Parameter(
            "notes",
            Kind.TEXT,
            "Your verdict: what the deck did well and what it did badly.",
            "Won on turn 8 with Craterhoof; the hand was short of green sources early.",
        ),
        _after(),
    ),
    overridable="Nothing; your result is trusted.",
)

GET_LOG = ToolDefinition(
    name="get_log",
    purpose="Return the game's records as JSON for analysis.",
    automatic=(
        "Changes nothing. Returns {game, entries, snapshots, calls}: the log entries of"
        " accepted changes with your choices and reasons, the turn snapshots, and the call"
        " records when asked for. Accepted in every game status. A call that cannot be"
        " answered is an ERROR in the text format, not JSON."
    ),
    parameters=(
        _game_id(),
        Parameter(
            "since",
            Kind.WHOLE_NUMBER,
            "Only records after this change number.",
            20,
        ),
        Parameter(
            "include_snapshots",
            Kind.FLAG,
            "False to leave the turn snapshots out; true by default.",
            False,
        ),
        Parameter(
            "include_calls",
            Kind.FLAG,
            "True to include the call records; false by default.",
            True,
        ),
    ),
    overridable="Nothing; it changes nothing.",
)

# @spec TOOL-007, TOOL-008, TOOL-009, TOOL-011, TOOL-033
TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    LOAD_DECK,
    NEW_GAME,
    MULLIGAN,
    GET_STATE,
    PLAY,
    EFFECT,
    CHOOSE,
    ATTACK,
    ADVANCE,
    PASS,
    WAIT,
    END_GAME,
    GET_LOG,
)
