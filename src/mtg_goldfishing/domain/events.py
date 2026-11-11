"""The facts every operation reports: events, errors and failed rule checks.

These are typed values. Nothing here is worded for a reader; the renderer in the MCP
adapter holds one wording per event type and per kind of error and rule check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import (
    EntersTappedReport,
    KeywordReport,
    ReadAbility,
    UnreadAbility,
)
from mtg_goldfishing.domain.steps import Step


class ErrorKind(Enum):
    """Structural impossibilities and malformed calls. Never overridable."""

    # games and status
    UNKNOWN_GAME = "unknown_game"
    NOT_ACCEPTED_IN_STATUS = "not_accepted_in_status"
    STALE_CHANGE = "stale_change"
    UNKNOWN_DECK = "unknown_deck"
    BAD_TURN_LIMIT = "bad_turn_limit"
    BAD_RESULT = "bad_result"
    TOO_MANY_OPPONENTS = "too_many_opponents"
    BAD_STARTING_LIFE = "bad_starting_life"
    BAD_POSITION = "bad_position"
    CONTESTED_ONLY = "contested_only"
    GOLDFISH_ONLY = "goldfish_only"
    # the seat to act
    NOT_YOUR_CALL = "not_your_call"
    NOT_ACCEPTED_NOW = "not_accepted_now"
    SEAT_ELIMINATED = "seat_eliminated"
    NOTHING_TO_PASS = "nothing_to_pass"
    ANSWER_WITH_CHOOSE = "answer_with_choose"
    WINDOW_OPEN = "window_open"
    # the stack
    NOT_ON_STACK = "not_on_stack"
    CARD_ON_STACK = "card_on_stack"
    ABILITY_HAS_NO_CARD = "ability_has_no_card"
    # seats named in a call
    NO_SUCH_SEAT = "no_such_seat"
    SEAT_OUT = "seat_out"
    # naming cards
    CARD_NOT_IN_ZONE = "card_not_in_zone"
    TOO_FEW_MATCHING = "too_few_matching"
    INSTANCE_REPEATED = "instance_repeated"
    HIDDEN_ZONE = "hidden_zone"
    # arguments
    MALFORMED_ARGUMENT = "malformed_argument"
    UNKNOWN_DELTA_KEY = "unknown_delta_key"
    UNKNOWN_EXPECT_KEY = "unknown_expect_key"
    UNPARSEABLE_MANA = "unparseable_mana"
    UNKNOWN_DESTINATION = "unknown_destination"
    UNKNOWN_ZONE = "unknown_zone"
    UNKNOWN_STEP = "unknown_step"
    LOOK_AND_SEARCH = "look_and_search"
    LOOK_WITHOUT_REST = "look_without_rest"
    TOO_MANY_REVEALS = "too_many_reveals"
    LOOK_AT_OWN_HAND = "look_at_own_hand"
    DAMAGE_NEEDS_SEATS = "damage_needs_seats"
    # play
    CARD_DATA_NEEDED = "card_data_needed"
    NOT_IN_LIBRARY = "not_in_library"
    WRONG_CHOICE = "wrong_choice"
    NOT_REVEALED = "not_revealed"
    WRONG_ANSWER = "wrong_answer"
    ANSWER_MAY_NOT_REVEAL = "answer_may_not_reveal"
    HAND_ANSWER_DELTA = "hand_answer_delta"
    SOURCE_MANA_UNKNOWN = "source_mana_unknown"
    SOURCE_TAPPED = "source_tapped"
    # mulligan and advance
    BOTTOM_NOT_IN_HAND = "bottom_not_in_hand"
    BOTTOM_WITHOUT_KEEP = "bottom_without_keep"
    DISCARD_NOT_IN_HAND = "discard_not_in_hand"
    DISCARD_WITHOUT_CLEANUP = "discard_without_cleanup"
    # combat
    ATTACKER_NOT_ON_BATTLEFIELD = "attacker_not_on_battlefield"
    NOT_AN_ATTACKER = "not_an_attacker"
    BAD_COMMANDER_TARGET = "bad_commander_target"
    NOT_YOUR_ATTACKER = "not_your_attacker"
    ATTACK_DECLARED = "attack_declared"
    ATTACK_AFTER_BLOCKERS = "attack_after_blockers"
    TARGET_IS_YOU = "target_is_you"
    NO_TARGET = "no_target"
    NO_OPPONENT_LEFT = "no_opponent_left"
    NOT_YOUR_BLOCKER = "not_your_blocker"
    NOT_ATTACKING_YOU = "not_attacking_you"
    # deck
    LINE_UNREADABLE = "line_unreadable"
    COUNT_NOT_POSITIVE = "count_not_positive"
    NO_COMMANDER = "no_commander"
    TOO_MANY_COMMANDERS = "too_many_commanders"
    COMMANDER_NOT_FOUND = "commander_not_found"
    CARDS_NOT_FOUND = "cards_not_found"
    CARD_DATA_UNAVAILABLE = "card_data_unavailable"
    DEFINITION_NOT_IN_DECK = "definition_not_in_deck"
    DEFINITION_NEEDS_TYPE_LINE = "definition_needs_type_line"
    # wait
    BAD_TIMEOUT = "bad_timeout"
    # the service itself
    CHANGED_UNDERNEATH = "changed_underneath"
    INTERNAL_FAILURE = "internal_failure"


class CheckKind(Enum):
    """Approximations from card data. Always overridable with a stated reason."""

    COST_NOT_PAYABLE = "cost_not_payable"
    LAND_DROP_USED = "land_drop_used"
    SPELL_TIMING = "spell_timing"
    LAND_TIMING = "land_timing"
    EXPLICIT_COST = "explicit_cost"
    SUMMONING_SICK_SOURCE = "summoning_sick_source"
    BOTTOM_COUNT = "bottom_count"
    HAND_TOO_BIG = "hand_too_big"
    DISCARD_COUNT = "discard_count"
    ATTACK_TOO_EARLY = "attack_too_early"
    COMBAT_OVER = "combat_over"
    NOT_A_CREATURE = "not_a_creature"
    ATTACKER_TAPPED = "attacker_tapped"
    SUMMONING_SICK_ATTACKER = "summoning_sick_attacker"
    POWER_NOT_A_NUMBER = "power_not_a_number"
    BLOCKER_TAPPED = "blocker_tapped"
    BLOCKER_NOT_A_CREATURE = "blocker_not_a_creature"
    DECK_SIZE = "deck_size"
    SINGLETON = "singleton"
    COLOR_IDENTITY = "color_identity"
    LEGALITY = "legality"
    COMMANDER_ELIGIBILITY = "commander_eligibility"


class AskedKind(Enum):
    """Why a seat is a seat to act: what the game is waiting for it to do."""

    KEEP = "keep"
    CHOICE = "choice"
    TRIGGER = "trigger"
    RESPOND = "respond"
    TURN = "turn"


@dataclass(frozen=True)
class Asked:
    """The seats a game is waiting on, in ascending seat number, and what they are asked.

    `choice` is the kind of the pending choice the seat must answer (`look`, `search`,
    `hand`, `ask`, `resolve`, `blocks`). A seat asked to respond is asked in a `window` of
    kind `stack`, `attack` or `end`, about the stack item `item` (its `source` and
    `controller`) when the stack is not empty. A seat asked for a trigger is reminded of
    `cards` in `step`.
    """

    seats: tuple[SeatNumber, ...]
    kind: AskedKind
    choice: str | None = None
    window: str | None = None
    item: str | None = None
    source: str | None = None
    controller: SeatNumber | None = None
    step: Step | None = None
    cards: tuple[str, ...] = ()


@dataclass(frozen=True)
class Error:
    """One error, with the facts its kind needs.

    `subject` is the card, argument or line concerned; `zone` and `found_in` are zone
    names; `names` lists several subjects or the accepted alternatives; `number` and
    `expected` carry counts, or a seat number; `asked` is what the seats to act are asked;
    `through_ask` adds, to an error about a delta's names in a contested game, that other
    seats' hands and libraries are reached through `ask`.
    """

    kind: ErrorKind
    subject: str | None = None
    zone: str | None = None
    found_in: str | None = None
    names: tuple[str, ...] = ()
    number: int | None = None
    expected: int | None = None
    asked: Asked | None = None
    through_ask: bool = False


@dataclass(frozen=True)
class FailedCheck:
    """One failed rule check, with the facts its kind needs."""

    kind: CheckKind
    subject: str | None = None
    names: tuple[str, ...] = ()
    cost: ManaString | None = None
    number: int | None = None
    expected: int | None = None
    step: Step | None = None


class NoticeKind(Enum):
    """End conditions the service watches for."""

    DAMAGE = "damage"
    COMMANDER_DAMAGE = "commander_damage"
    TURN_LIMIT = "turn_limit"
    LIFE = "life"
    EMPTY_LIBRARY = "empty_library"
    TESTED_SEAT_ELIMINATED = "tested_seat_eliminated"
    OPPONENTS_ELIMINATED = "opponents_eliminated"


# ---------------------------------------------------------------------------------------
# Events. Each is one kind of fact a call can report.
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EnteredStep:
    """A step entered. In a contested game `seat` names the active seat and `turn` is that
    seat's own turn count; in a goldfish game `seat` is None and `turn` the turn number."""

    turn: int
    step: Step
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class StepsEntered:
    steps: tuple[EnteredStep, ...]


