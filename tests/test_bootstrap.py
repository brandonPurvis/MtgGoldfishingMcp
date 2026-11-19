"""The composition root: settings from the environment, the wiring, and start-up."""

import json
import os
import re
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import pytest
from fastapi import FastAPI
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from starlette.testclient import TestClient

from mtg_goldfishing.adapters.memory import InMemoryCardCache, InMemoryCardCatalog
from mtg_goldfishing.adapters.scryfall import ScryfallCatalog
from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase, SqliteStores
from mtg_goldfishing.adapters.system import InProcessGameChanges
from mtg_goldfishing.adapters.telemetry import TelemetrySettings, meter_provider
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
from tests.support.telemetry import Measured, an_otlp_receiver, measured, unreachable_endpoint


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
def test_the_composed_service_wakes_waiting_seats_with_the_in_process_game_changes(
    tmp_path: Path,
) -> None:
    composition = compose(_settings(tmp_path), catalog=InMemoryCardCatalog(recorded_cards()))
    try:
        assert isinstance(composition.changes, InProcessGameChanges)
    finally:
        composition.close()


# @spec APP-075
def test_the_composed_service_answers_wait(tmp_path: Path) -> None:
    composition = compose(_settings(tmp_path), catalog=InMemoryCardCatalog(recorded_cards()))
    try:
        answer = composition.service.wait({"game_id": "gnosuchgame"})
    finally:
        composition.close()
    assert answer.response.startswith("ERROR ")


# ---------------------------------------------------------------------------------- telemetry

LOCAL = "http://127.0.0.1:8000"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}
TOOL_CALLS = "goldfishing.tool_call.duration"
HTTP_REQUESTS = "http.server.request.duration"
QUICK_PUSHES = 50
"""Milliseconds between pushes, so that pushes are attempted while calls are answered."""


@pytest.fixture
def _no_otel_variables_in_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenTelemetry's exporter also reads the process's environment; a developer's shell
    must not reach these tests."""
    for name in list(os.environ):
        if name.upper().startswith("OTEL_"):
            monkeypatch.delenv(name)


@pytest.fixture
def _never_served(monkeypatch: pytest.MonkeyPatch) -> None:
    """A start-up that should be refused must not reach the HTTP server."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the service started serving")

    monkeypatch.setattr("uvicorn.run", refuse)


def _telemetry(endpoint: str, interval_millis: int = 60_000) -> TelemetrySettings:
    return TelemetrySettings(
        endpoint=endpoint,
        interval_millis=interval_millis,
        resource_attributes={"service.name": "mtg-goldfishing", "service.instance.id": "test"},
    )


def _tool_call(client: TestClient, name: str, arguments: dict[str, object]) -> str:
    """The response text of one tool call over the MCP endpoint."""
    rpc = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    response = client.post("/mcp", headers=MCP_HEADERS, json=rpc)
    for line in response.text.splitlines():
        if line.startswith("data:"):
            message = json.loads(line.removeprefix("data:"))
            break
    else:
        message = json.loads(response.text)
    text: str = message["result"]["content"][0]["text"]
    return text


def _served_and_measured(
    tmp_path: Path, requests: Callable[[TestClient], None]
) -> tuple[list[Measured], list[Measured]]:
    """Serve with a meter provider read back in memory, make the requests, and give the tool
    calls and the HTTP requests measured."""
    reader = InMemoryMetricReader()
    seen: list[tuple[list[Measured], list[Measured]]] = []

    def run(app: FastAPI, host: str, port: int) -> None:
        with TestClient(app, base_url=LOCAL) as client:
            requests(client)
        seen.append((measured(reader, TOOL_CALLS), measured(reader, HTTP_REQUESTS)))

    serve(
        _settings(tmp_path),
        catalog=InMemoryCardCatalog(recorded_cards()),
        run=run,
        meter_provider=meter_provider(readers=[reader]),
    )
    return seen[0]


# @spec TEL-024
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_served_application_reports_each_tool_call_to_the_service_metrics(
    tmp_path: Path,
) -> None:
    tool_calls, _ = _served_and_measured(
        tmp_path, lambda client: _tool_call(client, "get_state", {"game_id": "gnosuchgame"})
    )

    assert [
        (point.attributes["tool.name"], point.attributes["tool.status"]) for point in tool_calls
    ] == [("get_state", "ERROR")]


