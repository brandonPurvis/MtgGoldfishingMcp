"""Readings: what the service has worked out from a card face's rules text.

Every reading carries its assumptions, empty when the text matched a known form exactly.
Readings that depend on game state (counted amounts) are rules evaluated later by whoever
holds the state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from mtg_goldfishing.domain.mana import COLORS, ManaString, Restriction
from mtg_goldfishing.domain.steps import Step

# The assumptions the card reader states, worded as the card-reading design gives them.
IGNORES_ACTIVATION_CONDITION = "ignores activation condition"
IGNORES_CONDITIONAL_BONUS = "ignores conditional bonus"
RESTRICTION_NOT_UNDERSTOOD = "restriction not understood"
AMOUNT_ASSUMED_ONE = "amount assumed to be one"
ASSUMES_ANY_COLOR = "assumes any color"
ASSUMES_ONE_COLOR = "assumes one color for the whole amount"
ASSUMES_CONDITION_MET = "assumes its condition is met"
ASSUMES_UNTAPPED_PREFIX = "assumes it enters untapped: "


class AnyColorScope(Enum):
    """Which colors an any-color ability chooses among, when not a stated list."""

    ANY = "any"
    COMMANDER_IDENTITY = "commander_identity"


@dataclass(frozen=True)
class Fixed:
    """Always the same mana: `{G}`, `{C}{C}`, `{W}{U}`."""

    mana: ManaString


@dataclass(frozen=True)
class Choice:
    """One of several options: `{W} or {U}`."""

    options: tuple[ManaString, ...]

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError("a choice needs at least two options")


@dataclass(frozen=True)
class AnyColor:
    """`amount` mana of one color among a scope or a stated list of colors."""

    amount: int = 1
    among: AnyColorScope | tuple[str, ...] = AnyColorScope.ANY

    def __post_init__(self) -> None:
        if self.amount < 1:
            raise ValueError("an any-color ability makes at least one mana")
        if isinstance(self.among, tuple) and not (self.among and set(self.among) <= set(COLORS)):
            raise ValueError(f"not a list of colors: {self.among}")


@dataclass(frozen=True)
class PermanentsCount:
    """Permanents the controller has whose type line contains a word: `creature`, `Elf`."""

    match: str


@dataclass(frozen=True)
class DevotionCount:
    colors: tuple[str, ...]


@dataclass(frozen=True)
class CardsInHandCount:
    pass


@dataclass(frozen=True)
class CardsInGraveyardCount:
    match: str | None = None


@dataclass(frozen=True)
class CountersOnSelfCount:
    counter: str


Count = (
    PermanentsCount | DevotionCount | CardsInHandCount | CardsInGraveyardCount | CountersOnSelfCount
)


@dataclass(frozen=True)
class Counted:
    """`mana` (or one any-color mana) for each counted thing."""

    per: Count
    mana: ManaString | AnyColor


Produces = Fixed | Choice | AnyColor | Counted


@dataclass(frozen=True)
class ManaAbility:
    """One `<cost>: Add <mana>` ability, as read."""

    produces: Produces
    taps: bool = True
    mana_cost: ManaString = field(default_factory=ManaString)
    life: int = 0
    sacrifices: bool = False
    other_cost: str | None = None
    restriction: Restriction | None = None
    assumptions: tuple[str, ...] = ()
    text: str = ""

    @property
    def is_exact(self) -> bool:
        return not self.assumptions


@dataclass(frozen=True)
class KeywordGrant:
    """A standing grant of a keyword to creatures the controller has."""

    includes_self: bool = True
    subtype: str | None = None


@dataclass(frozen=True)
class KeywordReading:
    """Whether a face has a keyword itself, grants it to others, both, or neither."""

    own: bool = False
    grant: KeywordGrant | None = None
    assumptions: tuple[str, ...] = ()

    @property
    def present(self) -> bool:
        return self.own or self.grant is not None


NO_KEYWORD = KeywordReading()


@dataclass(frozen=True)
class EntersTappedReading:
    tapped: bool = False
    assumptions: tuple[str, ...] = ()


ENTERS_UNTAPPED = EntersTappedReading()


class Whose(Enum):
    """Whose turns a step trigger happens on."""

    CONTROLLER = "controller"
    EACH = "each"
    OPPONENTS = "opponents"


@dataclass(frozen=True)
class StepTrigger:
    """A beginning-of-step trigger: the step it belongs to and whose turns it happens on."""

    step: Step
    whose: Whose = Whose.CONTROLLER

    def on_turn_of(self, *, controller: bool) -> bool:
        """Whether the trigger happens on a turn that is, or is not, its controller's own."""
        if self.whose is Whose.EACH:
            return True
        return (self.whose is Whose.CONTROLLER) == controller


@dataclass(frozen=True)
class FaceReading:
    """Everything the card reader worked out from one face. `flying`, `horsemanship` and
    `cant_be_blocked` are the evasion the service checks on blocks; `reach` lets a blocker
    block a creature with flying."""

    mana_abilities: tuple[ManaAbility, ...] = ()
    unread_mana_abilities: tuple[str, ...] = ()
    step_triggers: tuple[StepTrigger, ...] = ()
    haste: KeywordReading = NO_KEYWORD
    vigilance: KeywordReading = NO_KEYWORD
    flash: KeywordReading = NO_KEYWORD
    enters_tapped: EntersTappedReading = ENTERS_UNTAPPED
    flying: KeywordReading = NO_KEYWORD
    horsemanship: KeywordReading = NO_KEYWORD
    reach: KeywordReading = NO_KEYWORD
    cant_be_blocked: KeywordReading = NO_KEYWORD

    @property
    def is_mana_source(self) -> bool:
        return bool(self.mana_abilities)


NO_READING = FaceReading()


@dataclass(frozen=True)
class CardReading:
    """The reading of each face of a card, in face order."""

    faces: tuple[FaceReading, ...]

    def face(self, index: int) -> FaceReading:
        return self.faces[index] if 0 <= index < len(self.faces) else NO_READING


@dataclass(frozen=True)
class ReadAbility:
    card: str
    ability: ManaAbility


@dataclass(frozen=True)
class UnreadAbility:
    card: str
    text: str


@dataclass(frozen=True)
class KeywordReport:
    card: str
    keyword: str
    reading: KeywordReading


@dataclass(frozen=True)
class EntersTappedReport:
    card: str
    reading: EntersTappedReading


@dataclass(frozen=True)
class ReadingReport:
    """What a caller can show about the readings of a set of cards."""

    read_exactly: tuple[ReadAbility, ...] = ()
    read_with_assumptions: tuple[ReadAbility, ...] = ()
    unread: tuple[UnreadAbility, ...] = ()
    step_triggers: tuple[tuple[str, Step], ...] = ()
    keywords: tuple[KeywordReport, ...] = ()
    enters_tapped: tuple[EntersTappedReport, ...] = ()
    assumed_untapped: tuple[EntersTappedReport, ...] = ()
    evasion_and_reach: tuple[KeywordReport, ...] = ()