@dataclass(frozen=True)
class DeckReport:
    """What `load_deck` tells about a loaded deck's definitions and readings, named by face.

    `definitions_applied` names the cards a card definition changed. The rest list mana
    abilities read with assumptions, mana abilities not read, mana abilities the auto
    payment system will not use on its own (they sacrifice or carry another cost), cards
    granting haste or vigilance, cards read as entering tapped, cards assumed to enter
    untapped, and haste, vigilance or flash readings made with assumptions. `not_refreshed`
    names the cards a refresh could not fetch again, whose cached data the deck was built from.
    """

    definitions_applied: tuple[str, ...] = ()
    read_with_assumptions: tuple[ReadAbility, ...] = ()
    unread: tuple[UnreadAbility, ...] = ()
    not_used_on_their_own: tuple[ReadAbility, ...] = ()
    granting_haste_or_vigilance: tuple[KeywordReport, ...] = ()
    enters_tapped: tuple[EntersTappedReport, ...] = ()
    assumed_untapped: tuple[EntersTappedReport, ...] = ()
    keywords_with_assumptions: tuple[KeywordReport, ...] = ()
    not_refreshed: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeckLoaded:
    deck_id: str
    card_count: int
    commanders: tuple[str, ...]
    already_loaded: bool = False
    report: DeckReport = DeckReport()


