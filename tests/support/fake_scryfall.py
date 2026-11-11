"""A stand-in for Scryfall's collection endpoint, served through an httpx mock transport."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tests.support.card_data import recorded_scryfall_json

COLLECTION_URL = "https://api.scryfall.com/cards/collection"


WALL_START = datetime(2026, 1, 1, tzinfo=UTC)
"""The wall-clock time a `FakeTime` tells before anything sleeps on it."""


class FakeTime:
    """A monotonic clock, and a wall clock in step with it, that only move when told to."""

    def __init__(self, start: float = 1000.0) -> None:
        self.start = start
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def wall(self) -> datetime:
        """The wall-clock time: `WALL_START` plus however far the monotonic clock has moved."""
        return WALL_START + timedelta(seconds=self.now - self.start)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(seconds, 0.0)

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _names_of(card: dict[str, Any]) -> list[str]:
    """The names the collection endpoint finds a card by: its face names, if it lists faces."""
    faces = card.get("card_faces", [])
    return [face["name"] for face in faces] if faces else [card["name"]]


def refusal(status: int, retry_after: str | None = None) -> httpx.Response:
    """An error response from Scryfall, with a `Retry-After` header when one is given."""
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    return httpx.Response(status, json={"object": "error", "status": status}, headers=headers)


class FakeScryfall:
    """Answers the collection endpoint from Scryfall card objects, the way Scryfall does.

    Like Scryfall's collection endpoint, it matches a name identifier case-insensitively
    to a single-faced card by its name and to a card that lists faces by any one face name,
    never by that card's full name; it returns one data entry per found identifier, the
    same card again for each identifier finding it, and lists the rest under `not_found`.
    Tests can script failures and substitute cards.
    """

    def __init__(
        self,
        cards: Iterable[dict[str, Any]] | None = None,
        *,
        time: FakeTime | None = None,
    ) -> None:
        self.cards = list(recorded_scryfall_json() if cards is None else cards)
        self.time = time
        self.requests: list[httpx.Request] = []
        self.request_times: list[float] = []
        self._scripted: deque[int | Exception | httpx.Response] = deque()
        self._failing_names: dict[str, httpx.Response] = {}
        self._substitutes: dict[str, dict[str, Any]] = {}

    # Arranging

    def fail_next(self, *outcomes: int | Exception | httpx.Response) -> None:
        """Answer the next requests with these statuses or responses, or raise these errors."""
        self._scripted.extend(outcomes)

    def fail_requests_naming(
        self, *names: str, status: int = 503, retry_after: str | None = None
    ) -> None:
        """Answer `status` to every request that asks for any of these names."""
        self._failing_names.update(
            (name.casefold(), refusal(status, retry_after)) for name in names
        )

    def answer_with(self, name: str, card: dict[str, Any]) -> None:
        """Return `card` for the identifier `name`, whatever its name, as a loose match would."""
        self._substitutes[name.casefold()] = card

    def replace_card(self, card: dict[str, Any]) -> None:
        """Serve `card` in place of the card with the same full name."""
        self.cards = [c for c in self.cards if c["name"] != card["name"]] + [card]

    # Inspecting

    def requested_names(self, index: int) -> list[str]:
        body = json.loads(self.requests[index].content)
        return [identifier["name"] for identifier in body["identifiers"]]

    def all_requested_names(self) -> list[str]:
        return [name for index in range(len(self.requests)) for name in self.requested_names(index)]

    # Serving

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.time is not None:
            self.request_times.append(self.time.monotonic())
        if self._scripted:
            outcome = self._scripted.popleft()
            if isinstance(outcome, Exception):
                raise outcome
            return outcome if isinstance(outcome, httpx.Response) else refusal(outcome)
        if request.method != "POST" or str(request.url) != COLLECTION_URL:
            return httpx.Response(404, json={"object": "error", "status": 404})
        names = [identifier["name"] for identifier in json.loads(request.content)["identifiers"]]
        failing = next(
            (
                self._failing_names[n.casefold()]
                for n in names
                if n.casefold() in self._failing_names
            ),
            None,
        )
        if failing is not None:
            return refusal(failing.status_code, failing.headers.get("Retry-After"))
        data: list[dict[str, Any]] = []
        not_found: list[dict[str, str]] = []
        for name in names:
            card = self._find(name)
            if card is None:
                not_found.append({"name": name})
            else:
                data.append(card)
        return httpx.Response(200, json={"object": "list", "not_found": not_found, "data": data})

    def _find(self, name: str) -> dict[str, Any] | None:
        if name.casefold() in self._substitutes:
            return self._substitutes[name.casefold()]
        for card in self.cards:
            if any(name.casefold() == known.casefold() for known in _names_of(card)):
                return card
        return None
