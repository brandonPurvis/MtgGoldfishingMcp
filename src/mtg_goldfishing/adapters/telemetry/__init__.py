"""Telemetry: the service's measurements of itself, pushed over OTLP when configured.

Shapes only; the behaviour follows the specs TEL-001..059.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.resources import Resource

TOOL_CALL_DURATION = "goldfishing.tool_call.duration"
HTTP_REQUEST_DURATION = "http.server.request.duration"
BUCKET_BOUNDARIES: tuple[float, ...] = ()


def meter_provider(
    *, readers: Sequence[MetricReader] = (), resource: Resource | None = None
) -> MeterProvider:
    raise NotImplementedError


class ServiceMetrics:
    """Records tool calls and HTTP requests as measurements."""

    def __init__(self, provider: MeterProvider) -> None:
        self._provider = provider

    def record_tool_call(self, tool: str, status: str, seconds: float) -> None:
        raise NotImplementedError

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
        raise NotImplementedError


class HttpMeasurement:
    """ASGI middleware measuring every HTTP request the wrapped application receives."""

    def __init__(
        self,
        app: Any,
        *,
        metrics: ServiceMetrics,
        routes: Collection[str],
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self._app(scope, receive, send)


@dataclass(frozen=True)
class TelemetrySettings:
    """Where and how often metrics are pushed, and the resource they describe."""

    endpoint: str | None
    interval_millis: int
    resource_attributes: Mapping[str, str]


@dataclass(frozen=True)
class TelemetryProblem:
    """A telemetry setting the service cannot start with."""

    message: str


def telemetry_settings_from(
    environ: Mapping[str, str], *, instance_id: Callable[[], str] = lambda: ""
) -> TelemetrySettings | TelemetryProblem:
    raise NotImplementedError


def meter_provider_for(settings: TelemetrySettings) -> MeterProvider:
    raise NotImplementedError