@dataclass(frozen=True)
class GameStarted:
    game_id: str
    seed: int
    hand: tuple[str, ...]


@dataclass(frozen=True)
class SeatStarted:
    """One seat of a new contested game, as whoever started the game is told of it."""

    number: SeatNumber
    seat_id: str
    deck_id: str
    life: int
    tested: bool


@dataclass(frozen=True)
class ContestedGameStarted:
    """A new contested game: its seats in turn order, and no seat's hand."""

    game_id: str
    seed: int
    seats: tuple[SeatStarted, ...]


@dataclass(frozen=True)
class MulliganTaken:
    """A mulligan taken: the seat's new hand. In a contested game `seat` names the seat."""

    mulligans: int
    hand: tuple[str, ...]
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class HiddenMulliganTaken:
    """The public form of a mulligan: which seat took it, and how many it has now taken."""

    seat: SeatNumber
    mulligans: int


@dataclass(frozen=True)
class HandKept:
    """A hand kept. In a contested game `seat` names the seat that kept it."""

    bottomed: tuple[str, ...]
    hand: tuple[str, ...]
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class HiddenHandKept:
    """The public form of a kept hand: the seat, how many cards it kept and how many it put
    on the bottom of its library."""

    seat: SeatNumber
    kept: int
    bottomed: int


@dataclass(frozen=True)
class CardPlayed:
    card: str
    face: str
    from_zone: str
    to: str
    is_land: bool


@dataclass(frozen=True)
class EffectRecorded:
    source: str


@dataclass(frozen=True)
class CostPaid:
    cost: ManaString
    tapped: tuple[str, ...] = ()
    sacrificed: tuple[str, ...] = ()
    life: int = 0
    from_pool: str = ""
    surplus: str = ""
    unpaid: bool = False


