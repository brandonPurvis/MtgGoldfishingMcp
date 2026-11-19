"""The environment the end-to-end harness starts the service with. Starts nothing."""

from pathlib import Path

import pytest

from tests.e2e.running_service import _environment


# @spec TEL-041
def test_the_harness_starts_the_service_with_every_otel_variable_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://127.0.0.1:4318/v1/metrics")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "a-developer-s-shell")

    environment = _environment(8123, tmp_path / "games.sqlite3")

    assert [name for name in environment if name.upper().startswith("OTEL_")] == []


# @spec TEL-041
def test_the_harness_keeps_the_rest_of_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GOLDFISHING_UNRELATED", "kept")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "a-developer-s-shell")

    environment = _environment(8123, tmp_path / "games.sqlite3")

    assert environment.get("GOLDFISHING_UNRELATED") == "kept"
