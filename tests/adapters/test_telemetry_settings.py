"""The telemetry settings: whether and where metrics are pushed, how often, with which resource
attributes, and the settings the service refuses to start with."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping

import pytest

from mtg_goldfishing.adapters.telemetry import (
    ServiceMetrics,
    TelemetryProblem,
    TelemetrySettings,
    meter_provider_for,
    telemetry_settings_from,
)
from tests.support.telemetry import OtlpReceiver, an_otlp_receiver

ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
METRICS_ENDPOINT = "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
PROTOCOL = "OTEL_EXPORTER_OTLP_PROTOCOL"
METRICS_PROTOCOL = "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL"
INTERVAL = "OTEL_METRIC_EXPORT_INTERVAL"
EXPORTER = "OTEL_METRICS_EXPORTER"
DISABLED = "OTEL_SDK_DISABLED"
SERVICE_NAME = "OTEL_SERVICE_NAME"
RESOURCE_ATTRIBUTES = "OTEL_RESOURCE_ATTRIBUTES"
COLLECTOR = "http://127.0.0.1:4318"
PUSH_TIMEOUT = 5.0


@pytest.fixture(autouse=True)
def _no_otel_variables_in_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenTelemetry also reads the process's environment; a developer's shell must not
    reach these tests."""
    for name in list(os.environ):
        if name.upper().startswith("OTEL_"):
            monkeypatch.delenv(name)


@pytest.fixture
def receiver() -> Iterator[OtlpReceiver]:
    with an_otlp_receiver() as running:
        yield running


def _settings(environ: Mapping[str, str]) -> TelemetrySettings:
    settings = telemetry_settings_from(environ, instance_id=lambda: "instance-1")
    assert isinstance(settings, TelemetrySettings), settings
    return settings


def _problem(environ: Mapping[str, str]) -> TelemetryProblem:
    problem = telemetry_settings_from(environ, instance_id=lambda: "instance-1")
    assert isinstance(problem, TelemetryProblem), problem
    return problem


def _pushed_once(settings: TelemetrySettings) -> None:
    """Record a tool call under these settings and stop, pushing what was measured."""
    provider = meter_provider_for(settings)
    ServiceMetrics(provider).record_tool_call("get_state", "OK", 0.25)
    provider.shutdown()


# ------------------------------------------------------------------ whether metrics are pushed


# @spec TEL-026
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_with_no_endpoint_export_is_off() -> None:
    assert _settings({}).endpoint is None


# @spec TEL-026
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_empty_endpoint_variables_count_as_unset() -> None:
    assert _settings({METRICS_ENDPOINT: "", ENDPOINT: ""}).endpoint is None


# @spec TEL-026
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_with_export_off_nothing_is_pushed_whatever_the_process_environment_says(
    receiver: OtlpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENDPOINT, receiver.base_url)
    monkeypatch.setenv(METRICS_ENDPOINT, f"{receiver.base_url}/v1/metrics")

    _pushed_once(_settings({}))

    assert receiver.pushes == []


