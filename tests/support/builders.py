"""Builders that arrange games the way a test describes them.

situation = (
    a_game().with_battlefield("Forest", "Forest").with_hand("Cultivate").build()
)

What a builder is told about cards, life, pool and land drops is the tested seat's, until
`and_an_opposing_seat()` adds a seat: from then on it is that seat's. A game with an
opposing seat has no imaginary opponents. Every seat plays the one deck the situation holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.deck.model import DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game.model import (
    OPPONENTS,
    CardInstance,
    Game,
    GameStatus,
    ImaginaryOpponents,
    Seat,
    Zone,
)
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.mana import Mana, ManaPool, ManaString
from mtg_goldfishing.domain.reading.model import CardReading
from mtg_goldfishing.domain.steps import Step
from tests.support.library import LIBRARY

TESTED = SeatNumber(1)
"""The tested seat, the only seat of a goldfish game."""


@dataclass
class Situation:
    game: Game
    deck: LoadedDeck

    def named(self, name: str) -> CardInstance:
        """The lowest-id instance with this card name."""
        return next(c for c in sorted(self.game.cards, key=lambda c: c.number) if c.name == name)

    def ids_in(self, zone: Zone, seat: SeatNumber = TESTED) -> list[str]:
        return [c.id for c in self.game.in_zone(zone, seat)]

    def names_in(self, zone: Zone, seat: SeatNumber = TESTED) -> list[str]:
        return [c.name for c in self.game.in_zone(zone, seat)]


@dataclass
class _Placed:
    name: str
    zone: Zone
    tapped: bool = False
    entered_turn: int | None = None
    counters: dict[str, int] = field(default_factory=dict)
    is_commander: bool = False


@dataclass
class _SeatPlan:
    """What one seat is built with."""

    placed: list[_Placed] = field(default_factory=list)
    life: int = 40
    pool: ManaPool = field(default_factory=ManaPool)
    land_drops: int = 0
    turns: int | None = None
    eliminated: bool = False
    kept: bool | None = None
    commander_damage: dict[str, dict[str, int]] = field(default_factory=dict)
    controlled: dict[str, int] = field(default_factory=dict)


class GameBuilder:
    def __init__(self) -> None:
        self._seats: list[_SeatPlan] = [_SeatPlan()]
        self._extra: dict[str, tuple[Card, CardReading]] = {}
        self._step: Step | None = Step.MAIN1
        self._turn = 3
        self._status = GameStatus.ACTIVE
        self._seed = 7
        self._draw_first_turn = True
        self._turn_limit: int | None = None
        self._active: int | None = None
        self._round: int | None = None

    @property
    def _seat(self) -> _SeatPlan:
        """The seat being described: the last one added."""
        return self._seats[-1]

    @property
    def _placed(self) -> list[_Placed]:
        return [placed for seat in self._seats for placed in seat.placed]

    def and_an_opposing_seat(self) -> GameBuilder:
        """Add an opposing seat, next in turn order; what follows describes it."""
        self._seats.append(_SeatPlan())
        return self

    def with_card(self, card: Card, reading: CardReading) -> GameBuilder:
        """Make a card outside the standard test library known to the deck."""
        self._extra[card.name] = (card, reading)
        return self

    def _place(self, names: tuple[str, ...], zone: Zone, **options: object) -> GameBuilder:
        for name in names:
            self._seat.placed.append(_Placed(name, zone, **options))  # type: ignore[arg-type]
        return self

    def with_commander(self, *names: str, zone: Zone = Zone.COMMAND) -> GameBuilder:
        return self._place(names, zone, is_commander=True)

    def with_hand(self, *names: str) -> GameBuilder:
        return self._place(names, Zone.HAND)

    def with_battlefield(
        self,
        *names: str,
        tapped: bool = False,
        entered_turn: int | None = 1,
        counters: dict[str, int] | None = None,
    ) -> GameBuilder:
        return self._place(
            names,
            Zone.BATTLEFIELD,
            tapped=tapped,
            entered_turn=entered_turn,
            counters=dict(counters or {}),
        )

    def with_graveyard(self, *names: str) -> GameBuilder:
        return self._place(names, Zone.GRAVEYARD)

    def with_exile(self, *names: str) -> GameBuilder:
        return self._place(names, Zone.EXILE)

    def with_library(self, *names: str) -> GameBuilder:
        """Library cards, top first."""
        return self._place(names, Zone.LIBRARY)

    def in_step(self, step: Step | None, turn: int | None = None) -> GameBuilder:
        self._step = step
        if turn is not None:
            self._turn = turn
        return self

    def in_mulligan(self) -> GameBuilder:
        self._status = GameStatus.MULLIGAN
        self._step = None
        self._turn = 0
        return self

    def with_status(self, status: GameStatus) -> GameBuilder:
        self._status = status
        return self

    def with_life(self, life: int) -> GameBuilder:
        self._seat.life = life
        return self

    def with_pool(self, mana: str) -> GameBuilder:
        self._seat.pool = ManaPool(tuple(Mana(k) for k in ManaString.parse(mana).produced()))
        return self

    def with_pool_units(self, *units: Mana) -> GameBuilder:
        self._seat.pool = ManaPool(units)
        return self

    def with_land_drops_used(self, count: int) -> GameBuilder:
        self._seat.land_drops = count
        return self

    def with_seed(self, seed: int) -> GameBuilder:
        self._seed = seed
        return self

    def without_first_turn_draw(self) -> GameBuilder:
        self._draw_first_turn = False
        return self

    def with_turn_limit(self, limit: int) -> GameBuilder:
        self._turn_limit = limit
        return self

    def in_turn_of(self, seat: int) -> GameBuilder:
        """Make the seat with this number the active seat (the tested seat's turn otherwise)."""
        self._active = seat
        return self

    def in_round(self, round_number: int) -> GameBuilder:
        """The game's round; the turn number otherwise."""
        self._round = round_number
        return self

    def with_turns_taken(self, turns: int) -> GameBuilder:
        """How many turns the seat being described has begun."""
        self._seat.turns = turns
        return self

    def eliminated(self) -> GameBuilder:
        """The seat being described has been eliminated."""
        self._seat.eliminated = True
        return self

    def having_kept(self, kept: bool = True) -> GameBuilder:
        """Whether the seat being described has kept its opening hand."""
        self._seat.kept = kept
        return self

    def with_commander_damage(self, commander: str, to_seat: int, damage: int) -> GameBuilder:
        """Combat damage the described seat's commander (by card name) has dealt another seat."""
        self._seat.commander_damage.setdefault(commander, {})[str(to_seat)] = damage
        return self

    def controlled_by(self, card: str, seat: int) -> GameBuilder:
        """A permanent the described seat owns is controlled by the seat with this number."""
        self._seat.controlled[card] = seat
        return self

    def _known(self, name: str) -> tuple[Card, CardReading]:
        return self._extra.get(name) or LIBRARY[name]

    def build(self) -> Situation:
        started = self._status is not GameStatus.MULLIGAN
        game = Game(
            game_id="gtest000001",
            seed=self._seed,
            seats=[],
            turn_limit=self._turn_limit,
            draw_first_turn=self._draw_first_turn,
            status=self._status,
            active=SeatNumber(self._active or 1) if started else None,
            turn=self._turn,
            round=self._turn if self._round is None else self._round,
            step=self._step,
        )
        for number, plan in enumerate(self._seats, start=1):
            game.seats.append(self._seat_of(game, number, plan, started))
        if len(game.seats) == 1:
            game.imaginary = ImaginaryOpponents(
                commander_damage={c.id: [0] * OPPONENTS for c in game.commanders_of(TESTED)}
            )
        names = sorted({p.name for p in self._placed})
        commanders = tuple(sorted({p.name for p in self._placed if p.is_commander}))
        counts: dict[str, int] = {}
        for placed in self._placed:
            if not placed.is_commander:
                counts[placed.name] = counts.get(placed.name, 0) + 1
        deck = LoadedDeck(
            deck_id="dtest",
            commanders=tuple(self._known(n)[0].name for n in commanders),
            entries=tuple(DeckEntry(self._known(n)[0].name, c) for n, c in sorted(counts.items())),
            cards=tuple(DeckCard(*self._known(n)) for n in names)
            + tuple(DeckCard(*v) for k, v in self._extra.items() if k not in names),
        )
        return Situation(game, deck)

    def _seat_of(self, game: Game, number: int, plan: _SeatPlan, started: bool) -> Seat:
        """A seat and its cards, numbered seat by seat: commanders first, then the rest."""
        tested = number == 1
        seat = Seat(
            number=SeatNumber(number),
            seat_id=SeatId(f"gtest{number:06d}"),
            deck_id="dtest",
            tested=tested,
            shuffle_key="" if tested else f"o{number - 1}",
            life=plan.life,
            eliminated=plan.eliminated,
            kept=started if plan.kept is None else plan.kept,
            turns=(self._turn if tested else 0) if plan.turns is None else plan.turns,
            land_drops_used=plan.land_drops,
            mana_pool=plan.pool,
        )
        ordered = [p for p in plan.placed if p.is_commander] + [
            p for p in plan.placed if not p.is_commander
        ]
        for placed in ordered:
            card = CardInstance(
                id=game.new_instance_id(),
                name=self._known(placed.name)[0].name,
                zone=placed.zone,
                owner=seat.number,
                controller=seat.number,
                tapped=placed.tapped,
                counters=dict(placed.counters),
                is_commander=placed.is_commander,
                entered_turn=placed.entered_turn if placed.zone is Zone.BATTLEFIELD else None,
            )
            game.cards.append(card)
            if placed.zone is Zone.LIBRARY:
                seat.library.append(card.id)
            if placed.is_commander:
                seat.commander_casts[card.id] = 0
            if placed.zone is Zone.BATTLEFIELD and card.name in plan.controlled:
                card.controller = SeatNumber(plan.controlled[card.name])
        if plan.commander_damage:
            commanders = {
                c.name: c.id for c in game.cards if c.is_commander and c.owner == seat.number
            }
            seat.commander_damage = {
                commanders[name]: dict(damage) for name, damage in plan.commander_damage.items()
            }
        return seat


def a_game() -> GameBuilder:

    return GameBuilder()


def a_deck(*names: str, commanders: tuple[str, ...] = ("Atraxa, Praetors' Voice",)) -> LoadedDeck:
    """A loaded deck of library cards; a name given several times is that many copies."""
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    distinct = sorted(set(names) | set(commanders))
    return LoadedDeck(
        deck_id="dtest",
        commanders=commanders,
        entries=tuple(DeckEntry(n, c) for n, c in sorted(counts.items())),
        cards=tuple(DeckCard(*LIBRARY[n]) for n in distinct),
    )
