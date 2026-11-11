"""MCP clients over HTTP for playing the seats of a game from synchronous code, as separate
agents would: one client, with its own connection, for each player.

    clients = SeatClients(service.url)
    answer = clients.call("S2", "wait", {"game_id": seat_id})
    pending = clients.send("S3", "wait", {"game_id": other_id})   # answered later
    clients.close()

Every client runs on one event loop in a thread of its own, so a call one client has sent
(a `wait`, say) stays open while another client's calls are made and answered.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from mcp import Client
from mcp.types import CallToolResult, TextContent

CALL_TIMEOUT = 90.0
"""Seconds a step waits for any one answer; longer than the longest `wait` (60 seconds)."""


@dataclass(frozen=True)
class Answer:
    """What a tool call answered: its one text item and the MCP error flag."""

    text: str
    is_error: bool


def _answer(result: CallToolResult) -> Answer:
    texts = [item.text for item in result.content if isinstance(item, TextContent)]
    assert len(texts) == len(result.content) == 1, result
    return Answer(texts[0], bool(result.is_error))


_Request = tuple[str, dict[str, object], "asyncio.Future[Answer]"]


class _Connection:
    """One player's client, open for as long as it is used, serving its calls in order."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._requests: asyncio.Queue[_Request | None] = asyncio.Queue()

    async def serve(self) -> None:
        async with Client(self._url) as client:
            while (request := await self._requests.get()) is not None:
                tool, arguments, answered = request
                try:
                    result = await client.call_tool(tool, arguments)
                except Exception as problem:  # handed to the caller, who reports it
                    answered.set_exception(problem)
                else:
                    answered.set_result(_answer(result))

    async def ask(self, tool: str, arguments: dict[str, object]) -> Answer:
        answered: asyncio.Future[Answer] = asyncio.get_running_loop().create_future()
        await self._requests.put((tool, arguments, answered))
        return await answered

    async def close(self) -> None:
        await self._requests.put(None)


class SeatClients:
    """A client per player, created on its first call and named by the caller ("S2")."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._lock = threading.Lock()
        self._connections: dict[str, _Connection] = {}
        self._serving: dict[str, concurrent.futures.Future[None]] = {}

    def _connection(self, who: str) -> _Connection:
        with self._lock:
            if who not in self._connections:
                connection = _Connection(self._url)
                self._connections[who] = connection
                self._serving[who] = asyncio.run_coroutine_threadsafe(
                    connection.serve(), self._loop
                )
            serving = self._serving[who]
            if serving.done():
                serving.result()  # the client could not connect, or failed: say why
            return self._connections[who]

    def send(
        self, who: str, tool: str, arguments: Mapping[str, object]
    ) -> concurrent.futures.Future[Answer]:
        """Send a call through `who`'s client and return at once; the answer comes later."""
        connection = self._connection(who)
        return asyncio.run_coroutine_threadsafe(connection.ask(tool, dict(arguments)), self._loop)

    def call(self, who: str, tool: str, arguments: Mapping[str, object]) -> Answer:
        """Send a call through `who`'s client and return its answer."""
        return self.send(who, tool, arguments).result(timeout=CALL_TIMEOUT)

    def close(self) -> None:
        """Close every client, then stop the event loop."""
        for who, connection in self._connections.items():
            asyncio.run_coroutine_threadsafe(connection.close(), self._loop).result(10)
            # A client that failed has already reported it to its caller.
            with contextlib.suppress(Exception):
                self._serving[who].result(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
        self._loop.close()
