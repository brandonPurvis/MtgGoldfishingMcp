"""The service metrics: the tool-call and HTTP request instruments, their attributes, and the
bucket boundaries both share."""

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from mtg_goldfishing.adapters.telemetry import BUCKET_BOUNDARIES, ServiceMetrics, meter_provider
from tests.support.telemetry import measured

TOOL_CALLS = "goldfishing.tool_call.duration"
HTTP_REQUESTS = "http.server.request.duration"
BOUNDARIES = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
    15.0,
    20.0,
    25.0,
    30.0,
    35.0,
    45.0,
    60.0,
    65.0,
    90.0,
)
METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH")


def _metrics() -> tuple[ServiceMetrics, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    return ServiceMetrics(meter_provider(readers=[reader])), reader


def _record_request(metrics: ServiceMetrics, method: str = "GET") -> None:
    metrics.record_http_request(
        method=method,
        scheme="http",
        route="/health",
        status_code=200,
        error_type=None,
        seconds=0.01,
    )


# @spec TEL-009
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_tool_call_is_one_measurement_of_its_duration() -> None:
    metrics, reader = _metrics()

    metrics.record_tool_call("get_state", "OK", 0.25)

    assert [(point.count, point.total) for point in measured(reader, TOOL_CALLS)] == [(1, 0.25)]


# @spec TEL-009
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_tool_call_durations_are_in_seconds() -> None:
    metrics, reader = _metrics()

    metrics.record_tool_call("get_state", "OK", 0.25)

    assert [point.unit for point in measured(reader, TOOL_CALLS)] == ["s"]


# @spec TEL-009
@pytest.mark.parametrize(
    ("tool", "status"),
    [("play", "REJECTED"), ("unknown", "PROTOCOL_ERROR"), ("wait", "CANCELLED")],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_tool_call_is_attributed_to_its_tool_and_its_status_as_given(
    tool: str, status: str
) -> None:
    metrics, reader = _metrics()

    metrics.record_tool_call(tool, status, 0.25)

    assert [point.attributes for point in measured(reader, TOOL_CALLS)] == [
        {"tool.name": tool, "tool.status": status}
    ]


# @spec TEL-011
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_known_request_method_is_recorded_as_it_is(method: str) -> None:
    metrics, reader = _metrics()

    _record_request(metrics, method)

    [point] = measured(reader, HTTP_REQUESTS)
    assert point.attributes["http.request.method"] == method


# @spec TEL-011
@pytest.mark.parametrize("method", ["PROPFIND", "BREW"])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_any_other_request_method_is_folded_into_other(method: str) -> None:
    metrics, reader = _metrics()

    _record_request(metrics, method)

    [point] = measured(reader, HTTP_REQUESTS)
    assert point.attributes["http.request.method"] == "_OTHER"


# @spec TEL-021
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_bucket_boundaries_are_the_service_s_own() -> None:
    assert tuple(BUCKET_BOUNDARIES) == BOUNDARIES


# @spec TEL-021
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_tool_call_durations_are_bucketed_at_the_service_s_boundaries() -> None:
    metrics, reader = _metrics()

    metrics.record_tool_call("get_state", "OK", 0.25)

    assert [point.bounds for point in measured(reader, TOOL_CALLS)] == [BOUNDARIES]


# @spec TEL-021
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_http_request_durations_are_bucketed_at_the_service_s_boundaries() -> None:
    metrics, reader = _metrics()

    _record_request(metrics)

    assert [point.bounds for point in measured(reader, HTTP_REQUESTS)] == [BOUNDARIES]