# @spec TEL-024
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_served_application_measures_http_requests_by_mcp_health_and_other(
    tmp_path: Path,
) -> None:
    def requests(client: TestClient) -> None:
        client.get("/health")
        _tool_call(client, "get_state", {"game_id": "gnosuchgame"})
        client.get("/elsewhere")

    _, http_requests = _served_and_measured(tmp_path, requests)

    assert sorted(str(point.attributes["http.route"]) for point in http_requests) == [
        "/health",
        "/mcp",
        "other",
    ]


# @spec TEL-024, TEL-025
@pytest.mark.usefixtures("_no_otel_variables_in_the_process")
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_serving_with_export_on_pushes_what_was_measured_when_it_stops(tmp_path: Path) -> None:
    def run(app: FastAPI, host: str, port: int) -> None:
        with TestClient(app, base_url=LOCAL) as client:
            client.get("/health")

    with an_otlp_receiver() as receiver:
        serve(
            _settings(tmp_path),
            catalog=InMemoryCardCatalog(recorded_cards()),
            run=run,
            telemetry=_telemetry(f"{receiver.base_url}/v1/metrics"),
        )

    assert [push.path for push in receiver.pushes] == ["/v1/metrics"]


class ShutdownFailed(Exception):
    """The meter provider could not shut down."""


class WatchedMeterProvider(MeterProvider):
    """A meter provider noting when it is shut down, and how long it was given."""

    def __init__(self, events: list[str], *, fails: bool = False) -> None:
        super().__init__(shutdown_on_exit=False)
        self.events = events
        self.timeouts: list[float] = []
        self._fails = fails

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        self.events.append("meter provider shut down")
        self.timeouts.append(timeout_millis)
        if self._fails:
            raise ShutdownFailed
        super().shutdown(timeout_millis=timeout_millis)


class WatchedCatalog(ScryfallCatalog):
    """The Scryfall card catalog noting when it is closed."""

    def __init__(self, events: list[str]) -> None:
        super().__init__(InMemoryCardCache())
        self.events = events

    def close(self) -> None:
        self.events.append("card catalog closed")
        super().close()


def _served_and_stopped(tmp_path: Path, provider: WatchedMeterProvider, events: list[str]) -> None:
    def run(app: FastAPI, host: str, port: int) -> None:
        with TestClient(app, base_url=LOCAL) as client:
            client.get("/health")
        events.append("application stopped")

    serve(_settings(tmp_path), catalog=WatchedCatalog(events), run=run, meter_provider=provider)


# @spec TEL-025
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_meter_provider_is_shut_down_after_the_application_and_before_the_stores(
    tmp_path: Path,
) -> None:
    events: list[str] = []

    _served_and_stopped(tmp_path, WatchedMeterProvider(events), events)

    assert events == ["application stopped", "meter provider shut down", "card catalog closed"]


# @spec TEL-025
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_meter_provider_is_given_at_most_five_seconds_to_shut_down(tmp_path: Path) -> None:
    events: list[str] = []
    provider = WatchedMeterProvider(events)

    _served_and_stopped(tmp_path, provider, events)

    assert provider.timeouts == [5000]


# @spec TEL-025
def test_the_stores_are_closed_even_when_the_meter_provider_fails_to_shut_down(
    tmp_path: Path,
) -> None:
    events: list[str] = []

    with suppress(ShutdownFailed):
        _served_and_stopped(tmp_path, WatchedMeterProvider(events, fails=True), events)

    assert "card catalog closed" in events


COLLECTOR = "http://127.0.0.1:4318"
REFUSED_TELEMETRY = [
    pytest.param(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": "collector:4318"},
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        id="TEL-035 endpoint",
    ),
    pytest.param(
        {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "ftp://collector/v1/metrics"},
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        id="TEL-035 metrics endpoint",
    ),
    pytest.param(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR, "OTEL_METRIC_EXPORT_INTERVAL": "0"},
        "OTEL_METRIC_EXPORT_INTERVAL",
        id="TEL-036 interval",
    ),
    pytest.param(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR, "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc"},
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        id="TEL-037 protocol",
    ),
    pytest.param(
        {"OTEL_METRICS_EXPORTER": "prometheus"}, "OTEL_METRICS_EXPORTER", id="TEL-038 exporter"
    ),
]


