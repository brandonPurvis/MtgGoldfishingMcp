"""The Scryfall card catalog: batching, politeness, failures and the cache."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from mtg_goldfishing import __version__
from mtg_goldfishing.adapters.memory import InMemoryCardCache
from mtg_goldfishing.adapters.scryfall import RequestSpacing, ScryfallCatalog
from mtg_goldfishing.domain.cards import Card, CardLookup, Face, LookupStatus
from tests.support.card_data import recorded_card, recorded_scryfall_card
from tests.support.fake_scryfall import FakeScryfall, FakeTime, refusal

M4 = pytest.mark.xfail(strict=True, reason="M4: not implemented yet")


@dataclass
class Setup:
    """A Scryfall catalog wired to a fake Scryfall, a fake clock and an in-memory cache."""

    time: FakeTime = field(default_factory=FakeTime)
    cache: InMemoryCardCache = field(default_factory=InMemoryCardCache)
    spacing: RequestSpacing = field(default_factory=RequestSpacing)
    scryfall: FakeScryfall = field(init=False)
    catalog: ScryfallCatalog = field(init=False)

    def __post_init__(self) -> None:
        self.scryfall = FakeScryfall(time=self.time)
        self.catalog = self.new_catalog()

    def new_catalog(self) -> ScryfallCatalog:
        return ScryfallCatalog(
            self.cache,
            client=self.scryfall.client(),
            sleep=self.time.sleep,
            monotonic=self.time.monotonic,
            now=self.time.wall,
            spacing=self.spacing,
        )


@pytest.fixture
def setup() -> Setup:
    return Setup()


def _invented_names(count: int) -> list[str]:
    return [f"Invented Card {number}" for number in range(count)]


# Batching


# @spec CARD-008
def test_names_not_in_the_cache_are_requested_in_batches_of_at_most_75(setup: Setup) -> None:
    setup.catalog.look_up(_invented_names(160))

    assert [len(setup.scryfall.requested_names(i)) for i in range(3)] == [75, 75, 10]


# @spec CARD-008
def test_every_name_not_in_the_cache_is_requested(setup: Setup) -> None:
    names = _invented_names(160)
    setup.catalog.look_up(names)

    assert sorted(setup.scryfall.all_requested_names()) == sorted(names)


# @spec CARD-008
def test_a_lookup_of_75_names_is_one_request(setup: Setup) -> None:
    setup.catalog.look_up(_invented_names(75))

    assert len(setup.scryfall.requests) == 1


# @spec CARD-008, CARD-017
def test_names_in_the_cache_are_left_out_of_the_request(setup: Setup) -> None:
    setup.cache.put(recorded_card("Sol Ring"))
    setup.catalog.look_up(["Sol Ring", "Cultivate"])

    assert setup.scryfall.all_requested_names() == ["Cultivate"]


# @spec CARD-008
def test_requests_go_to_the_collection_endpoint(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])

    request = setup.scryfall.requests[0]
    assert (request.method, str(request.url)) == (
        "POST",
        "https://api.scryfall.com/cards/collection",
    )


def test_one_card_asked_for_under_several_spellings_is_requested_once(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate", "cultivate", " CULTIVATE "])

    assert len(setup.scryfall.all_requested_names()) == 1


def test_a_name_is_requested_without_its_surrounding_whitespace(setup: Setup) -> None:
    setup.catalog.look_up(["  Cultivate \t"])

    assert setup.scryfall.all_requested_names() == ["Cultivate"]


def test_a_blank_name_is_not_requested(setup: Setup) -> None:
    setup.catalog.look_up(["", "   "])

    assert setup.scryfall.requests == []


def test_a_lookup_of_cached_cards_only_makes_no_request(setup: Setup) -> None:
    setup.cache.put(recorded_card("Sol Ring"))
    setup.catalog.look_up(["Sol Ring"])

    assert setup.scryfall.requests == []


# Names with slash separators


# @spec CARD-023
@M4
@pytest.mark.parametrize(
    ("requested", "identifiers"),
    [
        ("Fire/Ice", ["Fire/Ice", "Fire"]),
        ("Fire // Ice", ["Fire // Ice", "Fire"]),
        (" Gallifrey Falls / No More ", ["Gallifrey Falls / No More", "Gallifrey Falls"]),
    ],
)
def test_a_name_with_a_slash_separator_is_requested_with_its_first_part_too(
    setup: Setup, requested: str, identifiers: list[str]
) -> None:
    setup.catalog.look_up([requested])

    assert setup.scryfall.all_requested_names() == identifiers


# @spec CARD-023
def test_a_name_whose_first_part_is_empty_is_requested_only_as_given(setup: Setup) -> None:
    setup.catalog.look_up(["/Ice"])

    assert setup.scryfall.all_requested_names() == ["/Ice"]


# @spec CARD-008, CARD-023
@M4
def test_both_spellings_of_a_name_go_in_the_same_request(setup: Setup) -> None:
    setup.catalog.look_up([*_invented_names(74), "Fire/Ice"])

    assert setup.scryfall.requested_names(1) == ["Fire/Ice", "Fire"]


# @spec CARD-008, CARD-023
@M4
def test_each_spelling_counts_toward_the_75_identifiers_of_a_request(setup: Setup) -> None:
    setup.catalog.look_up([f"Invented {number}/Card" for number in range(40)])

    assert [len(setup.scryfall.requested_names(i)) for i in range(2)] == [74, 6]


# @spec CARD-011, CARD-021, CARD-023
@M4
def test_a_multi_faced_card_written_with_a_slash_is_found(setup: Setup) -> None:
    result = setup.catalog.look_up(["Gallifrey Falls/No More"])["Gallifrey Falls/No More"]

    assert result == CardLookup(LookupStatus.FOUND, recorded_card("Gallifrey Falls // No More"))


# @spec CARD-006, CARD-023
@M4
def test_a_multi_faced_card_asked_for_by_its_full_name_is_found(setup: Setup) -> None:
    result = setup.catalog.look_up(["Fire // Ice"])["Fire // Ice"]

    assert result == CardLookup(LookupStatus.FOUND, recorded_card("Fire // Ice"))


# @spec CARD-011, CARD-021
def test_the_card_found_by_the_first_part_is_not_accepted_for_a_misspelled_later_part(
    setup: Setup,
) -> None:
    assert setup.catalog.look_up(["Fire/Ise"])["Fire/Ise"] == CardLookup(LookupStatus.NOT_FOUND)


def _two_faced_scryfall_card(first: str, second: str) -> dict[str, object]:
    fire_ice = recorded_scryfall_card("Fire // Ice")
    return fire_ice | {
        "name": f"{first} // {second}",
        "card_faces": [
            fire_ice["card_faces"][0] | {"name": first},
            fire_ice["card_faces"][1] | {"name": second},
        ],
    }


# @spec CARD-022
def test_a_card_with_a_slash_in_its_own_name_is_found_by_that_name(setup: Setup) -> None:
    setup.scryfall.answer_with("Summon: Choco", _two_faced_scryfall_card("Summon: Choco", "Mog"))
    result = setup.catalog.look_up(["Summon: Choco/Mog"])["Summon: Choco/Mog"]

    assert result.card == recorded_card("Summon: Choco/Mog")


# @spec CARD-020, CARD-021
@M4
def test_a_card_written_with_a_slash_that_the_card_model_cannot_hold_is_unavailable(
    setup: Setup,
) -> None:
    broken = recorded_scryfall_card("Fire // Ice") | {"color_identity": ["Q"]}
    setup.scryfall.answer_with("Fire", broken)

    assert setup.catalog.look_up(["Fire/Ice"])["Fire/Ice"].status is LookupStatus.UNAVAILABLE


# @spec CARD-024
@M4
def test_a_cached_card_is_supplied_for_its_full_name_written_with_a_slash_without_a_request(
    setup: Setup,
) -> None:
    setup.cache.put(recorded_card("Fire // Ice"))
    setup.catalog.look_up(["Fire/Ice"])

    assert setup.scryfall.requests == []


# @spec CARD-024
@M4
def test_a_cached_card_is_supplied_for_its_full_name_written_with_a_slash(setup: Setup) -> None:
    setup.cache.put(recorded_card("Fire // Ice"))
    result = setup.catalog.look_up(["Fire/Ice"])["Fire/Ice"]

    assert result == CardLookup(LookupStatus.FOUND, recorded_card("Fire // Ice"))


# Headers


# @spec CARD-009
def test_every_request_names_the_service_and_its_version_as_user_agent(setup: Setup) -> None:
    setup.catalog.look_up(_invented_names(100))

    assert {request.headers["User-Agent"] for request in setup.scryfall.requests} == {
        f"mtg-goldfishing/{__version__}"
    }


# @spec CARD-009
def test_every_request_asks_for_json(setup: Setup) -> None:
    setup.catalog.look_up(_invented_names(100))

    assert {request.headers["Accept"] for request in setup.scryfall.requests} == {
        "application/json"
    }


# @spec CARD-009
def test_a_request_carries_no_header_that_could_identify_the_person(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])

    generic = {
        "host",
        "accept",
        "accept-encoding",
        "connection",
        "user-agent",
        "content-length",
        "content-type",
    }
    assert set(setup.scryfall.requests[0].headers.keys()) <= generic


# Spacing


# @spec CARD-010
def test_consecutive_requests_start_at_least_100_ms_apart(setup: Setup) -> None:
    setup.catalog.look_up(_invented_names(160))

    times = setup.scryfall.request_times
    assert min(round(later - earlier, 9) for earlier, later in itertools.pairwise(times)) >= 0.1


# @spec CARD-010
def test_a_request_waits_only_for_what_remains_of_the_100_ms(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.time.advance(0.03)
    setup.catalog.look_up(["Ponder"])

    assert setup.time.sleeps == [pytest.approx(0.07)]


# @spec CARD-010
def test_a_request_long_after_the_last_does_not_wait(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.time.advance(5)
    setup.catalog.look_up(["Ponder"])

    assert setup.time.sleeps == []


# @spec CARD-010
def test_requests_from_two_catalogs_sharing_a_spacing_are_spaced(setup: Setup) -> None:
    other = setup.new_catalog()
    setup.catalog.look_up(["Cultivate"])
    other.look_up(["Ponder"])

    times = setup.scryfall.request_times
    assert round(times[1] - times[0], 9) >= 0.1


# @spec CARD-010
def test_catalogs_built_without_a_spacing_share_one_for_the_whole_process() -> None:
    time = FakeTime(start=1e6)
    scryfall = FakeScryfall(time=time)

    def build() -> ScryfallCatalog:
        return ScryfallCatalog(
            InMemoryCardCache(),
            client=scryfall.client(),
            sleep=time.sleep,
            monotonic=time.monotonic,
        )

    first, second = build(), build()
    first.look_up(["Cultivate"])
    second.look_up(["Ponder"])

    assert round(scryfall.request_times[1] - scryfall.request_times[0], 9) >= 0.1


# Matching what Scryfall returns


# @spec CARD-011, CARD-012
def test_a_returned_card_that_does_not_match_the_requested_name_is_not_accepted(
    setup: Setup,
) -> None:
    setup.scryfall.answer_with("Sol Rnig", recorded_scryfall_card("Sol Ring"))

    assert setup.catalog.look_up(["Sol Rnig"])["Sol Rnig"] == CardLookup(LookupStatus.NOT_FOUND)


# @spec CARD-011, CARD-016
def test_a_returned_card_that_matches_no_requested_name_is_not_cached(setup: Setup) -> None:
    setup.scryfall.answer_with("Sol Rnig", recorded_scryfall_card("Sol Ring"))
    setup.catalog.look_up(["Sol Rnig"])

    assert setup.cache.get("Sol Ring") is None


# @spec CARD-011
def test_a_returned_card_is_accepted_for_a_face_name(setup: Setup) -> None:
    result = setup.catalog.look_up(["Stomp"])["Stomp"]

    assert result == CardLookup(LookupStatus.FOUND, recorded_card("Bonecrusher Giant // Stomp"))


# @spec CARD-011
def test_returned_cards_are_matched_to_names_whatever_order_they_come_back_in(
    setup: Setup,
) -> None:
    setup.scryfall.answer_with("Cultivate", recorded_scryfall_card("Ponder"))
    setup.scryfall.answer_with("Ponder", recorded_scryfall_card("Cultivate"))

    results = setup.catalog.look_up(["Cultivate", "Ponder"])

    assert (results["Cultivate"].card, results["Ponder"].card) == (
        recorded_card("Cultivate"),
        recorded_card("Ponder"),
    )


# @spec CARD-012
def test_a_name_scryfall_reports_not_found_is_not_found(setup: Setup) -> None:
    result = setup.catalog.look_up(["Invented Card"])["Invented Card"]

    assert result == CardLookup(LookupStatus.NOT_FOUND)


# @spec CARD-020
def test_a_returned_card_the_card_model_cannot_hold_leaves_its_name_unavailable(
    setup: Setup,
) -> None:
    broken = recorded_scryfall_card("Cultivate") | {"mana_cost": "{Q}"}
    setup.scryfall.answer_with("Cultivate", broken)

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.UNAVAILABLE


# @spec CARD-020
def test_a_returned_card_the_card_model_cannot_hold_is_not_cached(setup: Setup) -> None:
    broken = recorded_scryfall_card("Cultivate") | {"mana_cost": "{Q}"}
    setup.scryfall.answer_with("Cultivate", broken)
    setup.catalog.look_up(["Cultivate"])

    assert setup.cache.get("Cultivate") is None


# Failures


# @spec CARD-013
@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectTimeout("timed out"),
    ],
    ids=["network error", "read timeout", "connect timeout"],
)
def test_a_request_that_fails_to_complete_leaves_its_names_unavailable(
    setup: Setup, error: Exception
) -> None:
    setup.scryfall.fail_next(error)

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"] == CardLookup(LookupStatus.UNAVAILABLE)


# @spec CARD-013
@pytest.mark.parametrize("status", [400, 403, 422])
def test_a_request_answered_with_a_failure_status_leaves_its_names_unavailable(
    setup: Setup, status: int
) -> None:
    setup.scryfall.fail_next(status)

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.UNAVAILABLE


# @spec CARD-013
def test_a_request_answered_not_found_leaves_its_names_not_found(setup: Setup) -> None:
    setup.scryfall.fail_next(404)

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.NOT_FOUND


# @spec CARD-013
def test_a_success_response_that_is_not_a_card_list_leaves_its_names_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    catalog = ScryfallCatalog(
        InMemoryCardCache(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=FakeTime().sleep,
        spacing=RequestSpacing(),
    )

    assert catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.UNAVAILABLE


# @spec CARD-013
def test_requests_give_up_after_10_seconds(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])

    timeout = setup.scryfall.requests[0].extensions["timeout"]
    assert {timeout["connect"], timeout["read"], timeout["write"], timeout["pool"]} == {10.0}


# @spec CARD-013
def test_a_failed_request_leaves_only_its_own_names_unavailable(setup: Setup) -> None:
    names = [*_invented_names(74), "Cultivate", "Ponder"]
    setup.scryfall.fail_requests_naming("Ponder")

    results = setup.catalog.look_up(names)

    assert (results["Cultivate"].status, results["Ponder"].status) == (
        LookupStatus.FOUND,
        LookupStatus.UNAVAILABLE,
    )


# Retries


def _gaps(times: list[float]) -> list[float]:
    """The seconds between the starts of consecutive requests."""
    return [round(later - earlier, 9) for earlier, later in itertools.pairwise(times)]


def _http_date(moment: datetime) -> str:
    return format_datetime(moment, usegmt=True)


# @spec CARD-014
@M4
@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_a_rate_limited_or_server_failed_request_is_retried_up_to_three_times(
    setup: Setup, status: int
) -> None:
    setup.scryfall.fail_next(status, status, status)

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"] == CardLookup(
        LookupStatus.FOUND, recorded_card("Cultivate")
    )


# @spec CARD-014
def test_a_request_failing_on_every_attempt_leaves_its_names_unavailable(setup: Setup) -> None:
    setup.scryfall.fail_next(503, 503, 503, 503)

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.UNAVAILABLE


# @spec CARD-014
@M4
def test_a_request_is_retried_no_more_than_three_times(setup: Setup) -> None:
    setup.scryfall.fail_next(503, 503, 503, 503, 503)
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 4


# @spec CARD-026
@M4
def test_retries_wait_one_then_two_then_four_seconds(setup: Setup) -> None:
    setup.scryfall.fail_next(503, 503, 503)
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [1.0, 2.0, 4.0]


# @spec CARD-026, CARD-027
@M4
def test_a_retry_waits_the_seconds_retry_after_asks_for_when_longer_than_the_backoff(
    setup: Setup,
) -> None:
    setup.scryfall.fail_next(refusal(429, "3"))
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [3.0]


# @spec CARD-026
@M4
def test_a_retry_waits_the_backoff_when_retry_after_asks_for_less(setup: Setup) -> None:
    setup.scryfall.fail_next(503, refusal(503, "1"))
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [1.0, 2.0]


# @spec CARD-027
@M4
def test_a_retry_after_given_as_an_http_date_is_waited_for_by_the_service_s_clock(
    setup: Setup,
) -> None:
    setup.scryfall.fail_next(refusal(429, _http_date(setup.time.wall() + timedelta(seconds=5))))
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [5.0]


# @spec CARD-027
def test_a_retry_after_date_already_past_asks_for_no_wait(setup: Setup) -> None:
    setup.scryfall.fail_next(refusal(429, _http_date(setup.time.wall() - timedelta(minutes=1))))
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [1.0]


# @spec CARD-028
@pytest.mark.parametrize("value", ["soon", "1.5", "-3", "", "3 seconds"])
def test_a_retry_after_that_is_neither_seconds_nor_a_date_is_ignored(
    setup: Setup, value: str
) -> None:
    setup.scryfall.fail_next(refusal(429, value))
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [1.0]


# @spec CARD-029
@M4
def test_a_retry_after_holds_back_the_requests_of_every_catalog_in_the_process(
    setup: Setup,
) -> None:
    other = setup.new_catalog()
    setup.scryfall.fail_next(*(refusal(503, "10") for _ in range(4)))
    setup.catalog.look_up(["Cultivate"])
    other.look_up(["Ponder"])

    assert _gaps(setup.scryfall.request_times)[-1] == 10.0


# @spec CARD-029
def test_a_request_due_after_a_retry_after_has_passed_is_sent(setup: Setup) -> None:
    other = setup.new_catalog()
    setup.scryfall.fail_next(refusal(429, "30"))
    setup.catalog.look_up(["Cultivate"])
    setup.time.advance(30)

    assert other.look_up(["Ponder"])["Ponder"].status is LookupStatus.FOUND


# @spec CARD-029, CARD-030
@M4
def test_a_request_due_while_a_long_retry_after_holds_is_not_sent(setup: Setup) -> None:
    other = setup.new_catalog()
    setup.scryfall.fail_next(refusal(429, "30"))
    setup.catalog.look_up(["Cultivate"])
    other.look_up(["Ponder"])

    assert len(setup.scryfall.requests) == 1


# @spec CARD-029, CARD-030
@M4
def test_a_request_due_while_a_long_retry_after_holds_leaves_its_names_unavailable(
    setup: Setup,
) -> None:
    other = setup.new_catalog()
    setup.scryfall.fail_next(refusal(429, "30"))
    setup.catalog.look_up(["Cultivate"])

    assert other.look_up(["Ponder"])["Ponder"].status is LookupStatus.UNAVAILABLE


# @spec CARD-030
@M4
def test_a_retry_after_longer_than_20_seconds_leaves_the_names_unavailable(setup: Setup) -> None:
    setup.scryfall.fail_next(refusal(429, "21"))

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.UNAVAILABLE


# @spec CARD-030
@M4
def test_a_retry_after_longer_than_20_seconds_is_not_retried(setup: Setup) -> None:
    setup.scryfall.fail_next(refusal(429, "21"))
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 1


# @spec CARD-030
@M4
def test_a_retry_after_longer_than_20_seconds_is_not_waited_for(setup: Setup) -> None:
    setup.scryfall.fail_next(refusal(429, "21"))
    setup.catalog.look_up(["Cultivate"])

    assert setup.time.sleeps == []


# @spec CARD-030
@M4
def test_a_retry_after_of_exactly_20_seconds_is_waited_for(setup: Setup) -> None:
    setup.scryfall.fail_next(refusal(429, "20"))
    setup.catalog.look_up(["Cultivate"])

    assert _gaps(setup.scryfall.request_times) == [20.0]


# @spec CARD-030
def test_a_retry_after_too_long_leaves_only_the_names_of_its_own_request_unavailable(
    setup: Setup,
) -> None:
    setup.scryfall.fail_requests_naming("Ponder", status=429, retry_after="30")

    results = setup.catalog.look_up([*_invented_names(74), "Cultivate", "Ponder"])

    assert (results["Cultivate"].status, results["Ponder"].status) == (
        LookupStatus.FOUND,
        LookupStatus.UNAVAILABLE,
    )


# @spec CARD-031
@pytest.mark.parametrize("status", [400, 404])
def test_a_request_refused_for_another_reason_is_not_retried(setup: Setup, status: int) -> None:
    setup.scryfall.fail_next(status)
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 1


# @spec CARD-031
def test_a_request_that_fails_to_complete_is_not_retried(setup: Setup) -> None:
    setup.scryfall.fail_next(httpx.ConnectError("connection refused"))
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 1


# @spec CARD-031
@M4
def test_a_retry_that_fails_to_complete_ends_the_request(setup: Setup) -> None:
    setup.scryfall.fail_next(503, 503, httpx.ReadTimeout("timed out"))
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 3


# @spec CARD-031
@M4
def test_a_retry_refused_for_another_reason_ends_the_request(setup: Setup) -> None:
    setup.scryfall.fail_next(503, 503, 400)
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 3


# @spec CARD-013, CARD-031
def test_a_retry_that_fails_to_complete_leaves_its_names_unavailable(setup: Setup) -> None:
    setup.scryfall.fail_next(503, httpx.ConnectError("connection refused"))

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.UNAVAILABLE


# Cache


# @spec CARD-015
def test_a_found_card_is_cached(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])

    assert setup.cache.get("Cultivate") == recorded_card("Cultivate")


# @spec CARD-015
def test_a_found_card_is_cached_when_another_name_in_the_lookup_is_not_found(
    setup: Setup,
) -> None:
    setup.catalog.look_up(["Cultivate", "Invented Card"])

    assert setup.cache.get("Cultivate") == recorded_card("Cultivate")


# @spec CARD-015
def test_a_found_card_is_cached_when_another_batch_of_the_lookup_is_unavailable(
    setup: Setup,
) -> None:
    setup.scryfall.fail_requests_naming("Ponder")
    setup.catalog.look_up([*_invented_names(74), "Cultivate", "Ponder"])

    assert setup.cache.get("Cultivate") == recorded_card("Cultivate")


# @spec CARD-016
def test_a_name_not_found_is_not_cached(setup: Setup) -> None:
    setup.scryfall.answer_with("Sol Rnig", recorded_scryfall_card("Sol Ring"))
    setup.catalog.look_up(["Sol Rnig"])
    setup.catalog.look_up(["Sol Rnig"])

    assert len(setup.scryfall.requests) == 2


# @spec CARD-016
def test_an_unavailable_name_is_not_cached(setup: Setup) -> None:
    setup.scryfall.fail_next(400)
    setup.catalog.look_up(["Cultivate"])

    assert setup.cache.get("Cultivate") is None


# @spec CARD-016
def test_a_name_unavailable_before_is_fetched_on_the_next_lookup(setup: Setup) -> None:
    setup.scryfall.fail_next(400)
    setup.catalog.look_up(["Cultivate"])

    assert setup.catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.FOUND


# @spec CARD-017
def test_a_cached_card_is_supplied_without_contacting_scryfall(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.catalog.look_up(["Cultivate"])

    assert len(setup.scryfall.requests) == 1


# @spec CARD-017
def test_a_cached_card_is_supplied_for_one_of_its_face_names(setup: Setup) -> None:
    setup.catalog.look_up(["Valki, God of Lies"])
    result = setup.catalog.look_up(["Tibalt, Cosmic Impostor"])["Tibalt, Cosmic Impostor"]

    assert (result.status, len(setup.scryfall.requests)) == (LookupStatus.FOUND, 1)


# @spec CARD-007, CARD-017
def test_a_cached_face_name_shared_by_two_cards_gives_the_card_whose_full_name_sorts_first(
    setup: Setup,
) -> None:
    earlier = Card("Aardvark // Shared", (Face("Aardvark"), Face("Shared")), layout="split")
    later = Card("Zebra // Shared", (Face("Zebra"), Face("Shared")), layout="split")
    setup.cache.put(later)
    setup.cache.put(earlier)

    assert setup.catalog.look_up(["Shared"])["Shared"].card == earlier


# Refresh


def _with_new_text(name: str, text: str) -> dict[str, object]:
    return recorded_scryfall_card(name) | {"oracle_text": text}


# @spec CARD-018
def test_a_refresh_requests_cached_names_again(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate", "Ponder"])
    setup.catalog.look_up(["Cultivate", "Ponder"], refresh=True)

    assert sorted(setup.scryfall.requested_names(1)) == ["Cultivate", "Ponder"]


# @spec CARD-018
def test_a_refresh_replaces_the_cached_card_with_the_fetched_one(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.scryfall.replace_card(_with_new_text("Cultivate", "Errata."))
    setup.catalog.look_up(["Cultivate"], refresh=True)

    cached = setup.cache.get("Cultivate")
    assert (cached.front.oracle_text if cached else None) == "Errata."


# @spec CARD-018
def test_a_refresh_reports_the_fetched_card(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.scryfall.replace_card(_with_new_text("Cultivate", "Errata."))
    result = setup.catalog.look_up(["Cultivate"], refresh=True)["Cultivate"]

    assert (result.card.front.oracle_text if result.card else None) == "Errata."


# @spec CARD-018
def test_a_refresh_by_face_name_requests_the_card_again(setup: Setup) -> None:
    setup.catalog.look_up(["Stomp"])
    setup.catalog.look_up(["Stomp"], refresh=True)

    assert len(setup.scryfall.requests) == 2


# @spec CARD-019
def test_a_refresh_that_is_unavailable_keeps_the_cached_card(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.scryfall.fail_next(400)
    setup.catalog.look_up(["Cultivate"], refresh=True)

    assert setup.cache.get("Cultivate") == recorded_card("Cultivate")


# @spec CARD-019
def test_a_refresh_that_is_unavailable_reports_unavailable_with_the_cached_card(
    setup: Setup,
) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.scryfall.fail_next(400)

    assert setup.catalog.look_up(["Cultivate"], refresh=True)["Cultivate"] == CardLookup(
        LookupStatus.UNAVAILABLE, recorded_card("Cultivate")
    )


# @spec CARD-019
def test_a_refresh_that_finds_nothing_keeps_the_cached_card(setup: Setup) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.scryfall.cards = []
    setup.catalog.look_up(["Cultivate"], refresh=True)

    assert setup.cache.get("Cultivate") == recorded_card("Cultivate")


# @spec CARD-019
def test_a_refresh_that_finds_nothing_reports_not_found_with_the_cached_card(
    setup: Setup,
) -> None:
    setup.catalog.look_up(["Cultivate"])
    setup.scryfall.cards = []

    assert setup.catalog.look_up(["Cultivate"], refresh=True)["Cultivate"] == CardLookup(
        LookupStatus.NOT_FOUND, recorded_card("Cultivate")
    )


# @spec CARD-019
def test_a_refresh_of_an_uncached_name_that_finds_nothing_reports_plain_not_found(
    setup: Setup,
) -> None:
    result = setup.catalog.look_up(["Invented Card"], refresh=True)["Invented Card"]

    assert result == CardLookup(LookupStatus.NOT_FOUND)