@dataclass(frozen=True)
class CardMoved:
    """A card moved. In a contested game `owner` names the seat that owns it, whose hand or
    library a move into or out of a hidden zone touches."""

    card: str
    from_zone: str
    to: str
    commander_redirected: bool = False
    token_gone: bool = False
    owner: SeatNumber | None = None


@dataclass(frozen=True)
class HiddenCardsMoved:
    """The public form of cards moved from one hidden zone of a seat to another without
    being revealed: whose zones, from where to where, and how many cards, not which."""

    seat: SeatNumber
    from_zone: str
    to: str
    count: int


@dataclass(frozen=True)
class TokensCreated:
    name: str
    count: int


@dataclass(frozen=True)
class CardsDrawn:
    """Cards drawn, named. In a contested game `seat` names the seat that drew them."""

    cards: tuple[str, ...]
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class HiddenCardsDrawn:
    """The public form of a draw: which seat drew, and how many cards, not which."""

    seat: SeatNumber
    count: int


@dataclass(frozen=True)
class CardsDiscarded:
    cards: tuple[str, ...]


@dataclass(frozen=True)
class Tapped:
    cards: tuple[str, ...]


@dataclass(frozen=True)
class Untapped:
    cards: tuple[str, ...]


@dataclass(frozen=True)
class ManaAdded:
    mana: str


@dataclass(frozen=True)
class CountersChanged:
    card: str
    kind: str
    change: int
    now: int


@dataclass(frozen=True)
class LifeChanged:
    """A seat's life changed by a delta. In a contested game `seat` names the seat."""

    change: int
    now: int
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class SeatDamaged:
    """Noncombat damage a delta dealt to a seat of a contested game, and its life after."""

    seat: SeatNumber
    amount: int
    life: int


@dataclass(frozen=True)
class ControlChanged:
    """A permanent that a delta gave to another seat's control."""

    card: str
    seat: SeatNumber


@dataclass(frozen=True)
class DamageAdded:
    amount: int
    total: int


@dataclass(frozen=True)
class LibraryShuffled:
    pass


class AlreadySoKind(Enum):
    ALREADY_TAPPED = "already_tapped"
    ALREADY_UNTAPPED = "already_untapped"
    COUNTER_AT_ZERO = "counter_at_zero"
    ALREADY_CONTROLLED = "already_controlled"


@dataclass(frozen=True)
class AlreadySo:
    """A requested change that was already so, applied as far as it could be."""

    card: str
    kind: AlreadySoKind
    counter: str | None = None


@dataclass(frozen=True)
class InstanceChosen:
    """Which of several differing instances a name was resolved to."""

    name: str
    instance_id: str


@dataclass(frozen=True)
class RevealedCard:
    instance_id: str
    name: str


@dataclass(frozen=True)
class CardsRevealed:
    """Cards revealed for a pending choice. In a contested game `seat` names the seat the
    choice is addressed to, the only seat shown the cards, and `hand_of` the seat whose hand
    a `hand` choice shows."""

    choice_id: str
    kind: str
    cards: tuple[RevealedCard, ...]
    seat: SeatNumber | None = None
    hand_of: SeatNumber | None = None


@dataclass(frozen=True)
class ChoiceRevealedTo:
    """The public form of a reveal: its kind, the seat it is addressed to and, for a look at
    a hand, whose hand; never the cards."""

    kind: str
    seat: SeatNumber
    hand_of: SeatNumber | None = None


@dataclass(frozen=True)
class ChoiceAsked:
    """A decision another seat's effect asks of a seat, as a pending choice for that seat."""

    choice_id: str
    seat: SeatNumber
    asked_by: SeatNumber
    text: str


@dataclass(frozen=True)
class NothingRevealed:
    kind: str


@dataclass(frozen=True)
class Placement:
    """Where a revealed card went. In a contested game `owner` names the seat that owns it,
    and `from_zone` is the zone it came from."""

    card: str
    to: str
    owner: SeatNumber | None = None
    from_zone: str = ""


@dataclass(frozen=True)
class ChoiceResolved:
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class AskAnswered:
    """A seat's answer to an `ask` pending choice; what its delta did follows it."""

    choice_id: str
    seat: SeatNumber


@dataclass(frozen=True)
class AttackerDamage:
    attacker: str
    damage: int
    commander_target: int | None = None


