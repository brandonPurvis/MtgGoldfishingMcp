"""Builders that arrange games the way a test describes them.

situation = (
    a_game().with_battlefield("Forest", "Forest").with_hand("Cultivate").build()
)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.deck.model import DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game.model import CardInstance, Game, GameStatus, Zone
from mtg_goldfishing.domain.mana import Mana, ManaPool, ManaString
from mtg_goldfishing.domain.reading.model import CardReading
from mtg_goldfishing.domain.steps import Step
from tests.support.library import LIBRARY


@dataclass
class Situation:
    game: Game
    deck: LoadedDeck

    def named(self, name: str) -> CardInstance:
        """The lowest-id instance with this card name."""
        return next(c for c in sorted(self.game.cards, key=lambda c: c.number) if c.name == name)

    def ids_in(self, zone: Zone) -> list[str]:
        return [c.id for c in self.game.in_zone(zone)]

    def names_in(self, zone: Zone) -> list[str]:
        return [c.name for c in self.game.in_zone(zone)]


@dataclass
class _Placed:
    name: str
    zone: Zone
    tapped: bool = False
    entered_turn: int | None = None
    counters: dict[str, int] = field(default_factory=dict)
    is_commander: bool = False


class GameBuilder:
    def __init__(self) -> None:
        self._placed: list[_Placed] = []
        self._extra: dict[str, tuple[Card, CardReading]] = {}
        self._step: Step | None = Step.MAIN1
        self._turn = 3
        self._status = GameStatus.ACTIVE
        self._life = 40
        self._pool = ManaPool()
        self._seed = 7
        self._draw_first_turn = True
        self._turn_limit: int | None = None
        self._land_drops = 0

    def with_card(self, card: Card, reading: CardReading) -> GameBuilder:
        """Make a card outside the standard test library known to the deck."""
        self._extra[card.name] = (card, reading)
        return self

    def _place(self, names: tuple[str, ...], zone: Zone, **options: object) -> GameBuilder:
        for name in names:
            self._placed.append(_Placed(name, zone, **options))  # type: ignore[arg-type]
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
        self._life = life
        return self

    def with_pool(self, mana: str) -> GameBuilder:
        self._pool = ManaPool(tuple(Mana(k) for k in ManaString.parse(mana).produced()))
        return self

    def with_pool_units(self, *units: Mana) -> GameBuilder:
        self._pool = ManaPool(units)
        return self

    def with_land_drops_used(self, count: int) -> GameBuilder:
        self._land_drops = count
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

    def _known(self, name: str) -> tuple[Card, CardReading]:
        return self._extra.get(name) or LIBRARY[name]

    def build(self) -> Situation:
        ordered = [p for p in self._placed if p.is_commander] + [
            p for p in self._placed if not p.is_commander
        ]
        game = Game(
            game_id="gtest000001",
            deck_id="dtest",
            seed=self._seed,
            turn_limit=self._turn_limit,
            draw_first_turn=self._draw_first_turn,
            status=self._status,
            turn=self._turn,
            step=self._step,
            life=self._life,
            mana_pool=self._pool,
            land_drops_used=self._land_drops,
        )
        for placed in ordered:
            card = CardInstance(
                id=game.new_instance_id(),
                name=self._known(placed.name)[0].name,
                zone=placed.zone,
                tapped=placed.tapped,
                counters=dict(placed.counters),
                is_commander=placed.is_commander,
                entered_turn=placed.entered_turn if placed.zone is Zone.BATTLEFIELD else None,
            )
            game.cards.append(card)
            if placed.zone is Zone.LIBRARY:
                game.library.append(card.id)
            if placed.is_commander:
                game.commander_casts[card.id] = 0
                game.commander_damage[card.id] = [0, 0, 0]
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


def a_game() -> GameBuilder:
    return GameBuilder()
