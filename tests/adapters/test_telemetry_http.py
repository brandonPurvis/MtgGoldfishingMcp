"""The HTTP middleware: one measurement of each HTTP request the application receives, with
its route, status code and error type, and never a change to how the request goes on."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, MutableMapping
from typing import Any

import anyio
import anyio.lowlevel
import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from mtg_goldfishing.adapters.telemetry import HttpMeasurement, ServiceMetrics, meter_provider
from tests.support.telemetry import Measured, SteppedClock, measured

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

HTTP_REQUESTS = "http.server.request.duration"
ROUTES = frozenset({"/mcp", "/health"})


class HandlerFailed(Exception):
    """The application's own failure while handling a request."""


class RecordingBroke(Exception):
    """A failure inside the service metrics while recording."""


HANDLER_FAILED = f"{HandlerFailed.__module__}.{HandlerFailed.__qualname__}"


def _http_scope(path: str = "/health", method: str = "GET", scheme: str = "http") -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": scheme,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 50000),
    }


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _start(send: Send, status: int) -> None:
    await send({"type": "http.response.start", "status": status, "headers": []})


async def _body(send: Send) -> None:
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


def _responding(status: int = 200) -> App:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await _start(send, status)
        await _body(send)

    return app


def _raising(failure: Exception, *, after_starting: int | None = None) -> App:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if after_starting is not None:
            await _start(send, after_starting)
        raise failure

    return app


async def _returning_without_a_response(scope: Scope, receive: Receive, send: Send) -> None:
    return


class Measuring:
    """An application wrapped in the HTTP middleware over service metrics read back in memory."""

    def __init__(
        self,
        app: App,
        *,
        routes: Collection[str] = ROUTES,
        clock: SteppedClock | None = None,
        metrics: Callable[[InMemoryMetricReader], ServiceMetrics] | None = None,
    ) -> None:
        self.reader = InMemoryMetricReader()
        self.clock = clock or SteppedClock()
        self.metrics = (
            ServiceMetrics(meter_provider(readers=[self.reader]))
            if metrics is None
            else metrics(self.reader)
        )
        self.middleware = HttpMeasurement(
            app, metrics=self.metrics, routes=routes, timer=self.clock
        )
        self.sent: list[Message] = []

    async def request(self, scope: Scope | None = None) -> None:
        async def send(message: Message) -> None:
            self.sent.append(message)

        await self.middleware(scope or _http_scope(), _receive, send)

    def measured(self) -> list[Measured]:
        return measured(self.reader, HTTP_REQUESTS)

    def attributes(self) -> dict[str, object]:
        [point] = self.measured()
        return dict(point.attributes)


async def _failed_request(measuring: Measuring) -> None:
    with pytest.raises(HandlerFailed):
        await measuring.request()


async def _cancelled_request(
    *, started: int | None = None, clock: SteppedClock | None = None
) -> tuple[Measuring, bool]:
    """A request whose application is cancelled, after starting a response with `started`
    if given; with whether the cancellation reached the caller."""
    with anyio.CancelScope() as cancel_scope:

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if started is not None:
                await _start(send, started)
            if clock is not None:
                clock.advance(0.5)
            cancel_scope.cancel()
            await anyio.lowlevel.checkpoint()

        measuring = Measuring(app, clock=clock)
        await measuring.request()
    return measuring, cancel_scope.cancelled_caught


# ------------------------------------------------------------------ one measurement per request


# @spec TEL-010
async def test_an_http_request_is_one_measurement_of_the_request_duration() -> None:
    measuring = Measuring(_responding())

    await measuring.request()

    assert [point.count for point in measuring.measured()] == [1]


# @spec TEL-010
async def test_http_request_durations_are_in_seconds() -> None:
    measuring = Measuring(_responding())

    await measuring.request()

    assert [point.unit for point in measuring.measured()] == ["s"]


# @spec TEL-010
async def test_a_request_is_timed_from_receiving_it_until_the_application_returned() -> None:
    clock = SteppedClock()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        clock.advance(1.0)
        await _start(send, 200)
        await _body(send)
        clock.advance(1.5)

    measuring = Measuring(app, clock=clock)

    await measuring.request()

    assert [point.total for point in measuring.measured()] == [2.5]


# @spec TEL-010
async def test_a_request_is_timed_until_the_application_raised() -> None:
    clock = SteppedClock()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        clock.advance(0.75)
        raise HandlerFailed

    measuring = Measuring(app, clock=clock)

    await _failed_request(measuring)

    assert [point.total for point in measuring.measured()] == [0.75]