@dataclass(frozen=True)
class AttackDeclared:
    """An attack declared. In a contested game `targets` gives the seat each attacker attacks."""

    attackers: tuple[str, ...]
    blocked: tuple[str, ...]
    commander_targets: tuple[tuple[str, int], ...]
    tapped: tuple[str, ...]
    targets: tuple[tuple[str, SeatNumber], ...] = ()


@dataclass(frozen=True)
class BlocksRequested:
    """A `blocks` pending choice for an attacked seat, with the attackers attacking it."""

    choice_id: str
    seat: SeatNumber
    attackers: tuple[str, ...]


@dataclass(frozen=True)
class NoBlocksDeclared:
    """An attacked seat with no untapped creature, for which no blocks were declared."""

    seat: SeatNumber


@dataclass(frozen=True)
class BlockDeclared:
    """One blocker and the attacker it blocks, by name and by instance id."""

    blocker: str
    attacker: str
    blocker_id: str = ""
    attacker_id: str = ""


@dataclass(frozen=True)
class BlocksDeclared:
    """A seat's answer to its `blocks` choice."""

    seat: SeatNumber
    blocks: tuple[BlockDeclared, ...]


@dataclass(frozen=True)
class SeatHit:
    """One attacker's combat damage to the seat it attacks."""

    attacker: str
    damage: int
    seat: SeatNumber


@dataclass(frozen=True)
class DamagedSeat:
    """A seat dealt combat damage: its life after, and each commander's damage to it so far."""

    seat: SeatNumber
    life: int
    commander_damage: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class CombatDamageToSeats:
    """A contested game's combat damage: each attacker's hit and each damaged seat's totals."""

    hits: tuple[SeatHit, ...]
    seats: tuple[DamagedSeat, ...]


class EliminationCause(Enum):
    LIFE = "life"
    COMMANDER_DAMAGE = "commander_damage"
    CONCEDE = "concede"


@dataclass(frozen=True)
class SeatEliminated:
    """A seat that left a contested game, why, and a conceding seat's notes."""

    seat: SeatNumber
    cause: EliminationCause
    notes: str = ""


@dataclass(frozen=True)
class CombatDamageDealt:
    hits: tuple[AttackerDamage, ...]
    damage_total: int
    commander_damage: tuple[tuple[str, tuple[int, int, int]], ...]


class AssumptionKind(Enum):
    X_IS_ZERO = "x_is_zero"
    NO_MANA_COST = "no_mana_cost"
    SNOW_AS_GENERIC = "snow_as_generic"
    READING = "reading"


@dataclass(frozen=True)
class AssumptionMade:
    kind: AssumptionKind
    card: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class ReminderIssued:
    """Reminders of a step. In a contested game `seat` names the seat reminded."""

    step: Step
    cards: tuple[tuple[str, int], ...]
    seat: SeatNumber | None = None


class StopReason(Enum):
    REMINDER = "reminder"
    DISCARD = "discard"
    BLOCKS = "blocks"
    END_WINDOW = "end_window"


@dataclass(frozen=True)
class AdvanceStopped:
    """Why an advance stopped short of its target; for the end-step window, `seat` is the
    seat being asked."""

    reason: StopReason
    step: Step
    to: Step | None
    discard_count: int = 0
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class AttackNotDeclared:
    """An attack that stopped before declaring, in `step`, for another seat's reminder."""

    step: Step


@dataclass(frozen=True)
class ItemStacked:
    """A play or effect put on the stack as item `item`, of kind `spell` or `ability`."""

    item: str
    controller: SeatNumber
    source: str
    kind: str


@dataclass(frozen=True)
class Passed:
    """A seat's `pass`: on the stack item `item`, or in an `attack` or `end` window with an
    empty stack; or, with `reminder`, declining the reminders of `step`."""

    seat: SeatNumber
    item: str | None = None
    window: str | None = None
    reminder: bool = False
    step: Step | None = None


@dataclass(frozen=True)
class AutomaticPass:
    """A pass the service made for a seat with no untapped permanents, on the stack item
    `item`, or in the `attack` or `end` window when the stack is empty."""

    seat: SeatNumber
    item: str | None
    window: str


