"""The game aggregate: the table, its seats, their card instances and zones.

`Game` is the one aggregate that changes. A `Seat` is an entity inside it, reached through
the game by its seat number. Operations never change the game they are given: they work on a
copy and return it only when the call is applied.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.events import Event, NoticeKind
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
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
HIDDEN_ZONES = (Zone.HAND, Zone.LIBRARY)


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
    """One card or token in one game.

    Its owner is the seat whose deck it came from or whose effect created it; its controller
    is its owner unless an effect has changed control.
    """

    id: str
    name: str
    zone: Zone
    owner: SeatNumber
    controller: SeatNumber
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

    @property
    def zone_seat(self) -> SeatNumber:
        """The seat whose zone the card is in: its controller on the battlefield, else its owner."""
        return self.controller if self.zone is Zone.BATTLEFIELD else self.owner


@dataclass
class Attack:
    """The declared attack, by instance id.

    In a contested game `targets` maps each attacker to the seat number it attacks, and
    `blocks` each blocker to the attacker it blocks; a goldfish game's commanders attack the
    imaginary opponents in `commander_targets`.
    """

    attackers: list[str]
    blocked: list[str] = field(default_factory=list)
    damage: dict[str, int] = field(default_factory=dict)
    commander_targets: dict[str, int] = field(default_factory=dict)
    targets: dict[str, int] = field(default_factory=dict)
    blocks: dict[str, str] = field(default_factory=dict)


@dataclass
class PendingChoice:
    """A decision the game waits on from one seat: `seat` is the seat that answers it.

    Its `kind` is `look`, `search`, `hand`, `ask` or `blocks`.

    `revealed` holds the cards a look, a search or a look at a hand shows; `asked_by` is the
    seat whose effect asked (for a `hand` choice, the looking seat), `hand_of` the seat whose
    hand a `hand` choice shows, `text` what an `ask` requires, and `attackers` the attackers
    a `blocks` choice may block.
    """

    choice_id: str
    seat: SeatNumber
    source: str
    kind: str
    revealed: list[str]
    rest: Destination | None
    from_bottom: bool = False
    asked_by: SeatNumber | None = None
    hand_of: SeatNumber | None = None
    text: str = ""
    attackers: list[str] = field(default_factory=list)


@dataclass
class HandLook:
    """A look at a seat's hand that waits for the asks of the same delta to be answered, so
    that it shows the hand those answers left."""

    seat: SeatNumber
    hand_of: SeatNumber
    source: str


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
    """A reminder issued for one permanent.

    `name` is the name of the permanent's face in play when reminded; `card_name` its card
    name, kept so the reminder can be answered after the permanent has left the battlefield;
    `turn` the table turn it was issued in, within which it may be answered.
    """

    instance_id: str
    name: str
    step: Step
    answered: bool = False
    card_name: str = ""
    turn: int = 0


@dataclass
class LastChange:
    """A seat's most recent accepted change, and the change number it took."""

    tool: str
    arguments: dict[str, object]
    summary: Event
    events: tuple[Event, ...]
    change: int


@dataclass
class Result:
    outcome: GameResult
    notes: str


# @spec GAME-061, PAY-044
@dataclass
class Seat:
    """One player's place in a game: what that player has, apart from its cards.

    The seat's cards are the game's card instances it owns; its library's order is kept here.
    """

    number: SeatNumber
    seat_id: SeatId
    deck_id: str
    tested: bool
    shuffle_key: str = ""
    life: int = STARTING_LIFE
    starting_life: int = STARTING_LIFE
    eliminated: bool = False
    kept: bool = False
    mulligans: int = 0
    shuffles: int = 0
    turns: int = 0
    land_drops_used: int = 0
    turn_stats: TurnStats = field(default_factory=TurnStats)
    mana_pool: ManaPool = field(default_factory=ManaPool)
    commander_casts: dict[str, int] = field(default_factory=dict)
    commander_damage: dict[str, dict[str, int]] = field(default_factory=dict)
    """Combat damage each of this seat's commanders (by instance id) has dealt to each other
    seat (by seat number, as text) of a contested game."""
    library: list[str] = field(default_factory=list)
    last_change: LastChange | None = None
    reminders: list[Reminder] = field(default_factory=list)
    notices: list[NoticeKind] = field(default_factory=list)
    """The notices that are this seat's own: in a contested game, its empty library notice."""

    def commander_tax(self, commander: CardInstance) -> int:
        return COMMANDER_TAX * self.commander_casts.get(commander.id, 0)

    def commander_damage_to(self, commander: CardInstance, seat: SeatNumber) -> int:
        """The combat damage one of this seat's commanders has dealt to another seat."""
        return self.commander_damage.get(commander.id, {}).get(str(seat.value), 0)

    @property
    def in_game(self) -> bool:
        """Whether the seat is still in the game: not eliminated."""
        return not self.eliminated


@dataclass
class ImaginaryOpponents:
    """What a goldfish game keeps for its tested seat against the three imaginary opponents."""

    damage_dealt: int = 0
    commander_damage: dict[str, list[int]] = field(default_factory=dict)


