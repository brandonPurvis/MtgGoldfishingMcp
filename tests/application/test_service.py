"""The service as a whole: built from the ports, one method per tool, a game played through it."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.memory import FixedClock, FixedIdSource
from mtg_goldfishing.adapters.memory.cards import InMemoryCardCatalog
from mtg_goldfishing.adapters.sqlite import SqliteStores
from mtg_goldfishing.adapters.system import InProcessGameLocks
from mtg_goldfishing.application import ports
from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.application.service import Service
from mtg_goldfishing.domain.events import DeckLoaded, ErrorKind, Refused
from mtg_goldfishing.domain.game.model import GameStatus
from tests.support.builders import a_game
from tests.support.card_data import recorded_cards
from tests.support.decks import ATRAXA, a_deck_list
from tests.support.rendering import PlainRenderer
from tests.support.service import GAME_ID, a_service

TOOLS = (
    "load_deck",
    "new_game",
    "mulligan",
    "get_state",
    "play",
    "effect",
    "choose",
    "attack",
    "advance",
    "end_game",
    "get_log",
)
PORTS = {
    "games": "GameRepository",
    "decks": "DeckRepository",
    "records": "RecordStore",
    "unit_of_work": "UnitOfWork",
    "catalog": "CardCatalog",
    "locks": "GameLocks",
    "ids": "IdSource",
    "clock": "Clock",
    "renderer": "Renderer",
}


# @spec APP-011
def test_the_service_is_built_from_the_application_s_ports() -> None:
    parameters = inspect.signature(Service.__init__, eval_str=True).parameters
    assert {
        name: parameter.annotation for name, parameter in parameters.items() if name != "self"
    } == {name: getattr(ports, port) for name, port in PORTS.items()}


@pytest.mark.parametrize("tool", TOOLS)
def test_the_service_answers_each_tool(tool: str) -> None:
    assert callable(getattr(Service, tool))


# @spec APP-028
def test_a_malformed_structured_argument_is_answered_as_an_error() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    answer = harness.service.effect({"game_id": GAME_ID, "source": "x", "delta": {"bogus": 1}})
    assert isinstance(answer.outcome.summary, Refused)
    assert answer.outcome.summary.errors[0].kind is ErrorKind.UNKNOWN_DELTA_KEY


@pytest.fixture
def sqlite_service(tmp_path: Path) -> Iterator[tuple[Service, SqliteStores]]:
    stores = SqliteStores.open(tmp_path / "goldfishing.db")
    try:
        yield (
            Service(
                games=stores.games,
                decks=stores.decks,
                records=stores.records,
                unit_of_work=stores.unit_of_work,
                catalog=InMemoryCardCatalog(recorded_cards()),
                locks=InProcessGameLocks(),
                ids=FixedIdSource(game_ids=["sqlite0001"], seeds=[31337]),
                clock=FixedClock(),
                renderer=PlainRenderer(),
            ),
            stores,
        )
    finally:
        stores.database.close()


# @spec APP-017, APP-019
def test_a_game_started_and_kept_over_sqlite_is_saved_with_its_records(
    sqlite_service: tuple[Service, SqliteStores],
) -> None:
    service, stores = sqlite_service
    loaded = service.load_deck({"cards": a_deck_list().text(), "commander": ATRAXA})
    assert isinstance(loaded.outcome.summary, DeckLoaded)
    service.new_game({"deck_id": loaded.outcome.summary.deck_id})
    kept = service.mulligan({"game_id": "gsqlite0001", "keep": True, "after": 1})
    assert kept.outcome.status is Status.OK
    stored = stores.games.get("gsqlite0001")
    assert stored is not None
    assert (stored.game.status, stored.game.change) == (GameStatus.ACTIVE, 2)
    records = stores.records.read("gsqlite0001")
    assert [e.tool for e in records.entries] == ["new_game", "mulligan"]
    assert [c.tool for c in records.calls] == ["new_game", "mulligan"]