@dataclass(frozen=True)
class ItemResolved:
    """A stack item resolved: the delta applied (with what the service added under `added`)
    and where its card went (`to`), None for an ability."""

    item: str
    controller: SeatNumber
    source: str
    delta: dict[str, object]
    to: str | None


@dataclass(frozen=True)
class ItemCountered:
    """A stack item a delta's `counter` removed without applying its delta."""

    item: str
    controller: SeatNumber
    source: str


@dataclass(frozen=True)
class ItemRemoved:
    """A stack item that left the stack unresolved because a seat was eliminated or the
    game was ended."""

    item: str
    controller: SeatNumber
    source: str


@dataclass(frozen=True)
class ResolveAsked:
    """A `resolve` pending choice for the controller of stack item `item`: its held delta
    and destination, and the error that stops it resolving as held, if any."""

    choice_id: str
    seat: SeatNumber
    item: str
    source: str
    delta: dict[str, object]
    to: str | None
    error: Error | None = None


@dataclass(frozen=True)
class ExpectationMismatched:
    key: str
    actual: str
    expected: str


@dataclass(frozen=True)
class NoticeRaised:
    """A notice first raised. A contested game's empty library notice names its seat."""

    notice: NoticeKind
    seat: SeatNumber | None = None


@dataclass(frozen=True)
class ChecksOverridden:
    checks: tuple[FailedCheck, ...]
    reason: str


@dataclass(frozen=True)
class GameEnded:
    result: str
    notes: str


@dataclass(frozen=True)
class AlreadyApplied:
    """The call was a resend of the most recent change and was not applied again."""

    change: int


@dataclass(frozen=True)
class SeatToAct:
    """`wait`: the calling seat is a seat to act, and what it is asked."""

    asked: Asked


@dataclass(frozen=True)
class StillWaiting:
    """`wait` timed out: the seats the game is still waiting on and what they are asked, or
    None when it waits on no seat."""

    asked: Asked | None


@dataclass(frozen=True)
class SeatOut:
    """`wait`: the calling seat has been eliminated; nothing more is asked of it."""

    seat: SeatNumber


@dataclass(frozen=True)
class GameHasEnded:
    """`wait`: the game has ended."""


@dataclass(frozen=True)
class SnapshotWritten:
    turn: int


@dataclass(frozen=True)
class StateListed:
    """`get_state`: the listing is carried in the outcome's payload."""

    detail: str


@dataclass(frozen=True)
class LogExported:
    """`get_log`: the records are carried in the outcome's payload."""

    entries: int
    snapshots: int
    calls: int


@dataclass(frozen=True)
class Refused:
    """The headline of a refused call; the errors and failed checks follow."""

    errors: tuple[Error, ...]
    checks: tuple[FailedCheck, ...]


Event = (
    StepsEntered
    | DeckLoaded
    | GameStarted
    | ContestedGameStarted
    | MulliganTaken
    | HiddenMulliganTaken
    | HandKept
    | HiddenHandKept
    | CardPlayed
    | EffectRecorded
    | CostPaid
    | CardMoved
    | HiddenCardsMoved
    | TokensCreated
    | CardsDrawn
    | HiddenCardsDrawn
    | CardsDiscarded
    | Tapped
    | Untapped
    | ManaAdded
    | CountersChanged
    | LifeChanged
    | SeatDamaged
    | ControlChanged
    | DamageAdded
    | LibraryShuffled
    | AlreadySo
    | InstanceChosen
    | CardsRevealed
    | ChoiceRevealedTo
    | ChoiceAsked
    | NothingRevealed
    | ChoiceResolved
    | AskAnswered
    | AttackDeclared
    | BlocksRequested
    | NoBlocksDeclared
    | BlocksDeclared
    | CombatDamageDealt
    | CombatDamageToSeats
    | SeatEliminated
    | AssumptionMade
    | ReminderIssued
    | AdvanceStopped
    | AttackNotDeclared
    | ItemStacked
    | Passed
    | AutomaticPass
    | ItemResolved
    | ItemCountered
    | ItemRemoved
    | ResolveAsked
    | ExpectationMismatched
    | NoticeRaised
    | ChecksOverridden
    | GameEnded
    | AlreadyApplied
    | SeatToAct
    | StillWaiting
    | SeatOut
    | GameHasEnded
    | SnapshotWritten
    | StateListed
    | LogExported
    | Refused
)