# @spec TEL-035, TEL-036, TEL-037, TEL-038
@pytest.mark.usefixtures("_never_served")
@pytest.mark.parametrize(("telemetry", "variable"), REFUSED_TELEMETRY)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_start_up_with_unusable_telemetry_settings_exits_with_status_2(
    tmp_path: Path, telemetry: dict[str, str], variable: str
) -> None:
    environ = {"MTG_GOLDFISHING_DB": str(tmp_path / "games.sqlite3"), **telemetry}

    assert main(environ) == 2


# @spec TEL-035, TEL-036, TEL-037, TEL-038
@pytest.mark.usefixtures("_never_served")
@pytest.mark.parametrize(("telemetry", "variable"), REFUSED_TELEMETRY)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_start_up_with_unusable_telemetry_settings_says_which_variable(
    tmp_path: Path, telemetry: dict[str, str], variable: str, capsys: pytest.CaptureFixture[str]
) -> None:
    environ = {"MTG_GOLDFISHING_DB": str(tmp_path / "games.sqlite3"), **telemetry}

    main(environ)

    error = capsys.readouterr().err
    assert (error.startswith("mtg-goldfishing: "), variable in error) == (True, True)


def _a_game_played_over_http(client: TestClient) -> tuple[object, ...]:
    """Load a deck, start a game with a fixed seed and play its first steps; the responses,
    the game's call records and its state, with the random game id put aside."""
    loaded = _tool_call(client, "load_deck", {"cards": a_deck_list().text(), "commander": ATRAXA})
    deck = re.search(r"Loaded deck (\w+)", loaded)
    assert deck is not None, loaded
    started = _tool_call(client, "new_game", {"deck_id": deck[1], "seed": 7})
    game = re.search(r"Started game (\w+)", started)
    assert game is not None, started
    game_id = game[1]
    responses = [
        loaded,
        started,
        _tool_call(client, "mulligan", {"game_id": game_id, "keep": True}),
        _tool_call(client, "play", {"game_id": game_id, "card": "Forest"}),
    ]
    state = _tool_call(client, "get_state", {"game_id": game_id, "detail": "full"})
    log = json.loads(_tool_call(client, "get_log", {"game_id": game_id, "include_calls": True}))
    records = [(call["tool"], call["status"], call["response"]) for call in log["calls"]]
    return tuple(
        json.loads(json.dumps(part).replace(game_id, "<game>"))
        for part in (responses, records, state)
    )


def _played(tmp_path: Path, folder: str, telemetry: TelemetrySettings | None) -> tuple[int, object]:
    """The exit status of serving a game played over HTTP, and what the game was told and kept."""
    played: list[object] = []

    def run(app: FastAPI, host: str, port: int) -> None:
        with TestClient(app, base_url=LOCAL) as client:
            played.append(_a_game_played_over_http(client))

    code = serve(
        Settings(database=tmp_path / folder / "games.sqlite3"),
        catalog=InMemoryCardCatalog(recorded_cards()),
        run=run,
        telemetry=telemetry,
    )
    return code, played[0]


# @spec TEL-040
@pytest.mark.usefixtures("_no_otel_variables_in_the_process")
def test_a_game_is_answered_and_kept_the_same_whether_or_not_telemetry_is_configured(
    tmp_path: Path,
) -> None:
    with an_otlp_receiver() as receiver:
        _, exported = _played(
            tmp_path, "exported", _telemetry(f"{receiver.base_url}/v1/metrics", QUICK_PUSHES)
        )
    _, unconfigured = _played(tmp_path, "unconfigured", None)

    assert exported == unconfigured


# @spec TEL-039, TEL-040
@pytest.mark.usefixtures("_no_otel_variables_in_the_process")
def test_a_game_is_answered_and_kept_the_same_when_every_push_fails(tmp_path: Path) -> None:
    unreachable = _telemetry(unreachable_endpoint(), QUICK_PUSHES)

    _, failing = _played(tmp_path, "unreachable", unreachable)
    _, unconfigured = _played(tmp_path, "unconfigured", None)

    assert failing == unconfigured


# @spec TEL-039
@pytest.mark.usefixtures("_no_otel_variables_in_the_process")
def test_serving_ends_normally_when_every_push_fails(tmp_path: Path) -> None:
    code, _ = _played(tmp_path, "unreachable", _telemetry(unreachable_endpoint(), QUICK_PUSHES))

    assert code == 0
