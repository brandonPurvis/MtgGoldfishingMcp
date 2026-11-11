"""Dependency injection: ports are abstract base classes, chosen only in the composition roots."""

from __future__ import annotations

import ast
import inspect
import tomllib
from abc import ABC
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.memory import (
    FixedClock,
    FixedIdSource,
    InMemoryCardCache,
    InMemoryCardCatalog,
    InMemoryDeckRepository,
    InMemoryGameRepository,
    InMemoryRecordStore,
    InMemoryStores,
    InMemoryUnitOfWork,
)
from mtg_goldfishing.adapters.scryfall import ScryfallCatalog
from mtg_goldfishing.adapters.sqlite import (
    SqliteCardCache,
    SqliteDeckRepository,
    SqliteGameRepository,
    SqliteRecordStore,
    SqliteUnitOfWork,
)
from mtg_goldfishing.adapters.system import (
    InProcessGameChanges,
    InProcessGameLocks,
    RandomIdSource,
    SystemClock,
)
from mtg_goldfishing.application import ports
from mtg_goldfishing.application.service import Service
from tests.application.test_failures import (
    CallRecordsCannotBeAdded,
    ChangedByAnotherWriter,
    SnapshotsCannotBeWritten,
)
from tests.application.test_game_order import (
    JournaledGames,
    JournaledLocks,
    JournaledRecords,
    SlowToLoad,
)
from tests.application.test_wait import (
    ImpatientChanges,
    JournaledChanges,
    JournaledUnitOfWork,
    WatchedChanges,
)
from tests.support.rendering import PlainRenderer
from tests.support.service import a_service

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mtg_goldfishing"

PORTS: tuple[type, ...] = (
    ports.GameRepository,
    ports.DeckRepository,
    ports.RecordStore,
    ports.CardCatalog,
    ports.CardCache,
    ports.UnitOfWork,
    ports.GameLocks,
    ports.IdSource,
    ports.Clock,
    ports.Renderer,
    ports.GameChanges,
)

OPERATIONS: dict[type, set[str]] = {
    ports.GameRepository: {"get", "find_seat", "add", "save"},
    ports.DeckRepository: {"get", "add"},
    ports.RecordStore: {"append_entry", "add_snapshot", "add_call", "read", "digest_baseline"},
    ports.CardCatalog: {"look_up"},
    ports.CardCache: {"get", "put"},
    ports.UnitOfWork: {"begin", "commit", "rollback"},
    ports.GameLocks: {"hold"},
    ports.IdSource: {"new_game_id", "new_seat_id", "new_seed"},
    ports.Clock: {"now"},
    ports.Renderer: {"render"},
    ports.GameChanges: {"announce", "wait_for_change"},
}

IMPLEMENTATIONS: tuple[tuple[type, type], ...] = (
    (SqliteGameRepository, ports.GameRepository),
    (SqliteDeckRepository, ports.DeckRepository),
    (SqliteRecordStore, ports.RecordStore),
    (SqliteUnitOfWork, ports.UnitOfWork),
    (SqliteCardCache, ports.CardCache),
    (ScryfallCatalog, ports.CardCatalog),
    (InProcessGameLocks, ports.GameLocks),
    (InProcessGameChanges, ports.GameChanges),
    (RandomIdSource, ports.IdSource),
    (SystemClock, ports.Clock),
    (TextRenderer, ports.Renderer),
    (InMemoryGameRepository, ports.GameRepository),
    (InMemoryDeckRepository, ports.DeckRepository),
    (InMemoryRecordStore, ports.RecordStore),
    (InMemoryUnitOfWork, ports.UnitOfWork),
    (InMemoryCardCache, ports.CardCache),
    (InMemoryCardCatalog, ports.CardCatalog),
    (FixedIdSource, ports.IdSource),
    (FixedClock, ports.Clock),
    (PlainRenderer, ports.Renderer),
    (ChangedByAnotherWriter, ports.GameRepository),
    (SlowToLoad, ports.GameRepository),
    (JournaledGames, ports.GameRepository),
    (SnapshotsCannotBeWritten, ports.RecordStore),
    (CallRecordsCannotBeAdded, ports.RecordStore),
    (JournaledRecords, ports.RecordStore),
    (JournaledLocks, ports.GameLocks),
    (ImpatientChanges, ports.GameChanges),
    (WatchedChanges, ports.GameChanges),
    (JournaledChanges, ports.GameChanges),
    (JournaledUnitOfWork, ports.UnitOfWork),
)
IMPLEMENTATION_IDS = [implementation.__name__ for implementation, _ in IMPLEMENTATIONS]

CONTAINER_LIBRARIES = (
    "dependency_injector",
    "injector",
    "punq",
    "lagom",
    "dishka",
    "wireup",
    "kink",
    "inject",
    "rodi",
    "svcs",
    "pinject",
    "that_depends",
)


def _named(classes: tuple[type, ...]) -> list[str]:
    return [cls.__name__ for cls in classes]


