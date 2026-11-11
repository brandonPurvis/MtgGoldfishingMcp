"""The card catalog on Scryfall's collection endpoint, in front of a card cache."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from mtg_goldfishing import __version__
from mtg_goldfishing.adapters.scryfall.conversion import read_scryfall_card
from mtg_goldfishing.application.ports import CardCache, CardCatalog
from mtg_goldfishing.domain.cards import (
    Card,
    CardLookup,
    LookupStatus,
    name_match,
    resolve_name,
    split_at_slash_separators,
)

COLLECTION_URL = "https://api.scryfall.com/cards/collection"
BATCH_SIZE = 75
"""The most identifiers the collection endpoint takes in one request."""
REQUEST_SPACING = 0.1
"""Seconds between the starts of any two requests made by this process."""
TIMEOUT = 10.0
BACKOFF = (1.0, 2.0, 4.0)
"""Seconds to wait before each retry of a rate-limited or server-failed request, in turn."""
LONGEST_RETRY_AFTER = 20.0
"""The most seconds an attempt waits for a `Retry-After`; one that would wait longer is not sent."""
HEADERS = {"User-Agent": f"mtg-goldfishing/{__version__}", "Accept": "application/json"}

_WHOLE_SECONDS = re.compile(r"[0-9]+")

Sleep = Callable[[float], None]
Monotonic = Callable[[], float]
Now = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class RequestSpacing:
    """When requests may start, for all who share it.

    The starts of requests are kept at least `interval` seconds apart, and none starts
    while a `Retry-After` from Scryfall holds.
    """

    def __init__(self, interval: float = REQUEST_SPACING) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._last_start: float | None = None
        self._held_until: float | None = None

    def hold_until(self, moment: float) -> None:
        """Start no request before this monotonic time."""
        with self._lock:
            if self._held_until is None or moment > self._held_until:
                self._held_until = moment

    def held_for(self, monotonic: Monotonic) -> float:
        """The seconds still to wait before the hold ends; 0 when nothing holds."""
        with self._lock:
            return self._still_held(monotonic())

    def _still_held(self, now: float) -> float:
        return 0.0 if self._held_until is None else max(0.0, self._held_until - now)

    def wait_turn(self, sleep: Sleep, monotonic: Monotonic, *, longest_hold: float) -> bool:
        """Wait until a request may start, and record that it starts now.

        False, without waiting or recording a start, when a hold has longer than
        `longest_hold` seconds still to run.
        """
        with self._lock:
            now = monotonic()
            held = self._still_held(now)
            if held > longest_hold:
                return False
            spaced = 0.0
            if self._last_start is not None:
                spaced = min(self._interval, self._last_start + self._interval - now)
            wait = max(spaced, held)
            if wait > 0:
                sleep(wait)
            self._last_start = monotonic()
            return True


PROCESS_SPACING = RequestSpacing()
"""The spacing every catalog in the process shares unless given its own."""


def _key(name: str) -> str:
    return name.strip().casefold()


def _spellings(name: str) -> list[str]:
    """The name identifiers a requested name is asked for by: as given, and its first part.

    The collection endpoint finds a multi-face card by a face name but not by its full name,
    so a name with slash separators is also asked for by the part before the first one.
    """
    given = name.strip()
    parts = split_at_slash_separators(given)
    return [given, parts[0]] if len(parts) > 1 and parts[0] else [given]


def _batches(names: Sequence[str]) -> Iterable[list[str]]:
    """The names in groups whose spellings together fill no more than one request."""
    batch: list[str] = []
    identifiers = 0
    for name in names:
        count = len(_spellings(name))
        if batch and identifiers + count > BATCH_SIZE:
            yield batch
            batch, identifiers = [], 0
        batch.append(name)
        identifiers += count
    if batch:
        yield batch


def _should_retry(status: int) -> bool:
    return status == httpx.codes.TOO_MANY_REQUESTS or status >= 500


# @spec CARD-027, CARD-028
def retry_after_seconds(value: str | None, now: datetime) -> float | None:
    """The seconds a `Retry-After` header asks for, or None when it cannot be read.

    Either a whole number of seconds or an HTTP date, measured against `now`; a date
    already past asks for none.
    """
    if value is None:
        return None
    text = value.strip()
    if _WHOLE_SECONDS.fullmatch(text):
        return float(text)
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - now).total_seconds())


def _names_in(data: object) -> tuple[str, list[str]] | None:
    """The full name and face names a raw Scryfall card object claims, as far as readable."""
    if not isinstance(data, Mapping) or not isinstance(data.get("name"), str):
        return None
    faces = data.get("card_faces")
    face_names = [
        entry["name"]
        for entry in (faces if isinstance(faces, list) else [])
        if isinstance(entry, Mapping) and isinstance(entry.get("name"), str)
    ]
    return data["name"], face_names or [data["name"]]


class ScryfallCatalog(CardCatalog):
    """Supplies card data by exact name from the cache, fetching what is missing from Scryfall."""

    def __init__(
        self,
        cache: CardCache,
        *,
        client: httpx.Client | None = None,
        sleep: Sleep = time.sleep,
        monotonic: Monotonic = time.monotonic,
        now: Now = utc_now,
        spacing: RequestSpacing | None = None,
    ) -> None:
        self._cache = cache
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=TIMEOUT)
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._spacing = spacing if spacing is not None else PROCESS_SPACING

    def close(self) -> None:
        """Release the HTTP client, if this catalog made it."""
        if self._owns_client:
            self._client.close()

    # @spec CARD-008, CARD-011, CARD-012, CARD-013, CARD-015, CARD-016, CARD-017, CARD-018
    # @spec CARD-019, CARD-021, CARD-022, CARD-023, CARD-024
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
        answer = self._request([spelling for name in batch for spelling in _spellings(name)])
        if isinstance(answer, LookupStatus):
            return {_key(name): CardLookup(answer) for name in batch}
        cards: list[Card] = []
        unreadable: list[tuple[str, list[str]]] = []
        for data in answer:
            card = read_scryfall_card(data) if isinstance(data, Mapping) else None
            if card is not None:
                cards.append(card)
            elif (claimed := _names_in(data)) is not None:
                unreadable.append(claimed)
        outcomes: dict[str, CardLookup] = {}
        for name in batch:
            match = resolve_name(name, cards)
            if match is not None:
                self._cache.put(match)
                outcomes[_key(name)] = CardLookup(LookupStatus.FOUND, match)
            elif any(name_match(name, full, faces) for full, faces in unreadable):
                outcomes[_key(name)] = CardLookup(LookupStatus.UNAVAILABLE)
            else:
                outcomes[_key(name)] = CardLookup(LookupStatus.NOT_FOUND)
        return outcomes

    # @spec CARD-013, CARD-014, CARD-026, CARD-029, CARD-031
    def _request(self, identifiers: Sequence[str]) -> list[Any] | LookupStatus:
        """The card objects Scryfall returned for one request, or why there are none.

        A 429 or server error is retried up to three times, each retry waiting the longer of
        its backoff and the failed response's `Retry-After`; an attempt that fails to
        complete, or is refused for another reason, ends the request.
        """
        response: httpx.Response | None = None
        due = self._monotonic()
        for attempt in range(len(BACKOFF) + 1):
            if attempt > 0:
                due = self._monotonic() + BACKOFF[attempt - 1]
            if not self._wait_until_sendable(due):
                return LookupStatus.UNAVAILABLE
            response = self._send(identifiers)
            if response is None or not _should_retry(response.status_code):
                break
            self._hold_for_retry_after(response)
        if response is None or _should_retry(response.status_code):
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

    # @spec CARD-010, CARD-029, CARD-030
    def _wait_until_sendable(self, due: float) -> bool:
        """Wait until an attempt due at `due` may start; False when a hold is too long to wait."""
        if self._spacing.held_for(self._monotonic) > LONGEST_RETRY_AFTER:
            return False
        backoff = due - self._monotonic()
        if backoff > 0:
            self._sleep(backoff)
        return self._spacing.wait_turn(
            self._sleep, self._monotonic, longest_hold=LONGEST_RETRY_AFTER
        )

    def _hold_for_retry_after(self, response: httpx.Response) -> None:
        """Hold back every request in the process for as long as the response's `Retry-After`."""
        seconds = retry_after_seconds(response.headers.get("Retry-After"), self._now())
        if seconds:
            self._spacing.hold_until(self._monotonic() + seconds)

    # @spec CARD-009
    def _send(self, identifiers: Sequence[str]) -> httpx.Response | None:
        """One request to the collection endpoint, or None when it could not complete."""
        try:
            return self._client.post(
                COLLECTION_URL,
                json={"identifiers": [{"name": name} for name in identifiers]},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
        except httpx.HTTPError:
            return None
