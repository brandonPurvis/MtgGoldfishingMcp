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
    # the seat to act
    NOT_YOUR_CALL = "not_your_call"
    NOT_ACCEPTED_NOW = "not_accepted_now"
    SEAT_ELIMINATED = "seat_eliminated"
    # naming cards
    CARD_NOT_IN_ZONE = "card_not_in_zone"
    TOO_FEW_MATCHING = "too_few_matching"
    INSTANCE_REPEATED = "instance_repeated"
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
    # play
    CARD_DATA_NEEDED = "card_data_needed"
    NOT_IN_LIBRARY = "not_in_library"
    WRONG_CHOICE = "wrong_choice"
    NOT_REVEALED = "not_revealed"
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
    DECK_SIZE = "deck_size"
    SINGLETON = "singleton"
    COLOR_IDENTITY = "color_identity"
    LEGALITY = "legality"
    COMMANDER_ELIGIBILITY = "commander_eligibility"


class AskedKind(Enum):
    """Why a seat is a seat to act: what the game is waiting for it to do."""

    KEEP = "keep"
    CHOICE = "choice"
    TURN = "turn"


@dataclass(frozen=True)
class Asked:
    """The seats a game is waiting on, in ascending seat number, and what they are asked.

    `choice` is the kind of the pending choice the seat must answer (`look`, `search`).
    """

    seats: tuple[SeatNumber, ...]
    kind: AskedKind
    choice: str | None = None


@dataclass(frozen=True)
class Error:
    """One error, with the facts its kind needs.

    `subject` is the card, argument or line concerned; `zone` and `found_in` are zone
    names; `names` lists several subjects or the accepted alternatives; `number` and
    `expected` carry counts; `asked` is what the seats to act are asked.
    """

    kind: ErrorKind
    subject: str | None = None
    zone: str | None = None
    found_in: str | None = None
    names: tuple[str, ...] = ()
    number: int | None = None
    expected: int | None = None
    asked: Asked | None = None


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
    mulligans: int
    hand: tuple[str, ...]


@dataclass(frozen=True)
class HandKept:
    bottomed: tuple[str, ...]
    hand: tuple[str, ...]


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
    card: str
    from_zone: str
    to: str
    commander_redirected: bool = False
    token_gone: bool = False


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
    change: int
    now: int


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
    choice_id: str
    kind: str
    cards: tuple[RevealedCard, ...]


@dataclass(frozen=True)
class NothingRevealed:
    kind: str


@dataclass(frozen=True)
class Placement:
    card: str
    to: str


@dataclass(frozen=True)
class ChoiceResolved:
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class AttackerDamage:
    attacker: str
    damage: int
    commander_target: int | None = None


@dataclass(frozen=True)
class AttackDeclared:
    attackers: tuple[str, ...]
    blocked: tuple[str, ...]
    commander_targets: tuple[tuple[str, int], ...]
    tapped: tuple[str, ...]


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


@dataclass(frozen=True)
class AdvanceStopped:
    reason: StopReason
    step: Step
    to: Step | None
    discard_count: int = 0


@dataclass(frozen=True)
class ExpectationMismatched:
    key: str
    actual: str
    expected: str


@dataclass(frozen=True)
class NoticeRaised:
    notice: NoticeKind


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
    | HandKept
    | CardPlayed
    | EffectRecorded
    | CostPaid
    | CardMoved
    | TokensCreated
    | CardsDrawn
    | HiddenCardsDrawn
    | CardsDiscarded
    | Tapped
    | Untapped
    | ManaAdded
    | CountersChanged
    | LifeChanged
    | DamageAdded
    | LibraryShuffled
    | AlreadySo
    | InstanceChosen
    | CardsRevealed
    | NothingRevealed
    | ChoiceResolved
    | AttackDeclared
    | CombatDamageDealt
    | AssumptionMade
    | ReminderIssued
    | AdvanceStopped
    | ExpectationMismatched
    | NoticeRaised
    | ChecksOverridden
    | GameEnded
    | AlreadyApplied
    | SnapshotWritten
    | StateListed
    | LogExported
    | Refused
)