# @spec APP-030, GAME-100
@dataclass
class Game:
    """The table: what every seat shares, the seats in turn order, and every seat's cards.

    `imaginary` holds a goldfish game's tallies; a game with opposing seats has none.
    """

    game_id: str
    seed: int
    seats: list[Seat]
    turn_limit: int | None = None
    draw_first_turn: bool = True
    status: GameStatus = GameStatus.MULLIGAN
    active: SeatNumber | None = None
    turn: int = 0
    round: int = 0
    step: Step | None = None
    change: int = 0
    pending: list[PendingChoice] = field(default_factory=list)
    hand_looks: list[HandLook] = field(default_factory=list)
    declared_attack: Attack | None = None
    tapped_by_attacks: list[str] = field(default_factory=list)  # this turn; reset on untap
    notices: list[NoticeKind] = field(default_factory=list)
    result: Result | None = None
    cards: list[CardInstance] = field(default_factory=list)
    imaginary: ImaginaryOpponents | None = None
    snapshot_turns: list[int] = field(default_factory=list)
    next_instance: int = 1
    next_choice: int = 1

    def copy(self) -> Game:
        return copy.deepcopy(self)

    @property
    def contested(self) -> bool:
        """Whether the game has opposing seats; a goldfish game has imaginary opponents."""
        return self.imaginary is None

    # ------------------------------------------------------------------ seats

    def seat(self, number: SeatNumber) -> Seat:
        for seat in self.seats:
            if seat.number == number:
                return seat
        raise KeyError(number)

    def others_from(self, number: SeatNumber) -> list[Seat]:
        """Every other seat, in turn order starting from the seat after `number`."""
        at = next(i for i, seat in enumerate(self.seats) if seat.number == number)
        return self.seats[at + 1 :] + self.seats[:at]

    @property
    def tested(self) -> Seat:
        """The seat whose deck the game is judging."""
        return next(seat for seat in self.seats if seat.tested)

    @property
    def active_seat(self) -> Seat:
        """The seat whose turn it is; asking while no seat is active is a defect."""
        if self.active is None:
            raise LookupError("no seat is active")
        return self.seat(self.active)

    @property
    def imaginary_opponents(self) -> ImaginaryOpponents:
        """A goldfish game's tallies; asking a game with opposing seats for them is a defect."""
        if self.imaginary is None:
            raise LookupError("only a goldfish game has imaginary opponents")
        return self.imaginary

    @property
    def waiting_choice(self) -> PendingChoice | None:
        """The pending choice to be answered next: the oldest still waiting."""
        return self.pending[0] if self.pending else None

    # ------------------------------------------------------------------ looking things up

    def instance(self, instance_id: str) -> CardInstance:
        for card in self.cards:
            if card.id == instance_id:
                return card
        raise KeyError(instance_id)

    def find(self, instance_id: str) -> CardInstance | None:
        lowered = instance_id.strip().lower()
        return next((card for card in self.cards if card.id == lowered), None)

    def in_zone(self, zone: Zone, seat: SeatNumber) -> list[CardInstance]:
        """A seat's cards in a zone: the permanents it controls, elsewhere the cards it owns.

        The library is in its own order, top first; every other zone in instance order.
        """
        if zone is Zone.LIBRARY:
            return [self.instance(instance_id) for instance_id in self.seat(seat).library]
        return sorted(
            (c for c in self.cards if c.zone is zone and c.zone_seat == seat),
            key=lambda c: c.number,
        )

    def hand_of(self, seat: SeatNumber) -> list[CardInstance]:
        return self.in_zone(Zone.HAND, seat)

    def battlefield_of(self, seat: SeatNumber) -> list[CardInstance]:
        """The permanents a seat controls, whichever seat owns them."""
        return self.in_zone(Zone.BATTLEFIELD, seat)

    def commanders_of(self, seat: SeatNumber) -> list[CardInstance]:
        """A seat's own commanders, in name order."""
        return sorted(
            (c for c in self.cards if c.is_commander and c.owner == seat),
            key=lambda c: c.name.casefold(),
        )

    # @spec GAME-064
    def new_instance_id(self) -> str:
        """The next instance id of the game, counted across every seat and never reused."""
        instance_id = f"c{self.next_instance}"
        self.next_instance += 1
        return instance_id

    def new_choice_id(self) -> str:
        choice_id = f"x{self.next_choice}"
        self.next_choice += 1
        return choice_id

    # ------------------------------------------------------------------ changing zones

    def take_from_library(self, card: CardInstance) -> None:
        self.seat(card.owner).library.remove(card.id)

    def put(self, card: CardInstance, destination: Destination, *, tapped: bool = False) -> None:
        """Put a card that is in no zone list into a destination, doing arrival bookkeeping.

        A card bound for a library goes to its owner's.
        """
        card.zone = destination.zone
        library = self.seat(card.owner).library
        if destination is Destination.LIBRARY_TOP:
            library.insert(0, card.id)
        elif destination is Destination.LIBRARY_BOTTOM:
            library.append(card.id)
        if card.zone is Zone.BATTLEFIELD:
            card.entered_turn = self.turn
            card.tapped = tapped or destination is Destination.BATTLEFIELD_TAPPED

    def remove_token(self, card: CardInstance) -> None:
        self.cards = [c for c in self.cards if c.id != card.id]


def arguments_without_after(arguments: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in arguments.items() if key != "after"}
