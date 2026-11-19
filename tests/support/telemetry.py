"""Measurements read back from OpenTelemetry's in-memory reader, timers whose readings a test
chooses, and an OTLP receiver on the loopback address that keeps every push sent to it.

reader = InMemoryMetricReader()
metrics = ServiceMetrics(meter_provider(readers=[reader]))
metrics.record_tool_call("play", "OK", 0.25)
[point] = measured(reader, "goldfishing.tool_call.duration")
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader


@dataclass(frozen=True)
class Measured:
    """One histogram data point: its attributes, how many measurements it holds and their
    sum, its bucket boundaries and its instrument's unit."""

    attributes: Mapping[str, object]
    count: int
    total: float
    bounds: tuple[float, ...]
    unit: str


def measured(reader: InMemoryMetricReader, instrument: str) -> list[Measured]:
    """Every data point the reader holds for the histogram named `instrument`."""
    data = reader.get_metrics_data()
    if data is None:
        return []
    found = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != instrument:
                    continue
                for point in metric.data.data_points:
                    assert isinstance(point, HistogramDataPoint), point
                    found.append(
                        Measured(
                            attributes=dict(point.attributes or {}),
                            count=point.count,
                            total=point.sum,
                            bounds=tuple(point.explicit_bounds),
                            unit=metric.unit or "",
                        )
                    )
    return found


class SteppedClock:
    """A monotonic timer that reads what the test set it to, counting how often it is read."""

    def __init__(self, reading: float = 100.0) -> None:
        self.reading = reading
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return self.reading

    def advance(self, seconds: float) -> None:
        self.reading += seconds

    def set(self, reading: float) -> None:
        self.reading = reading


class Readings:
    """A monotonic timer giving the chosen readings in turn, then the last one again."""

    def __init__(self, *readings: float) -> None:
        self._readings = list(readings)

    def __call__(self) -> float:
        if len(self._readings) > 1:
            return self._readings.pop(0)
        return self._readings[0]


@dataclass(frozen=True)
class Push:
    """One push of metrics received: the path it was sent to, its headers (names in lower
    case) and its body."""

    path: str
    headers: Mapping[str, str]
    body: bytes

    def resource_attributes(self) -> dict[str, str]:
        request = ExportMetricsServiceRequest()
        request.ParseFromString(self.body)
        return {
            attribute.key: attribute.value.string_value
            for resource_metrics in request.resource_metrics
            for attribute in resource_metrics.resource.attributes
        }


class OtlpReceiver:
    """Answers every push with success and keeps it."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.pushes: list[Push] = []
        self._arrived = threading.Event()

    def keep(self, push: Push) -> None:
        self.pushes.append(push)
        self._arrived.set()

    def wait_for_push(self, timeout: float) -> bool:
        return self._arrived.wait(timeout)


@contextmanager
def an_otlp_receiver() -> Iterator[OtlpReceiver]:
    """An OTLP/HTTP receiver listening on 127.0.0.1, until the block ends."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    receiver = OtlpReceiver(f"http://127.0.0.1:{server.server_address[1]}")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            headers = {name.lower(): value for name, value in self.headers.items()}
            receiver.keep(Push(self.path, headers, body))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server.RequestHandlerClass = Handler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield receiver
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def unreachable_endpoint() -> str:
    """A push URL on the loopback address where nothing is listening."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/v1/metrics"
