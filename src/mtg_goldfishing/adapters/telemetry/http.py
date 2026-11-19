"""The HTTP middleware: one measurement of each HTTP request the wrapped application receives."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Collection

import anyio
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mtg_goldfishing.adapters.telemetry.metrics import ServiceMetrics

_log = logging.getLogger(__name__)

OTHER_ROUTE = "other"
CANCELLED = "cancelled"
SERVER_ERROR = 500
"""What the server sends when the application raised or returned without responding."""


def _error_type(failure: Exception) -> str:
    """The exception's fully qualified class name; a built-in exception's bare name."""
    kind = type(failure)
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"


class HttpMeasurement:
    """ASGI middleware measuring every HTTP request the wrapped application receives.

    A request's path is its `http.route` when it is one of the measured `routes`, else
    `other`. Requests of any other type, such as `lifespan`, pass through unmeasured.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics: ServiceMetrics,
        routes: Collection[str],
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._app = app
        self._metrics = metrics
        self._routes = frozenset(routes)
        self._timer = timer

    # @spec TEL-010, TEL-012, TEL-013, TEL-014, TEL-015, TEL-016, TEL-017, TEL-018, TEL-019
    # @spec TEL-020
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = self._timer()
        response_status: list[int] = []

        async def sending(message: Message) -> None:
            if message["type"] == "http.response.start" and not response_status:
                response_status.append(int(message["status"]))
            await send(message)

        try:
            await self._app(scope, receive, sending)
        except anyio.get_cancelled_exc_class():
            if response_status:
                self._record(scope, started, response_status[0], None)
            else:
                self._record(scope, started, None, CANCELLED)
            raise
        except Exception as failure:
            status_code = response_status[0] if response_status else SERVER_ERROR
            self._record(scope, started, status_code, _error_type(failure))
            raise
        self._record(scope, started, response_status[0] if response_status else SERVER_ERROR, None)

    def _record(
        self, scope: Scope, started: float, status_code: int | None, error_type: str | None
    ) -> None:
        """Record the request; a status code of 500 or above with no other error type is its
        own error type. A failure to record is logged and goes no further."""
        if error_type is None and status_code is not None and status_code >= SERVER_ERROR:
            error_type = str(status_code)
        try:
            path = scope.get("path", "")
            self._metrics.record_http_request(
                method=scope.get("method", ""),
                scheme=scope.get("scheme", "http"),
                route=path if path in self._routes else OTHER_ROUTE,
                status_code=status_code,
                error_type=error_type,
                seconds=self._timer() - started,
            )
        except Exception:
            _log.exception("recording an HTTP request failed")
