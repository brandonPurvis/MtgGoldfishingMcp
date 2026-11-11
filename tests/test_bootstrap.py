"""The composition root: settings from the environment, the wiring, and start-up."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from mtg_goldfishing.adapters import system
from mtg_goldfishing.adapters.memory import InMemoryCardCatalog
from mtg_goldfishing.adapters.scryfall import ScryfallCatalog
from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase, SqliteStores
from mtg_goldfishing.bootstrap import (
    Settings,
    SettingsProblem,
    compose,
    main,
    serve,
    settings_from,
)
from tests.support.card_data import recorded_cards
from tests.support.decks import ATRAXA, a_deck_list


def _settings(tmp_path: Path) -> Settings:
    return Settings(database=tmp_path / "goldfishing.sqlite3")


# @spec TOOL-003
def test_the_service_listens_on_the_local_machine_by_default() -> None:
    settings = settings_from({})

    assert isinstance(settings, Settings)
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)


# @spec TOOL-003
def test_the_address_and_port_come_from_the_environment() -> None:
    settings = settings_from({"MTG_GOLDFISHING_HOST": "0.0.0.0", "MTG_GOLDFISHING_PORT": "9123"})

    assert isinstance(settings, Settings)
    assert (settings.host, settings.port) == ("0.0.0.0", 9123)


# @spec TOOL-003
@pytest.mark.parametrize("port", ["eighty", "0", "70000"])
def test_a_port_that_is_not_a_port_number_is_a_settings_problem(port: str) -> None:
    problem = settings_from({"MTG_GOLDFISHING_PORT": port})

    assert isinstance(problem, SettingsProblem)
    assert "MTG_GOLDFISHING_PORT" in problem.message


# @spec TOOL-004
def test_the_database_is_kept_under_data_by_default() -> None:
    settings = settings_from({})

    assert isinstance(settings, Settings)
    assert settings.database == Path("data/mtg-goldfishing.sqlite3")


# @spec TOOL-004
def test_the_database_path_comes_from_the_environment(tmp_path: Path) -> None:
    settings = settings_from({"MTG_GOLDFISHING_DB": str(tmp_path / "games.sqlite3")})

    assert isinstance(settings, Settings)
    assert settings.database == tmp_path / "games.sqlite3"


# @spec TOOL-004
def test_the_composed_service_keeps_its_games_in_the_configured_database(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    composition = compose(settings, catalog=InMemoryCardCatalog(recorded_cards()))
    try:
        answer = composition.service.load_deck({"cards": a_deck_list().text(), "commander": ATRAXA})
    finally:
        composition.close()

    deck_id = getattr(answer.outcome.summary, "deck_id", None)
    assert isinstance(deck_id, str)
    reopened = SqliteStores.open(settings.database)
    try:
        assert reopened.decks.get(deck_id) is not None
    finally:
        reopened.database.close()


def test_the_composed_service_looks_cards_up_on_scryfall_by_default(tmp_path: Path) -> None:
    composition = compose(_settings(tmp_path))
    try:
        assert isinstance(composition.catalog, ScryfallCatalog)
    finally:
        composition.close()


def test_the_composed_service_answers_in_the_text_format(tmp_path: Path) -> None:
    composition = compose(_settings(tmp_path), catalog=InMemoryCardCatalog(recorded_cards()))
    try:
        answer = composition.service.get_state({"game_id": "gnosuchgame"})
    finally:
        composition.close()

    assert answer.response.startswith("ERROR ")


# @spec TOOL-001, TOOL-003
def test_serving_runs_the_http_application_on_the_configured_address(tmp_path: Path) -> None:
    served: list[tuple[str, int]] = []

    def run(app: FastAPI, host: str, port: int) -> None:
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            assert client.get("/health").status_code == 200
        served.append((host, port))

    settings = Settings(host="127.0.0.1", port=8123, database=tmp_path / "games.sqlite3")
    code = serve(settings, catalog=InMemoryCardCatalog(recorded_cards()), run=run)

    assert (code, served) == (0, [("127.0.0.1", 8123)])


def _database_from_the_future(path: Path) -> None:
    database = SqliteDatabase(path, migrations=(*MIGRATIONS, "CREATE TABLE later (id INTEGER)"))
    database.close()


# @spec STOR-014
def test_start_up_against_a_newer_schema_ends_with_a_non_zero_exit(tmp_path: Path) -> None:
    path = tmp_path / "games.sqlite3"
    _database_from_the_future(path)

    assert main({"MTG_GOLDFISHING_DB": str(path)}) != 0


# @spec STOR-014
def test_start_up_against_a_newer_schema_says_why(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "games.sqlite3"
    _database_from_the_future(path)

    main({"MTG_GOLDFISHING_DB": str(path)})

    assert "schema version" in capsys.readouterr().err


def test_start_up_with_a_bad_setting_ends_with_a_non_zero_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main({"MTG_GOLDFISHING_PORT": "eighty"})

    assert (code != 0, "MTG_GOLDFISHING_PORT" in capsys.readouterr().err) == (True, True)


# @spec APP-051
@pytest.mark.xfail(strict=True, reason="M3c: not built")
def test_the_composed_service_wakes_waiting_seats_with_the_in_process_game_changes(
    tmp_path: Path,
) -> None:
    composition: Any = compose(_settings(tmp_path), catalog=InMemoryCardCatalog(recorded_cards()))
    try:
        assert isinstance(composition.changes, getattr(system, "InProcessGameChanges"))  # noqa: B009
    finally:
        composition.close()


# @spec APP-075
@pytest.mark.xfail(strict=True, reason="M3c: not built")
def test_the_composed_service_answers_wait(tmp_path: Path) -> None:
    composition: Any = compose(_settings(tmp_path), catalog=InMemoryCardCatalog(recorded_cards()))
    try:
        answer = composition.service.wait({"game_id": "gnosuchgame"})
    finally:
        composition.close()
    assert answer.response.startswith("ERROR ")
