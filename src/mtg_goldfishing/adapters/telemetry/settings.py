"""The telemetry settings, read from OpenTelemetry's standard environment variables, and the
meter provider they call for.

| Setting                        | Environment variable                                     |
|--------------------------------|----------------------------------------------------------|
| Where metrics are pushed       | OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, as given; else      |
|                                | OTEL_EXPORTER_OTLP_ENDPOINT with `/v1/metrics` appended  |
| Milliseconds between pushes    | OTEL_METRIC_EXPORT_INTERVAL (5000)                       |
| Service name                   | OTEL_SERVICE_NAME, else OTEL_RESOURCE_ATTRIBUTES         |
| Other resource attributes      | OTEL_RESOURCE_ATTRIBUTES                                 |
| Turning telemetry off          | OTEL_SDK_DISABLED=true or OTEL_METRICS_EXPORTER=none     |

Push headers and timeout are read by OpenTelemetry's OTLP exporter itself.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from mtg_goldfishing.adapters.telemetry.metrics import meter_provider

ENDPOINT_VARIABLE = "OTEL_EXPORTER_OTLP_ENDPOINT"
METRICS_ENDPOINT_VARIABLE = "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
PROTOCOL_VARIABLE = "OTEL_EXPORTER_OTLP_PROTOCOL"
METRICS_PROTOCOL_VARIABLE = "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL"
INTERVAL_VARIABLE = "OTEL_METRIC_EXPORT_INTERVAL"
EXPORTER_VARIABLE = "OTEL_METRICS_EXPORTER"
DISABLED_VARIABLE = "OTEL_SDK_DISABLED"
SERVICE_NAME_VARIABLE = "OTEL_SERVICE_NAME"
RESOURCE_ATTRIBUTES_VARIABLE = "OTEL_RESOURCE_ATTRIBUTES"

SERVICE_NAME = "service.name"
SERVICE_INSTANCE_ID = "service.instance.id"
DEFAULT_SERVICE_NAME = "mtg-goldfishing"
DEFAULT_INTERVAL_MILLIS = 5000
METRICS_PATH = "v1/metrics"
PROTOCOL = "http/protobuf"
EXPORTERS = ("otlp", "none")
URL_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class TelemetrySettings:
    """Where and how often metrics are pushed, and the resource they describe.

    `endpoint` is the full push URL, or `None` when export is off.
    """

    endpoint: str | None
    interval_millis: int
    resource_attributes: Mapping[str, str]


@dataclass(frozen=True)
class TelemetryProblem:
    """A telemetry setting the service cannot start with; the message names its variable."""

    message: str


def _random_instance_id() -> str:
    return str(uuid.uuid4())


def _set(environ: Mapping[str, str], name: str) -> str | None:
    """The variable's value; an empty variable counts as unset."""
    return environ.get(name) or None


def _in_effect(environ: Mapping[str, str], specific: str, general: str) -> tuple[str, str] | None:
    """The variable in effect, the metrics-specific one first, and its value."""
    for name in (specific, general):
        value = _set(environ, name)
        if value is not None:
            return name, value
    return None


def _resource_attributes(
    environ: Mapping[str, str], instance_id: Callable[[], str]
) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for pair in (_set(environ, RESOURCE_ATTRIBUTES_VARIABLE) or "").split(","):
        key, separator, value = pair.partition("=")
        if separator and key.strip():
            attributes[key.strip()] = unquote(value.strip())
    service_name = _set(environ, SERVICE_NAME_VARIABLE)
    if service_name is not None:
        attributes[SERVICE_NAME] = service_name
    attributes.setdefault(SERVICE_NAME, DEFAULT_SERVICE_NAME)
    if SERVICE_INSTANCE_ID not in attributes:
        attributes[SERVICE_INSTANCE_ID] = instance_id()
    return attributes


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in URL_SCHEMES and bool(parsed.hostname)
    except ValueError:
        return False


def _push_url(variable: str, url: str) -> str:
    if variable == METRICS_ENDPOINT_VARIABLE:
        return url
    return f"{url.rstrip('/')}/{METRICS_PATH}"


# @spec TEL-026, TEL-027, TEL-028, TEL-029, TEL-030, TEL-031, TEL-032, TEL-033, TEL-034
# @spec TEL-035, TEL-036, TEL-037, TEL-038
def telemetry_settings_from(
    environ: Mapping[str, str], *, instance_id: Callable[[], str] = _random_instance_id
) -> TelemetrySettings | TelemetryProblem:
    """The telemetry settings named in `environ`, or the first setting that cannot be used.

    Settings that will not be used are not checked: with telemetry turned off, neither the
    endpoint, the protocol nor the interval is; with no endpoint, neither of the latter two.
    """
    exporter = _set(environ, EXPORTER_VARIABLE)
    if exporter is not None and exporter.lower() not in EXPORTERS:
        return TelemetryProblem(f"{EXPORTER_VARIABLE} is {exporter!r}; it must be otlp or none")
    attributes = _resource_attributes(environ, instance_id)
    disabled = (_set(environ, DISABLED_VARIABLE) or "").lower() == "true"
    turned_off = disabled or (exporter or "").lower() == "none"
    endpoint = _in_effect(environ, METRICS_ENDPOINT_VARIABLE, ENDPOINT_VARIABLE)
    if turned_off or endpoint is None:
        return TelemetrySettings(None, DEFAULT_INTERVAL_MILLIS, attributes)
    endpoint_variable, url = endpoint
    if not _is_http_url(url):
        return TelemetryProblem(
            f"{endpoint_variable} is {url!r}; it must be an http:// or https:// URL with a host"
        )
    protocol = _in_effect(environ, METRICS_PROTOCOL_VARIABLE, PROTOCOL_VARIABLE)
    if protocol is not None and protocol[1].lower() != PROTOCOL:
        return TelemetryProblem(
            f"{protocol[0]} is {protocol[1]!r}; the service pushes only {PROTOCOL}"
        )
    interval_text = _set(environ, INTERVAL_VARIABLE)
    interval = DEFAULT_INTERVAL_MILLIS
    if interval_text is not None:
        if not re.fullmatch(r"[0-9]+", interval_text.strip()) or int(interval_text) <= 0:
            return TelemetryProblem(
                f"{INTERVAL_VARIABLE} is {interval_text!r}; it must be a whole number of"
                " milliseconds greater than zero"
            )
        interval = int(interval_text)
    return TelemetrySettings(_push_url(endpoint_variable, url), interval, attributes)


# @spec TEL-024, TEL-026, TEL-027, TEL-028, TEL-029, TEL-034
def meter_provider_for(settings: TelemetrySettings) -> MeterProvider:
    """A meter provider over the settings' resource, pushing over OTLP/HTTP with protobuf on a
    periodic reader when export is on, and with no reader otherwise.

    The exporter reads the push headers and timeout from the environment itself.
    """
    readers: list[MetricReader] = []
    if settings.endpoint is not None:
        readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=settings.endpoint),
                export_interval_millis=settings.interval_millis,
            )
        )
    return meter_provider(readers=readers, resource=Resource(dict(settings.resource_attributes)))