# @spec TEL-010
async def test_a_request_is_timed_until_the_application_was_cancelled() -> None:
    measuring, _ = await _cancelled_request(clock=SteppedClock())

    assert [point.total for point in measuring.measured()] == [0.5]


# @spec TEL-010
async def test_the_response_reaches_the_server_unchanged() -> None:
    measuring = Measuring(_responding(201))

    await measuring.request()

    assert measuring.sent == [
        {"type": "http.response.start", "status": 201, "headers": []},
        {"type": "http.response.body", "body": b"ok", "more_body": False},
    ]


# @spec TEL-010
@pytest.mark.parametrize("kind", ["lifespan", "websocket"])
async def test_an_event_that_is_not_an_http_request_reaches_the_application(kind: str) -> None:
    received: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        received.append(scope["type"])

    measuring = Measuring(app)

    await measuring.request({"type": kind, "asgi": {"version": "3.0"}})

    assert received == [kind]


# @spec TEL-010
@pytest.mark.parametrize("kind", ["lifespan", "websocket"])
async def test_an_event_that_is_not_an_http_request_is_not_measured(kind: str) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        return

    measuring = Measuring(app)

    await measuring.request({"type": kind, "asgi": {"version": "3.0"}})

    assert measuring.measured() == []


# ------------------------------------------------------------------ attributes


# @spec TEL-012
@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_the_request_s_scheme_is_recorded(scheme: str) -> None:
    measuring = Measuring(_responding())

    await measuring.request(_http_scope(scheme=scheme))

    assert measuring.attributes()["url.scheme"] == scheme


# @spec TEL-011
async def test_the_request_s_method_is_recorded() -> None:
    measuring = Measuring(_responding())

    await measuring.request(_http_scope(method="POST"))

    assert measuring.attributes()["http.request.method"] == "POST"


# @spec TEL-013
@pytest.mark.parametrize("path", ["/mcp", "/health"])
async def test_a_measured_route_is_recorded_as_its_path(path: str) -> None:
    measuring = Measuring(_responding())

    await measuring.request(_http_scope(path))

    assert measuring.attributes()["http.route"] == path


# @spec TEL-013
@pytest.mark.parametrize("path", ["/mcp/", "/", "/health/deep", "/MCP", "/elsewhere"])
async def test_any_other_path_is_recorded_as_other(path: str) -> None:
    measuring = Measuring(_responding())

    await measuring.request(_http_scope(path))

    assert measuring.attributes()["http.route"] == "other"


# @spec TEL-013
@pytest.mark.parametrize(("path", "route"), [("/games", "/games"), ("/mcp", "other")])
async def test_the_measured_routes_are_the_ones_the_middleware_was_given(
    path: str, route: str
) -> None:
    measuring = Measuring(_responding(), routes={"/games"})

    await measuring.request(_http_scope(path))

    assert measuring.attributes()["http.route"] == route


# @spec TEL-014
@pytest.mark.parametrize("status", [200, 404, 503])
async def test_the_status_code_of_the_response_started_is_recorded(status: int) -> None:
    measuring = Measuring(_responding(status))

    await measuring.request()

    assert measuring.attributes()["http.response.status_code"] == status


# @spec TEL-014, TEL-017
async def test_a_response_started_before_the_application_raised_keeps_its_status_code() -> None:
    measuring = Measuring(_raising(HandlerFailed(), after_starting=200))

    await _failed_request(measuring)

    assert measuring.attributes()["http.response.status_code"] == 200


# @spec TEL-015
async def test_an_application_that_raised_before_responding_is_recorded_as_500() -> None:
    measuring = Measuring(_raising(HandlerFailed()))

    await _failed_request(measuring)

    assert measuring.attributes()["http.response.status_code"] == 500


# @spec TEL-015
async def test_an_application_that_returned_without_responding_is_recorded_as_500() -> None:
    measuring = Measuring(_returning_without_a_response)

    await measuring.request()

    assert measuring.attributes()["http.response.status_code"] == 500


# @spec TEL-016
async def test_a_request_cancelled_before_responding_is_recorded_without_a_status_code() -> None:
    measuring, _ = await _cancelled_request()

    assert "http.response.status_code" not in measuring.attributes()


# @spec TEL-014
async def test_a_request_cancelled_after_responding_keeps_its_status_code() -> None:
    measuring, _ = await _cancelled_request(started=200)

    assert measuring.attributes()["http.response.status_code"] == 200


# ------------------------------------------------------------------ error type


