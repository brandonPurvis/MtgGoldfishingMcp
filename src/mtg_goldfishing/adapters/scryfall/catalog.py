"""The card catalog on Scryfall's collection endpoint, in front of a card cache."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import httpx

from mtg_goldfishing import __version__
from mtg_goldfishing.adapters.scryfall.conversion import read_scryfall_card
from mtg_goldfishing.application.ports import CardCache
from mtg_goldfishing.domain.cards import Card, CardLookup, LookupStatus, same_name

COLLECTION_URL = "https://api.scryfall.com/cards/collection"
BATCH_SIZE = 75
"""The most identifiers the collection endpoint takes in one request."""
REQUEST_SPACING = 0.1
"""Seconds between the starts of any two requests made by this process."""
TIMEOUT = 10.0
RETRY_DELAY = 1.0
HEADERS = {"User-Agent": f"mtg-goldfishing/{__version__}", "Accept": "application/json"}

Sleep = Callable[[float], None]
Monotonic = Callable[[], float]


class RequestSpacing:
    """Keeps the starts of requests at least `interval` seconds apart for all who share it."""

    def __init__(self, interval: float = REQUEST_SPACING) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._last_start: float | None = None

    def wait_turn(self, sleep: Sleep, monotonic: Monotonic) -> None:
        """Wait until a request may start, and record that it starts now."""
        with self._lock:
            if self._last_start is not None:
                wait = min(self._interval, self._last_start + self._interval - monotonic())
                if wait > 0:
                    sleep(wait)
            self._last_start = monotonic()


PROCESS_SPACING = RequestSpacing()
"""The spacing every catalog in the process shares unless given its own."""


def _key(name: str) -> str:
    return name.strip().casefold()


def _batches(names: Sequence[str]) -> Iterable[Sequence[str]]:
    for start in range(0, len(names), BATCH_SIZE):
        yield names[start : start + BATCH_SIZE]


def _should_retry(status: int) -> bool:
    return status == httpx.codes.TOO_MANY_REQUESTS or status >= 500


def _names_in(data: object) -> list[str]:
    """The full name and face names a raw Scryfall card object claims, as far as readable."""
    if not isinstance(data, Mapping):
        return []
    faces = data.get("card_faces")
    entries = [data, *(faces if isinstance(faces, list) else [])]
    return [
        entry["name"]
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("name"), str)
    ]


class ScryfallCatalog:
    """Supplies card data by exact name from the cache, fetching what is missing from Scryfall."""

    def __init__(
        self,
        cache: CardCache,
        *,
        client: httpx.Client | None = None,
        sleep: Sleep = time.sleep,
        monotonic: Monotonic = time.monotonic,
        spacing: RequestSpacing | None = None,
    ) -> None:
        self._cache = cache
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=TIMEOUT)
        self._sleep = sleep
        self._monotonic = monotonic
        self._spacing = spacing if spacing is not None else PROCESS_SPACING

    def close(self) -> None:
        """Release the HTTP client, if this catalog made it."""
        if self._owns_client:
            self._client.close()

    # @spec CARD-008, CARD-011, CARD-012, CARD-013, CARD-015, CARD-016, CARD-017, CARD-018
    # @spec CARD-019
    def look_up(self, names: Iterable[str], *, refresh: bool = False) -> Mapping[str, CardLookup]:
        """For each requested name, as given: the card, not found, or unavailable."""
        requested = list(names)
        cached: dict[str, Card] = {}
        to_fetch: dict[str, str] = {}
        for name in requested:
            if not name.strip():
                continue
            card = self._cache.get(name)
            if card is not None:
                cached[name] = card
            if card is None or refresh:
                to_fetch.setdefault(_key(name), name.strip())
        fetched: dict[str, CardLookup] = {}
        for batch in _batches(list(to_fetch.values())):
            fetched.update(self._fetch(batch))
        return {name: self._outcome(name, cached, fetched) for name in requested}

    @staticmethod
    def _outcome(
        name: str, cached: Mapping[str, Card], fetched: Mapping[str, CardLookup]
    ) -> CardLookup:
        lookup = fetched.get(_key(name))
        kept = cached.get(name)
        if lookup is None:
            if kept is None:
                return CardLookup(LookupStatus.NOT_FOUND)
            return CardLookup(LookupStatus.FOUND, kept)
        if lookup.status is not LookupStatus.FOUND and kept is not None:
            return CardLookup(lookup.status, kept)
        return lookup

    def _fetch(self, batch: Sequence[str]) -> dict[str, CardLookup]:
        """Each name of one request's outcome, keyed by the name's lookup key."""
        answer = self._request(batch)
        if isinstance(answer, LookupStatus):
            return {_key(name): CardLookup(answer) for name in batch}
        cards: list[Card] = []
        unreadable: list[str] = []
        for data in answer:
            card = read_scryfall_card(data) if isinstance(data, Mapping) else None
            if card is None:
                unreadable.extend(_names_in(data))
            else:
                cards.append(card)
        outcomes: dict[str, CardLookup] = {}
        for name in batch:
            match = next((card for card in cards if card.matches(name)), None)
            if match is not None:
                self._cache.put(match)
                outcomes[_key(name)] = CardLookup(LookupStatus.FOUND, match)
            elif any(same_name(name, claimed) for claimed in unreadable):
                outcomes[_key(name)] = CardLookup(LookupStatus.UNAVAILABLE)
            else:
                outcomes[_key(name)] = CardLookup(LookupStatus.NOT_FOUND)
        return outcomes

    # @spec CARD-013, CARD-014
    def _request(self, batch: Sequence[str]) -> list[Any] | LookupStatus:
        """The card objects Scryfall returned for a batch, or why there are none."""
        response = self._send(batch)
        if response is not None and _should_retry(response.status_code):
            self._sleep(RETRY_DELAY)
            response = self._send(batch)
        if response is None:
            return LookupStatus.UNAVAILABLE
        if response.status_code == httpx.codes.NOT_FOUND:
            return LookupStatus.NOT_FOUND
        if not response.is_success:
            return LookupStatus.UNAVAILABLE
        try:
            body = response.json()
        except ValueError:
            return LookupStatus.UNAVAILABLE
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return LookupStatus.UNAVAILABLE
        return data

    # @spec CARD-009, CARD-010
    def _send(self, batch: Sequence[str]) -> httpx.Response | None:
        """One request to the collection endpoint, or None when it could not complete."""
        self._spacing.wait_turn(self._sleep, self._monotonic)
        try:
            return self._client.post(
                COLLECTION_URL,
                json={"identifiers": [{"name": name} for name in batch]},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
        except httpx.HTTPError:
            return None
