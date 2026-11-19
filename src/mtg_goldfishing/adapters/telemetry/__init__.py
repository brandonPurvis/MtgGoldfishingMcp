"""Telemetry: the service's measurements of itself, pushed over OTLP when configured.

The service metrics record tool calls and HTTP requests over an OpenTelemetry meter provider;
the HTTP middleware measures each request; the settings say whether and where to push.
"""

from mtg_goldfishing.adapters.telemetry.http import HttpMeasurement
from mtg_goldfishing.adapters.telemetry.metrics import (
    BUCKET_BOUNDARIES,
    HTTP_REQUEST_DURATION,
    TOOL_CALL_DURATION,
    ServiceMetrics,
    meter_provider,
)
from mtg_goldfishing.adapters.telemetry.settings import (
    TelemetryProblem,
    TelemetrySettings,
    meter_provider_for,
    telemetry_settings_from,
)

__all__ = [
    "BUCKET_BOUNDARIES",
    "HTTP_REQUEST_DURATION",
    "TOOL_CALL_DURATION",
    "HttpMeasurement",
    "ServiceMetrics",
    "TelemetryProblem",
    "TelemetrySettings",
    "meter_provider",
    "meter_provider_for",
    "telemetry_settings_from",
]