# @spec TEL-017
@pytest.mark.parametrize("after_starting", [None, 200], ids=["before responding", "after"])
async def test_an_application_that_raised_is_recorded_with_the_exception_s_class(
    after_starting: int | None,
) -> None:
    measuring = Measuring(_raising(HandlerFailed(), after_starting=after_starting))

    await _failed_request(measuring)

    assert measuring.attributes()["error.type"] == HANDLER_FAILED


# @spec TEL-017
async def test_a_built_in_exception_is_recorded_by_its_bare_class_name() -> None:
    measuring = Measuring(_raising(ValueError("no such card")))

    with pytest.raises(ValueError, match="no such card"):
        await measuring.request()

    assert measuring.attributes()["error.type"] == "ValueError"


# @spec TEL-017
@pytest.mark.parametrize("after_starting", [None, 200], ids=["before responding", "after"])
async def test_the_application_s_exception_goes_on_as_the_same_exception(
    after_starting: int | None,
) -> None:
    failure = HandlerFailed()
    measuring = Measuring(_raising(failure, after_starting=after_starting))

    with pytest.raises(HandlerFailed) as raised:
        await measuring.request()

    assert raised.value is failure


# @spec TEL-018
@pytest.mark.parametrize("started", [None, 200], ids=["before responding", "after"])
async def test_a_cancellation_goes_on_after_the_request_is_recorded(started: int | None) -> None:
    _, cancellation_went_on = await _cancelled_request(started=started)

    assert cancellation_went_on


# @spec TEL-018
async def test_a_request_cancelled_before_responding_is_recorded_as_cancelled() -> None:
    measuring, _ = await _cancelled_request()

    assert measuring.attributes()["error.type"] == "cancelled"


# @spec TEL-018, TEL-019
async def test_a_request_cancelled_after_a_successful_response_started_has_no_error_type() -> None:
    measuring, _ = await _cancelled_request(started=200)

    assert "error.type" not in measuring.attributes()


# @spec TEL-019
async def test_a_request_cancelled_after_a_server_error_started_has_its_code_as_error_type() -> (
    None
):
    measuring, _ = await _cancelled_request(started=503)

    assert measuring.attributes()["error.type"] == "503"


# @spec TEL-019
@pytest.mark.parametrize("status", [500, 503, 599])
async def test_a_server_error_response_has_its_status_code_as_error_type(status: int) -> None:
    measuring = Measuring(_responding(status))

    await measuring.request()

    assert measuring.attributes()["error.type"] == str(status)


# @spec TEL-015, TEL-019
async def test_an_application_that_returned_without_responding_has_500_as_error_type() -> None:
    measuring = Measuring(_returning_without_a_response)

    await measuring.request()

    assert measuring.attributes()["error.type"] == "500"


# @spec TEL-019
@pytest.mark.parametrize("status", [200, 302, 404, 499])
async def test_a_response_below_500_has_no_error_type(status: int) -> None:
    measuring = Measuring(_responding(status))

    await measuring.request()

    assert "error.type" not in measuring.attributes()


# ------------------------------------------------------------------ recording that fails


class RecordingFails(ServiceMetrics):
    """Service metrics that raise whenever they record an HTTP request."""

    def __init__(self, reader: InMemoryMetricReader, failure: RecordingBroke) -> None:
        super().__init__(meter_provider(readers=[reader]))
        self.failure = failure

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
        raise self.failure


def _failing_to_record(app: App, failure: RecordingBroke | None = None) -> Measuring:
    broke = failure or RecordingBroke()
    return Measuring(app, metrics=lambda reader: RecordingFails(reader, broke))


# @spec TEL-020
async def test_a_response_goes_on_when_recording_raises() -> None:
    measuring = _failing_to_record(_responding(201))

    await measuring.request()

    assert [message["type"] for message in measuring.sent] == [
        "http.response.start",
        "http.response.body",
    ]


# @spec TEL-020
async def test_the_application_s_exception_goes_on_when_recording_raises() -> None:
    failure = HandlerFailed()
    measuring = _failing_to_record(_raising(failure))

    with pytest.raises(HandlerFailed) as raised:
        await measuring.request()

    assert raised.value is failure


# @spec TEL-020
async def test_a_cancellation_goes_on_when_recording_raises() -> None:
    with anyio.CancelScope() as cancel_scope:

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            cancel_scope.cancel()
            await anyio.lowlevel.checkpoint()

        await _failing_to_record(app).request()

    assert cancel_scope.cancelled_caught


# @spec TEL-020
async def test_a_failure_to_record_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    failure = RecordingBroke()
    measuring = _failing_to_record(_responding(), failure)

    await measuring.request()

    assert any(
        record.name.startswith("mtg_goldfishing")
        and record.exc_info is not None
        and record.exc_info[1] is failure
        for record in caplog.records
    )
