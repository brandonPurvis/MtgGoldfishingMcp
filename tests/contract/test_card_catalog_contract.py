"""What every CardCatalog promises, run against each adapter that implements it."""

from collections.abc import Callable, Iterable

import pytest

from mtg_goldfishing.adapters.memory import InMemoryCardCache, InMemoryCardCatalog
from mtg_goldfishing.adapters.scryfall import RequestSpacing, ScryfallCatalog
from mtg_goldfishing.application.ports import CardCatalog
from mtg_goldfishing.domain.cards import CardLookup, LookupStatus
from tests.support.card_data import recorded_cards
from tests.support.fake_scryfall import FakeScryfall, FakeTime

CatalogFactory = Callable[[Iterable[str]], CardCatalog]
"""Builds a catalog holding the recorded cards, where the given names are unavailable."""

NOT_FOUND = CardLookup(LookupStatus.NOT_FOUND)


def _memory_catalog(unavailable: Iterable[str]) -> CardCatalog:
    return InMemoryCardCatalog(recorded_cards(), unavailable=unavailable)


def _scryfall_catalog(unavailable: Iterable[str]) -> CardCatalog:
    time = FakeTime()
    scryfall = FakeScryfall(time=time)
    scryfall.fail_requests_naming(*unavailable)
    return ScryfallCatalog(
        InMemoryCardCache(),
        client=scryfall.client(),
        sleep=time.sleep,
        monotonic=time.monotonic,
        spacing=RequestSpacing(),
    )


# @spec APP-012, APP-013
@pytest.fixture(params=[_memory_catalog, _scryfall_catalog], ids=["memory", "scryfall"])
def new_catalog(request: pytest.FixtureRequest) -> CatalogFactory:
    factory: CatalogFactory = request.param
    return factory


# @spec CARD-006
def test_a_catalog_finds_a_card_by_its_exact_full_name(new_catalog: CatalogFactory) -> None:
    result = new_catalog(()).look_up(["Cultivate"])["Cultivate"]

    assert (result.status, result.card and result.card.name) == (LookupStatus.FOUND, "Cultivate")


# @spec CARD-006
@pytest.mark.parametrize(
    ("requested", "full_name"),
    [
        ("Valki, God of Lies", "Valki, God of Lies // Tibalt, Cosmic Impostor"),
        ("Tibalt, Cosmic Impostor", "Valki, God of Lies // Tibalt, Cosmic Impostor"),
        ("Stomp", "Bonecrusher Giant // Stomp"),
        ("Bonecrusher Giant", "Bonecrusher Giant // Stomp"),
        ("Fire", "Fire // Ice"),
    ],
)
def test_a_catalog_finds_a_multi_faced_card_by_a_face_name(
    new_catalog: CatalogFactory, requested: str, full_name: str
) -> None:
    result = new_catalog(()).look_up([requested])[requested]

    assert (result.status, result.card and result.card.name) == (LookupStatus.FOUND, full_name)


# @spec CARD-006
@pytest.mark.parametrize("requested", ["sol ring", "SOL RING", "  Sol Ring", "Sol Ring\t"])
def test_a_catalog_ignores_letter_case_and_surrounding_whitespace(
    new_catalog: CatalogFactory, requested: str
) -> None:
    result = new_catalog(()).look_up([requested])[requested]

    assert (result.status, result.card and result.card.name) == (LookupStatus.FOUND, "Sol Ring")


# @spec CARD-006, CARD-012
@pytest.mark.parametrize(
    "requested",
    ["Sol Rnig", "Sol", "Sol Ring Ring", "Gaeas Cradle", "Valki", "Kodamas Reach", "Sol  Ring"],
)
def test_a_catalog_reports_a_misspelled_or_partial_name_as_not_found(
    new_catalog: CatalogFactory, requested: str
) -> None:
    result = new_catalog(()).look_up([requested])[requested]

    assert result == NOT_FOUND


# @spec CARD-012
def test_a_catalog_reports_a_blank_name_as_not_found(new_catalog: CatalogFactory) -> None:
    assert new_catalog(()).look_up(["  "])["  "] == NOT_FOUND


# @spec CARD-013
def test_a_catalog_reports_an_unreachable_card_as_unavailable_not_as_not_found(
    new_catalog: CatalogFactory,
) -> None:
    result = new_catalog(["Sol Ring"]).look_up(["Sol Ring"])["Sol Ring"]

    assert result.status is LookupStatus.UNAVAILABLE


def test_a_catalog_keys_each_result_by_the_name_exactly_as_requested(
    new_catalog: CatalogFactory,
) -> None:
    requested = ["Sol Ring", "sol ring ", "Valki, God of Lies", "Sol Rnig"]

    assert set(new_catalog(()).look_up(requested)) == set(requested)


def test_a_catalog_reports_each_spelling_of_one_card_as_that_card(
    new_catalog: CatalogFactory,
) -> None:
    results = new_catalog(()).look_up(["Sol Ring", "SOL RING"])

    assert results["Sol Ring"] == results["SOL RING"]


# @spec CARD-006, CARD-012
def test_a_catalog_reports_each_name_of_a_lookup_on_its_own(new_catalog: CatalogFactory) -> None:
    results = new_catalog(()).look_up(["Sol Ring", "Sol Rnig", "Cultivate"])

    assert [results[name].status for name in ["Sol Ring", "Sol Rnig", "Cultivate"]] == [
        LookupStatus.FOUND,
        LookupStatus.NOT_FOUND,
        LookupStatus.FOUND,
    ]


def test_a_catalog_answers_an_empty_lookup_with_no_results(new_catalog: CatalogFactory) -> None:
    assert dict(new_catalog(()).look_up([])) == {}


# @spec CARD-017
def test_a_catalog_gives_the_same_card_when_asked_twice(new_catalog: CatalogFactory) -> None:
    catalog = new_catalog(())
    first = catalog.look_up(["Cultivate"])["Cultivate"]

    assert catalog.look_up(["Cultivate"])["Cultivate"] == first


# @spec CARD-018
def test_a_catalog_finds_a_card_on_a_refresh_lookup(new_catalog: CatalogFactory) -> None:
    catalog = new_catalog(())
    catalog.look_up(["Cultivate"])

    assert catalog.look_up(["Cultivate"], refresh=True)["Cultivate"].status is LookupStatus.FOUND
