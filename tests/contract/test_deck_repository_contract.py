"""What every DeckRepository promises, run against each adapter that implements it."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from mtg_goldfishing.application.ports import DeckRepository
from tests.support.builders import a_deck
from tests.support.stored import a_rich_deck
from tests.support.stores import STORE_ADAPTER_IDS, STORE_ADAPTERS, OpenStores


# @spec APP-012, APP-013, STOR-001
@pytest.fixture(params=STORE_ADAPTERS, ids=STORE_ADAPTER_IDS)
def decks(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[DeckRepository]:
    open_stores: OpenStores = request.param
    with open_stores(tmp_path) as stores:
        yield stores.decks


def test_a_repository_has_no_deck_under_an_id_never_added(decks: DeckRepository) -> None:
    assert decks.get("dnothing") is None


def test_an_added_deck_is_returned_equal(decks: DeckRepository) -> None:
    deck = a_deck("Forest", "Sol Ring", "Cultivate")
    decks.add(deck)

    assert decks.get(deck.deck_id) == deck


def test_a_deck_with_multi_faced_cards_readings_and_overrides_is_returned_equal(
    decks: DeckRepository,
) -> None:
    decks.add(a_rich_deck())

    assert decks.get("drich") == a_rich_deck()


def test_adding_a_deck_returns_the_stored_deck(decks: DeckRepository) -> None:
    assert decks.add(a_rich_deck()) == a_rich_deck()


# @spec STOR-010
def test_adding_a_deck_under_an_existing_id_keeps_the_original(decks: DeckRepository) -> None:
    original = a_rich_deck()
    decks.add(original)

    decks.add(replace(a_deck("Island"), deck_id="drich"))

    assert decks.get("drich") == original


# @spec STOR-010
def test_adding_a_deck_under_an_existing_id_returns_the_original(decks: DeckRepository) -> None:
    original = a_rich_deck()
    decks.add(original)

    assert decks.add(replace(a_deck("Island"), deck_id="drich")) == original


def test_decks_under_different_ids_are_kept_apart(decks: DeckRepository) -> None:
    decks.add(a_rich_deck("done"))
    decks.add(replace(a_deck("Island"), deck_id="dtwo"))

    assert decks.get("done") == a_rich_deck("done")