# @spec TEL-032
@pytest.mark.parametrize(
    ("variable", "value"),
    [(DISABLED, "true"), (DISABLED, "TRUE"), (EXPORTER, "none"), (EXPORTER, "None")],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_telemetry_turned_off_exports_nothing_whatever_endpoint_is_set(
    variable: str, value: str
) -> None:
    settings = _settings({variable: value, ENDPOINT: COLLECTOR})

    assert settings.endpoint is None


# @spec TEL-032
@pytest.mark.parametrize(
    ("variable", "value"), [(DISABLED, "true"), (EXPORTER, "none")], ids=["disabled", "none"]
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_telemetry_turned_off_checks_neither_endpoint_protocol_nor_interval(
    variable: str, value: str
) -> None:
    environ = {
        variable: value,
        ENDPOINT: "not a url",
        METRICS_ENDPOINT: "collector:4318",
        PROTOCOL: "grpc",
        METRICS_PROTOCOL: "http/json",
        INTERVAL: "soon",
    }

    assert isinstance(telemetry_settings_from(environ), TelemetrySettings)


# @spec TEL-032
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_sdk_disabled_set_to_anything_but_true_leaves_telemetry_on() -> None:
    assert _settings({DISABLED: "false", ENDPOINT: COLLECTOR}).endpoint is not None


# ------------------------------------------------------------------ where metrics are pushed


# @spec TEL-027
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_metrics_endpoint_is_used_exactly_as_given() -> None:
    settings = _settings({METRICS_ENDPOINT: "http://collector:4318/custom/path"})

    assert settings.endpoint == "http://collector:4318/custom/path"


# @spec TEL-027
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_metrics_endpoint_wins_over_the_general_endpoint() -> None:
    settings = _settings(
        {METRICS_ENDPOINT: "http://metrics:4318/v1/metrics", ENDPOINT: "http://general:4318"}
    )

    assert settings.endpoint == "http://metrics:4318/v1/metrics"


# @spec TEL-027
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_an_empty_metrics_endpoint_gives_way_to_the_general_endpoint() -> None:
    settings = _settings({METRICS_ENDPOINT: "", ENDPOINT: "http://general:4318"})

    assert settings.endpoint == "http://general:4318/v1/metrics"


# @spec TEL-027
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_metrics_are_pushed_to_the_metrics_endpoint_as_given(receiver: OtlpReceiver) -> None:
    settings = _settings({METRICS_ENDPOINT: f"{receiver.base_url}/custom/path"})

    _pushed_once(settings)

    assert [push.path for push in receiver.pushes] == ["/custom/path"]


# @spec TEL-027, TEL-028
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_metrics_are_pushed_as_protobuf_over_http(receiver: OtlpReceiver) -> None:
    settings = _settings({ENDPOINT: receiver.base_url})

    _pushed_once(settings)

    assert [push.headers.get("content-type") for push in receiver.pushes] == [
        "application/x-protobuf"
    ]


# @spec TEL-028
@pytest.mark.parametrize(
    ("general", "endpoint"),
    [
        ("http://collector:4318", "http://collector:4318/v1/metrics"),
        ("http://collector:4318/", "http://collector:4318/v1/metrics"),
        ("https://collector.example/otlp", "https://collector.example/otlp/v1/metrics"),
        ("https://collector.example/otlp/", "https://collector.example/otlp/v1/metrics"),
    ],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_general_endpoint_has_v1_metrics_appended_after_one_slash(
    general: str, endpoint: str
) -> None:
    assert _settings({ENDPOINT: general}).endpoint == endpoint


# @spec TEL-028
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_metrics_are_pushed_to_v1_metrics_under_the_general_endpoint(
    receiver: OtlpReceiver,
) -> None:
    settings = _settings({ENDPOINT: f"{receiver.base_url}/otlp"})

    _pushed_once(settings)

    assert [push.path for push in receiver.pushes] == ["/otlp/v1/metrics"]


# ------------------------------------------------------------------ how often


# @spec TEL-029
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_metrics_are_pushed_every_five_seconds_by_default() -> None:
    assert _settings({ENDPOINT: COLLECTOR}).interval_millis == 5000


# @spec TEL-029
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_an_empty_interval_counts_as_unset() -> None:
    assert _settings({ENDPOINT: COLLECTOR, INTERVAL: ""}).interval_millis == 5000


# @spec TEL-029
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_push_interval_comes_from_the_environment() -> None:
    assert _settings({ENDPOINT: COLLECTOR, INTERVAL: "250"}).interval_millis == 250


# @spec TEL-029
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_metrics_are_pushed_each_interval_without_being_asked(receiver: OtlpReceiver) -> None:
    provider = meter_provider_for(_settings({ENDPOINT: receiver.base_url, INTERVAL: "50"}))
    try:
        ServiceMetrics(provider).record_tool_call("get_state", "OK", 0.25)

        assert receiver.wait_for_push(PUSH_TIMEOUT)
    finally:
        provider.shutdown()


# ------------------------------------------------------------------ resource attributes


# @spec TEL-030
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_service_is_named_mtg_goldfishing_by_default() -> None:
    assert _settings({}).resource_attributes["service.name"] == "mtg-goldfishing"


# @spec TEL-030
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_service_name_comes_from_otel_service_name() -> None:
    settings = _settings({SERVICE_NAME: "table-one"})

    assert settings.resource_attributes["service.name"] == "table-one"


# @spec TEL-030
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_service_name_comes_from_the_resource_attributes_without_otel_service_name() -> None:
    settings = _settings({SERVICE_NAME: "", RESOURCE_ATTRIBUTES: "service.name=table-two"})

    assert settings.resource_attributes["service.name"] == "table-two"


# @spec TEL-030
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_otel_service_name_wins_over_the_resource_attributes() -> None:
    settings = _settings({SERVICE_NAME: "table-one", RESOURCE_ATTRIBUTES: "service.name=table-two"})

    assert settings.resource_attributes["service.name"] == "table-one"


# @spec TEL-031
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_instance_id_comes_from_the_resource_attributes() -> None:
    settings = _settings({RESOURCE_ATTRIBUTES: "service.instance.id=seat-runner-7"})

    assert settings.resource_attributes["service.instance.id"] == "seat-runner-7"


# @spec TEL-031
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_without_one_given_the_instance_id_is_chosen_at_start() -> None:
    assert _settings({}).resource_attributes["service.instance.id"] == "instance-1"


# @spec TEL-031
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_instance_id_is_chosen_anew_each_time_the_service_starts() -> None:
    first = telemetry_settings_from({})
    second = telemetry_settings_from({})
    assert isinstance(first, TelemetrySettings)
    assert isinstance(second, TelemetrySettings)

    ids = {
        first.resource_attributes["service.instance.id"],
        second.resource_attributes["service.instance.id"],
    }
    assert len(ids) == 2


# @spec TEL-033
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_other_resource_attributes_are_given_to_every_measurement() -> None:
    settings = _settings({RESOURCE_ATTRIBUTES: "deployment.environment=test,host.name=box"})

    assert dict(settings.resource_attributes) == {
        "service.name": "mtg-goldfishing",
        "service.instance.id": "instance-1",
        "deployment.environment": "test",
        "host.name": "box",
    }


# @spec TEL-030, TEL-031, TEL-033
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_resource_attributes_are_pushed_with_the_metrics(receiver: OtlpReceiver) -> None:
    settings = _settings(
        {
            ENDPOINT: receiver.base_url,
            SERVICE_NAME: "table-one",
            RESOURCE_ATTRIBUTES: "service.instance.id=seat-runner-7,deployment.environment=test",
        }
    )

    _pushed_once(settings)

    [push] = receiver.pushes
    pushed = push.resource_attributes()
    assert {
        name: pushed.get(name)
        for name in ("service.name", "service.instance.id", "deployment.environment")
    } == {
        "service.name": "table-one",
        "service.instance.id": "seat-runner-7",
        "deployment.environment": "test",
    }


# ------------------------------------------------------------------ left to OpenTelemetry


# @spec TEL-034
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_push_headers_and_timeout_are_not_checked() -> None:
    environ = {
        ENDPOINT: COLLECTOR,
        "OTEL_EXPORTER_OTLP_HEADERS": "not a header list",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "===",
        "OTEL_EXPORTER_OTLP_TIMEOUT": "soon",
        "OTEL_EXPORTER_OTLP_METRICS_TIMEOUT": "-1",
    }

    assert isinstance(telemetry_settings_from(environ), TelemetrySettings)


# @spec TEL-034
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_push_headers_are_applied_by_the_otlp_exporter(
    receiver: OtlpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-goldfishing-key=table-one")

    _pushed_once(_settings({ENDPOINT: receiver.base_url}))

    assert [push.headers.get("x-goldfishing-key") for push in receiver.pushes] == ["table-one"]


# ------------------------------------------------------------------ settings refused


# @spec TEL-035
@pytest.mark.parametrize(
    "value", ["collector:4318", "localhost", "ftp://collector:4318", "http://", "http:///v1"]
)
@pytest.mark.parametrize("variable", [ENDPOINT, METRICS_ENDPOINT])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_an_endpoint_that_is_not_an_http_url_with_a_host_is_a_problem_naming_its_variable(
    variable: str, value: str
) -> None:
    assert variable in _problem({variable: value}).message


# @spec TEL-035
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_general_endpoint_is_not_checked_when_the_metrics_endpoint_is_in_effect() -> None:
    settings = _settings({METRICS_ENDPOINT: "http://metrics:4318/v1/metrics", ENDPOINT: "nonsense"})

    assert settings.endpoint == "http://metrics:4318/v1/metrics"


# @spec TEL-036
@pytest.mark.parametrize("value", ["0", "-5", "1.5", "five", "1e3"])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_an_interval_that_is_not_a_whole_number_above_zero_is_a_problem(value: str) -> None:
    assert INTERVAL in _problem({ENDPOINT: COLLECTOR, INTERVAL: value}).message


# @spec TEL-036
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_interval_is_not_checked_with_export_off() -> None:
    assert isinstance(telemetry_settings_from({INTERVAL: "five"}), TelemetrySettings)


# @spec TEL-037
@pytest.mark.parametrize(
    ("variable", "value"),
    [(PROTOCOL, "grpc"), (PROTOCOL, "http/json"), (METRICS_PROTOCOL, "grpc")],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_protocol_other_than_http_protobuf_is_a_problem_naming_its_variable(
    variable: str, value: str
) -> None:
    assert variable in _problem({ENDPOINT: COLLECTOR, variable: value}).message


# @spec TEL-037
@pytest.mark.parametrize("value", ["http/protobuf", "HTTP/Protobuf", ""])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_http_protobuf_in_any_case_or_no_protocol_is_accepted(value: str) -> None:
    assert _settings({ENDPOINT: COLLECTOR, PROTOCOL: value}).endpoint is not None


# @spec TEL-037
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_metrics_protocol_wins_over_the_general_protocol() -> None:
    settings = _settings({ENDPOINT: COLLECTOR, METRICS_PROTOCOL: "http/protobuf", PROTOCOL: "grpc"})

    assert settings.endpoint is not None


# @spec TEL-037
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_protocol_is_not_checked_with_export_off() -> None:
    assert isinstance(telemetry_settings_from({PROTOCOL: "grpc"}), TelemetrySettings)


# @spec TEL-038
@pytest.mark.parametrize("value", ["prometheus", "console", "otlp,console"])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_metrics_exporter_other_than_otlp_or_none_is_a_problem(value: str) -> None:
    assert EXPORTER in _problem({EXPORTER: value}).message


# @spec TEL-038
@pytest.mark.parametrize("value", ["otlp", "OTLP"])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_otlp_metrics_exporter_is_accepted(value: str) -> None:
    assert _settings({EXPORTER: value, ENDPOINT: COLLECTOR}).endpoint is not None
