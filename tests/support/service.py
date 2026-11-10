"""The application's service over in-memory adapters, and ways to arrange and inspect it.

harness = a_service()
game_id = harness.holding(a_game().with_hand("Forest").build())
answer = harness.service.play({"game_id": game_id, "card": "Forest"})
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from mtg_goldfishing.adapters.memory import (
    FixedClock,
    FixedIdSource,
    InMemoryCardCatalog,
    InMemoryGameRepository,
    InMemoryRecordStore,
    InMemoryStores,
)
from mtg_goldfishing.adapters.system import InProcessGameLocks
from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.ports import (
    CardCatalog,
    GameLocks,
    GameRecords,
    GameRepository,
    RecordStore,
    Renderer,
)
from mtg_goldfishing.application.service import Service
from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import CallRecord
from tests.support.builders import Situation
from tests.support.card_data import recorded_cards
from tests.support.decks import ATRAXA, a_deck_list
from tests.support.rendering import PlainRenderer

GAME_ID = "gtest000001"


@dataclass
class ServiceHarness:
    """A service and the in-memory stores and adapters behind it."""

    service: Service
    stores: InMemoryStores
    catalog: CardCatalog
    locks: GameLocks
    ids: FixedIdSource
    clock: FixedClock

    def holding(self, situation: Situation, game_id: str = GAME_ID) -> str:
        """Store a built game and its deck, as if the game had been started earlier."""
        game = situation.game
        game.game_id = game_id
        self.stores.decks.add(situation.deck)
        self.stores.games.add(game)
        return game_id

    def game(self, game_id: str = GAME_ID) -> Game:
        stored = self.stores.games.get(game_id)
        assert stored is not None, f"no game {game_id}"
        return stored.game

    def version(self, game_id: str = GAME_ID) -> int:
        stored = self.stores.games.get(game_id)
        assert stored is not None, f"no game {game_id}"
        return stored.version

    def records(self, game_id: str = GAME_ID) -> GameRecords:
        return self.stores.records.read(game_id)

    def calls(self) -> tuple[CallRecord, ...]:
        """Every call record, whatever game it names."""
        return self.stores.records.calls()

    def last_call(self) -> CallRecord:
        return self.calls()[-1]

    def loaded_deck_id(self) -> str:
        """Load the standard test deck list through the service and return its id."""
        answer = self.service.load_deck({"cards": a_deck_list().text(), "commander": ATRAXA})
        summary = answer.outcome.summary
        deck_id = getattr(summary, "deck_id", None)
        assert isinstance(deck_id, str), answer
        return deck_id

    def started_game(self, **arguments: object) -> Answer:
        """Start a game on the standard test deck through the service."""
        return self.service.new_game({"deck_id": self.loaded_deck_id(), **arguments})


# @spec APP-051
def a_service(
    *,
    games: Callable[[InMemoryGameRepository], GameRepository] | None = None,
    records: Callable[[InMemoryRecordStore], RecordStore] | None = None,
    locks: GameLocks | None = None,
    renderer: Renderer | None = None,
    cards: Iterable[Card] | None = None,
    unavailable: Iterable[str] = (),
    game_ids: Iterable[str] = ("abcdefghij", "klmnopqrst", "uvwxyz0123"),
    seeds: Iterable[int] = (1234, 5678, 9012),
) -> ServiceHarness:
    """A service over in-memory adapters.

    `games` and `records` wrap the in-memory stores, for tests that need a store to
    misbehave; the unit of work still spans the stores underneath.
    """
    stores = InMemoryStores()
    catalog = InMemoryCardCatalog(recorded_cards() if cards is None else cards, unavailable)
    held = locks or InProcessGameLocks()
    ids = FixedIdSource(game_ids=game_ids, seeds=seeds)
    clock = FixedClock()
    service = Service(
        games=stores.games if games is None else games(stores.games),
        decks=stores.decks,
        records=stores.records if records is None else records(stores.records),
        unit_of_work=stores.unit_of_work,
        catalog=catalog,
        locks=held,
        ids=ids,
        clock=clock,
        renderer=renderer or PlainRenderer(),
    )
    return ServiceHarness(service, stores, catalog, held, ids, clock)
