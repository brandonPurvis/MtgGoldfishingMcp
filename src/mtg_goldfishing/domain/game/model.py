"""The game aggregate: one goldfish game, its card instances, zones and counters.

`Game` is the one aggregate that changes. Operations never change the game they are given:
they work on a copy and return it only when the call is applied.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.events import Event, NoticeKind
from mtg_goldfishing.domain.mana import ManaPool, ManaString
from mtg_goldfishing.domain.reading.model import CardReading
from mtg_goldfishing.domain.steps import Step

STARTING_LIFE = 40
OPENING_HAND = 7
MAXIMUM_HAND = 7
OPPONENTS = 3
DAMAGE_TO_WIN = 120
COMMANDER_DAMAGE_TO_WIN = 21
COMMANDER_TAX = 2


class Zone(Enum):
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    COMMAND = "command"

    @classmethod
    def named(cls, name: str) -> Zone | None:
        try:
            return cls(name.strip().lower())
        except ValueError:
            return None


PUBLIC_ZONES = (Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND)


class Destination(Enum):
    """A place a delta can send a card."""

    HAND = "hand"
    BATTLEFIELD = "battlefield"
    BATTLEFIELD_TAPPED = "battlefield_tapped"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    COMMAND = "command"
    LIBRARY_TOP = "library_top"
    LIBRARY_BOTTOM = "library_bottom"

    @classmethod
    def named(cls, name: str) -> Destination | None:
        try:
            return cls(name.strip().lower())
        except ValueError:
            return None

    @property
    def zone(self) -> Zone:
        return {
            Destination.HAND: Zone.HAND,
            Destination.BATTLEFIELD: Zone.BATTLEFIELD,
            Destination.BATTLEFIELD_TAPPED: Zone.BATTLEFIELD,
            Destination.GRAVEYARD: Zone.GRAVEYARD,
            Destination.EXILE: Zone.EXILE,
            Destination.COMMAND: Zone.COMMAND,
            Destination.LIBRARY_TOP: Zone.LIBRARY,
            Destination.LIBRARY_BOTTOM: Zone.LIBRARY,
        }[self]


class GameStatus(Enum):
    MULLIGAN = "mulligan"
    ACTIVE = "active"
    PENDING_CHOICE = "pending_choice"
    ENDED = "ended"


class GameResult(Enum):
    WIN = "win"
    LOSS = "loss"
    STALLED = "stalled"


@dataclass(frozen=True)
class TokenSpec:
    """The agent's description of a token."""

    name: str
    types: str
    count: int = 1
    pt: str | None = None
    produces: tuple[ManaString, ...] = ()
    sacrifice_to_produce: bool = False
    tapped: bool = False

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("a token spec makes at least one token")

    @property
    def power(self) -> str | None:
        return self.pt.split("/")[0].strip() if self.pt and "/" in self.pt else None


@dataclass
class CardInstance:
    """One card or token in one game."""

    id: str
    name: str
    zone: Zone
    face: int = 0
    tapped: bool = False
    counters: dict[str, int] = field(default_factory=dict)
    is_token: bool = False
    is_commander: bool = False
    entered_turn: int | None = None
    token: TokenSpec | None = None
    definition: Card | None = None
    reading: CardReading | None = None

    @property
    def number(self) -> int:
        return int(self.id[1:])


@dataclass
class Attack:
    """The declared attack, by instance id."""

    attackers: list[str]
    blocked: list[str] = field(default_factory=list)
    damage: dict[str, int] = field(default_factory=dict)
    commander_targets: dict[str, int] = field(default_factory=dict)


@dataclass
class PendingChoice:
    choice_id: str
    source: str
    kind: str
    revealed: list[str]
    rest: Destination | None
    from_bottom: bool = False


@dataclass(frozen=True)
class PaymentRecord:
    """One payment made this turn: what it cost and how many mana symbols it took."""

    cost: ManaString
    mana_spent: int
    life: int = 0


@dataclass
class TurnStats:
    mana_available: int = 0
    mana_spent: int = 0
    payments: list[PaymentRecord] = field(default_factory=list)


