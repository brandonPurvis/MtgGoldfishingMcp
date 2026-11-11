"""The composition root: reads the settings, wires the adapters to the service, and serves it.

This is the one module that imports adapters from more than one ring of the outside: the
SQLite stores, the Scryfall card catalog over the SQLite card cache, in-process game locks
and game change announcements,
the system's randomness and clock, the text renderer, and the MCP adapter that serves it
all over HTTP.

    uv run mtg-goldfishing

| Setting              | Environment variable   | Default                        |
|----------------------|------------------------|--------------------------------|
| Address to listen on | MTG_GOLDFISHING_HOST   | 127.0.0.1                      |
| Port                 | MTG_GOLDFISHING_PORT   | 8000                           |
| Database file        | MTG_GOLDFISHING_DB     | data/mtg-goldfishing.sqlite3   |
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from mtg_goldfishing.adapters.mcp.app import create_app
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.scryfall import ScryfallCatalog
from mtg_goldfishing.adapters.sqlite import SchemaTooNew, SqliteStores
from mtg_goldfishing.adapters.system import (
    InProcessGameChanges,
    InProcessGameLocks,
    RandomIdSource,
    SystemClock,
)
from mtg_goldfishing.application.ports import CardCatalog, GameChanges
from mtg_goldfishing.application.service import Service

HOST_VARIABLE = "MTG_GOLDFISHING_HOST"
PORT_VARIABLE = "MTG_GOLDFISHING_PORT"
DATABASE_VARIABLE = "MTG_GOLDFISHING_DB"
HIGHEST_PORT = 65535


@dataclass(frozen=True)
class Settings:
    """Where the service listens and where it keeps its database."""

    host: str = "127.0.0.1"
    port: int = 8000
    database: Path = Path("data/mtg-goldfishing.sqlite3")


@dataclass(frozen=True)
class SettingsProblem:
    """A setting in the environment the service cannot start with."""

    message: str


# @spec TOOL-003, TOOL-004
def settings_from(environ: Mapping[str, str]) -> Settings | SettingsProblem:
    """The settings named in `environ`, each defaulting when absent or empty."""
    defaults = Settings()
    host = environ.get(HOST_VARIABLE) or defaults.host
    database = environ.get(DATABASE_VARIABLE)
    port_text = environ.get(PORT_VARIABLE)
    port = defaults.port
    if port_text:
        if not port_text.strip().isdigit() or not 0 < int(port_text) <= HIGHEST_PORT:
            return SettingsProblem(
                f"{PORT_VARIABLE} is {port_text!r}; it must be a port number from 1 to"
                f" {HIGHEST_PORT}"
            )
        port = int(port_text)
    return Settings(
        host=host, port=port, database=Path(database) if database else defaults.database
    )


@dataclass(frozen=True)
class Composition:
    """The service wired to its adapters, and what must be released when it stops."""

    service: Service
    stores: SqliteStores
    catalog: CardCatalog
    changes: GameChanges

    def close(self) -> None:
        if isinstance(self.catalog, ScryfallCatalog):
            self.catalog.close()
        self.stores.database.close()


# @spec APP-051, APP-052
def compose(settings: Settings, *, catalog: CardCatalog | None = None) -> Composition:
    """The service over SQLite at the configured path.

    Card data comes from Scryfall through the SQLite card cache, unless `catalog` is given:
    that is for checks that must not reach the network, and is never set by `main`.
    Raises `SchemaTooNew` when the database was laid out by a newer version.
    """
    stores = SqliteStores.open(settings.database)
    cards = catalog if catalog is not None else ScryfallCatalog(stores.card_cache)
    changes = InProcessGameChanges()
    service = Service(
        games=stores.games,
        decks=stores.decks,
        records=stores.records,
        unit_of_work=stores.unit_of_work,
        catalog=cards,
        locks=InProcessGameLocks(),
        ids=RandomIdSource(),
        clock=SystemClock(),
        renderer=TextRenderer(),
        changes=changes,
    )
    return Composition(service, stores, cards, changes)


Runner = Callable[[FastAPI, str, int], None]


def run_with_uvicorn(app: FastAPI, host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port)


# @spec TOOL-001, STOR-014
def serve(
    settings: Settings,
    *,
    catalog: CardCatalog | None = None,
    run: Runner = run_with_uvicorn,
) -> int:
    """Serve until stopped; the process's exit status.

    A database with a newer schema ends start-up with its message and a non-zero status,
    before anything is changed.
    """
    try:
        composition = compose(settings, catalog=catalog)
    except SchemaTooNew as too_new:
        print(f"mtg-goldfishing: {too_new}", file=sys.stderr)
        return 1
    try:
        run(create_app(composition.service, host=settings.host), settings.host, settings.port)
    finally:
        composition.close()
    return 0


# @spec TOOL-005
def main(environ: Mapping[str, str] | None = None) -> int:
    """The `mtg-goldfishing` command: serve with the settings in the environment."""
    settings = settings_from(os.environ if environ is None else environ)
    if isinstance(settings, SettingsProblem):
        print(f"mtg-goldfishing: {settings.message}", file=sys.stderr)
        return 2
    return serve(settings)


if __name__ == "__main__":
    sys.exit(main())