def _imported_modules(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


# ------------------------------------------------------------------ ports are abstract


# @spec APP-042
def test_every_class_the_ports_module_offers_for_implementing_is_a_known_port() -> None:
    value_objects = {ports.StoredGame, ports.SeatOfGame, ports.GameRecords, ports.Rendered}
    defined = {
        cls
        for _, cls in inspect.getmembers(ports, inspect.isclass)
        if cls.__module__ == ports.__name__
    }
    assert defined - value_objects == set(PORTS)


# @spec APP-042
@pytest.mark.parametrize("port", PORTS, ids=_named(PORTS))
def test_a_port_is_an_abstract_base_class(port: type) -> None:
    assert ABC in port.__mro__


# @spec APP-042
@pytest.mark.parametrize("port", PORTS, ids=_named(PORTS))
def test_every_operation_of_a_port_is_abstract(port: type) -> None:
    assert getattr(port, "__abstractmethods__", frozenset()) == OPERATIONS[port]


# @spec APP-043
@pytest.mark.parametrize(("implementation", "port"), IMPLEMENTATIONS, ids=IMPLEMENTATION_IDS)
def test_an_implementation_inherits_from_the_port_it_implements(
    implementation: type, port: type
) -> None:
    assert port in implementation.__mro__


# @spec APP-043
@pytest.mark.parametrize(
    "implementation",
    [implementation for implementation, _ in IMPLEMENTATIONS],
    ids=IMPLEMENTATION_IDS,
)
def test_an_implementation_is_a_concrete_class(implementation: type) -> None:
    assert not inspect.isabstract(implementation)


# @spec APP-044
@pytest.mark.parametrize("port", PORTS, ids=_named(PORTS))
def test_a_class_missing_an_operation_of_its_port_cannot_be_constructed(port: type) -> None:
    missing = min(OPERATIONS[port])
    kept = {name: lambda *_, **__: None for name in OPERATIONS[port] - {missing}}
    incomplete = type(f"Incomplete{port.__name__}", (port,), kept)

    with pytest.raises(TypeError, match=missing):
        incomplete()


# ------------------------------------------------------------------ injected, never looked up


# @spec APP-049
def test_the_service_takes_every_port_as_a_keyword_argument() -> None:
    parameters = list(inspect.signature(Service).parameters.values())
    assert parameters
    assert {parameter.kind for parameter in parameters} == {inspect.Parameter.KEYWORD_ONLY}


# @spec APP-049
def test_the_service_has_no_default_for_any_port() -> None:
    parameters = inspect.signature(Service).parameters.values()
    assert [p.name for p in parameters if p.default is not inspect.Parameter.empty] == []


# @spec APP-050
def test_no_application_module_imports_an_adapter() -> None:
    found = [
        f"{path.relative_to(SRC)} imports {imported}"
        for path in sorted((SRC / "application").rglob("*.py"))
        for imported in _imported_modules(path)
        if imported.startswith(("mtg_goldfishing.adapters", "mtg_goldfishing.bootstrap"))
    ]
    assert found == []


# @spec APP-050
def test_no_application_module_defines_an_implementation_of_a_port() -> None:
    port_names = set(_named(PORTS))
    found = []
    for path in sorted((SRC / "application").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {ast.unparse(base).rpartition(".")[2] for base in node.bases}
            if bases & port_names:
                found.append(f"{path.relative_to(SRC)} defines {node.name}")
    assert found == []


# @spec APP-051
def test_the_test_composition_root_builds_the_service_from_the_in_memory_adapters() -> None:
    harness = a_service()

    assert isinstance(harness.stores, InMemoryStores)
    assert isinstance(harness.catalog, InMemoryCardCatalog)
    assert isinstance(harness.ids, FixedIdSource)
    assert isinstance(harness.clock, FixedClock)
    assert isinstance(harness.locks, InProcessGameLocks)


# @spec APP-051
def test_bootstrap_is_the_only_source_module_that_imports_adapters_other_than_its_own() -> None:
    choosing = []
    for path in sorted(SRC.rglob("*.py")):
        own = path.relative_to(SRC).parts[:2]
        imported_adapters = {
            tuple(imported.split(".")[1:3])
            for imported in _imported_modules(path)
            if imported.startswith("mtg_goldfishing.adapters.")
        }
        if imported_adapters - {own}:
            choosing.append(path.relative_to(SRC).as_posix())
    assert choosing == ["bootstrap.py"]


# @spec APP-052
def test_the_project_depends_on_no_dependency_injection_container() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    required = [*project["project"]["dependencies"], *project["dependency-groups"]["dev"]]
    names = {
        requirement.split(">", 1)[0].split("=", 1)[0].split("[", 1)[0].strip().replace("-", "_")
        for requirement in required
    }
    assert names & set(CONTAINER_LIBRARIES) == set()


# @spec APP-052
def test_no_source_module_imports_a_dependency_injection_container() -> None:
    found = [
        f"{path.relative_to(SRC)} imports {imported}"
        for path in sorted(SRC.rglob("*.py"))
        for imported in _imported_modules(path)
        if imported.split(".", maxsplit=1)[0] in CONTAINER_LIBRARIES
    ]
    assert found == []


# ------------------------------------------------------------------ waking waiting seats


# @spec APP-041, APP-042
def test_game_changes_is_a_port_with_an_announce_and_a_wait_operation() -> None:
    assert ABC in ports.GameChanges.__mro__
    assert ports.GameChanges.__abstractmethods__ == {"announce", "wait_for_change"}


# @spec APP-048, APP-051
def test_the_test_composition_root_wakes_waiting_seats_with_the_in_process_game_changes() -> None:
    assert isinstance(a_service().changes, InProcessGameChanges)
