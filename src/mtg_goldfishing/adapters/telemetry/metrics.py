"""The service metrics: the two duration histograms, their attributes and bucket boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.util.types import AttributeValue

METER_NAME = "mtg_goldfishing"
TOOL_CALL_DURATION = "goldfishing.tool_call.duration"
HTTP_REQUEST_DURATION = "http.server.request.duration"
SECONDS = "s"
BUCKET_BOUNDARIES: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0,
    15.0, 20.0, 25.0, 30.0, 35.0, 45.0, 60.0, 65.0, 90.0,
)  # fmt: skip
"""Seconds; edges just above `wait`'s timeouts of 30 and 60 seconds."""

KNOWN_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
)
OTHER_METHOD = "_OTHER"


# @spec TEL-021
def meter_provider(
    *, readers: Sequence[MetricReader] = (), resource: Resource | None = None
) -> MeterProvider:
    """A meter provider giving both instruments the service's bucket boundaries.

    It is shut down by whoever built it, never at interpreter exit.
    """
    views = [
        View(
            instrument_name=name,
            aggregation=ExplicitBucketHistogramAggregation(boundaries=BUCKET_BOUNDARIES),
        )
        for name in (TOOL_CALL_DURATION, HTTP_REQUEST_DURATION)
    ]
    if resource is None:
        return MeterProvider(metric_readers=readers, views=views, shutdown_on_exit=False)
    return MeterProvider(
        metric_readers=readers, resource=resource, views=views, shutdown_on_exit=False
    )


class ServiceMetrics:
    """Records tool calls and HTTP requests as measurements."""

    def __init__(self, provider: MeterProvider) -> None:
        meter = provider.get_meter(METER_NAME)
        self._tool_calls = meter.create_histogram(
            TOOL_CALL_DURATION, unit=SECONDS, description="Duration of MCP tool calls."
        )
        self._http_requests = meter.create_histogram(
            HTTP_REQUEST_DURATION, unit=SECONDS, description="Duration of HTTP server requests."
        )

    # @spec TEL-009
    def record_tool_call(self, tool: str, status: str, seconds: float) -> None:
        self._tool_calls.record(seconds, {"tool.name": tool, "tool.status": status})

    # @spec TEL-011
    def record_http_request(
        self,
        *,
        method: str,
        scheme: str,
        route: str,
        status_code: int | None,
        error_type: str | None,
        seconds: float,
    ) -> None:
        """Record one request; an unknown method is folded into `_OTHER`, and a status code
        or error type of `None` is left out."""
        attributes: dict[str, AttributeValue] = {
            "http.request.method": method if method in KNOWN_METHODS else OTHER_METHOD,
            "url.scheme": scheme,
            "http.route": route,
        }
        if status_code is not None:
            attributes["http.response.status_code"] = status_code
        if error_type is not None:
            attributes["error.type"] = error_type
        self._http_requests.record(seconds, attributes)