@dataclass
class Reminder:
    """A reminder issued for one permanent this turn.

    `name` is the name of the permanent's face in play when reminded; `card_name` its card
    name, kept so the reminder can be answered after the permanent has left the battlefield.
    """

    instance_id: str
    name: str
    step: Step
    answered: bool = False
    card_name: str = ""


@dataclass
class LastChange:
    tool: str
    arguments: dict[str, object]
    summary: Event
    events: tuple[Event, ...]


@dataclass
class Result:
    outcome: GameResult
    notes: str


@dataclass
class Game:
    game_id: str
    deck_id: str
    seed: int
    turn_limit: int | None = None
    draw_first_turn: bool = True
    status: GameStatus = GameStatus.MULLIGAN
    turn: int = 0
    step: Step | None = None
    change: int = 0
    last_change: LastChange | None = None
    life: int = STARTING_LIFE
    land_drops_used: int = 0
    turn_stats: TurnStats = field(default_factory=TurnStats)
    mana_pool: ManaPool = field(default_factory=ManaPool)
    mulligans: int = 0
    shuffles: int = 0
    commander_casts: dict[str, int] = field(default_factory=dict)
    damage_dealt: int = 0
    commander_damage: dict[str, list[int]] = field(default_factory=dict)
    cards: list[CardInstance] = field(default_factory=list)
    library: list[str] = field(default_factory=list)
    declared_attack: Attack | None = None
    tapped_by_attacks: list[str] = field(default_factory=list)  # this turn; reset on untap
    pending_choice: PendingChoice | None = None
    notices: list[NoticeKind] = field(default_factory=list)
    result: Result | None = None
    reminders: list[Reminder] = field(default_factory=list)
    snapshot_turns: list[int] = field(default_factory=list)
    next_instance: int = 1
    next_choice: int = 1

    def copy(self) -> Game:
        return copy.deepcopy(self)

    # ------------------------------------------------------------------ looking things up

    def instance(self, instance_id: str) -> CardInstance:
        for card in self.cards:
            if card.id == instance_id:
                return card
        raise KeyError(instance_id)

    def find(self, instance_id: str) -> CardInstance | None:
        lowered = instance_id.strip().lower()
        return next((card for card in self.cards if card.id == lowered), None)

    def in_zone(self, zone: Zone) -> list[CardInstance]:
        if zone is Zone.LIBRARY:
            return [self.instance(instance_id) for instance_id in self.library]
        return sorted((c for c in self.cards if c.zone is zone), key=lambda c: c.number)

    @property
    def hand(self) -> list[CardInstance]:
        return self.in_zone(Zone.HAND)

    @property
    def battlefield(self) -> list[CardInstance]:
        return self.in_zone(Zone.BATTLEFIELD)

    @property
    def commanders(self) -> list[CardInstance]:
        """The commanders, in name order."""
        return sorted((c for c in self.cards if c.is_commander), key=lambda c: c.name.casefold())

    def commander_tax(self, commander: CardInstance) -> int:
        return COMMANDER_TAX * self.commander_casts.get(commander.id, 0)

    def new_instance_id(self) -> str:
        instance_id = f"c{self.next_instance}"
        self.next_instance += 1
        return instance_id

    def new_choice_id(self) -> str:
        choice_id = f"x{self.next_choice}"
        self.next_choice += 1
        return choice_id

    # ------------------------------------------------------------------ changing zones

    def take_from_library(self, instance_id: str) -> None:
        self.library.remove(instance_id)

    def put(self, card: CardInstance, destination: Destination, *, tapped: bool = False) -> None:
        """Put a card that is in no zone list into a destination, doing arrival bookkeeping."""
        card.zone = destination.zone
        if destination is Destination.LIBRARY_TOP:
            self.library.insert(0, card.id)
        elif destination is Destination.LIBRARY_BOTTOM:
            self.library.append(card.id)
        if card.zone is Zone.BATTLEFIELD:
            card.entered_turn = self.turn
            card.tapped = tapped or destination is Destination.BATTLEFIELD_TAPPED

    def remove_token(self, card: CardInstance) -> None:
        self.cards = [c for c in self.cards if c.id != card.id]


def arguments_without_after(arguments: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in arguments.items() if key != "after"}
