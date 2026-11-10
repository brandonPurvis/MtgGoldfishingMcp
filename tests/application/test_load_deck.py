"""The `load_deck` use case: look the cards up, let the domain build the deck, keep it."""

from __future__ import annotations

from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.domain.cards import LookupStatus
from mtg_goldfishing.domain.events import CheckKind, DeckLoaded, ErrorKind, Refused
from tests.support.decks import ATRAXA, a_deck_list
from tests.support.service import a_service


def load_arguments(**extra: object) -> dict[str, object]:
    return {"cards": a_deck_list().text(), "commander": ATRAXA, **extra}


def test_loading_a_deck_keeps_it_in_the_deck_repository() -> None:
    harness = a_service()
    answer = harness.service.load_deck(load_arguments())
    assert isinstance(answer.outcome.summary, DeckLoaded)
    assert harness.stores.decks.get(answer.outcome.summary.deck_id) is not None


def test_a_loaded_deck_is_answered_ok_with_no_game() -> None:
    answer = a_service().service.load_deck(load_arguments())
    assert (answer.outcome.status, answer.outcome.game) == (Status.OK, None)


# @spec DECK-031
def test_loading_the_same_deck_again_leaves_the_loaded_deck_unchanged() -> None:
    harness = a_service()
    first = harness.service.load_deck(load_arguments())
    assert isinstance(first.outcome.summary, DeckLoaded)
    kept = harness.stores.decks.get(first.outcome.summary.deck_id)
    second = harness.service.load_deck(load_arguments())
    assert second.outcome.summary == DeckLoaded(
        kept.deck_id if kept else "",
        first.outcome.summary.card_count,
        first.outcome.summary.commanders,
        already_loaded=True,
        report=first.outcome.summary.report,
    )
    assert harness.stores.decks.get(first.outcome.summary.deck_id) == kept


# @spec DECK-018
def test_loading_a_deck_with_a_card_definition_leaves_the_catalog_s_card_data_alone() -> None:
    harness = a_service()
    before = harness.catalog.look_up(["Sol Ring"])["Sol Ring"]
    answer = harness.service.load_deck(
        load_arguments(definitions=[{"name": "Sol Ring", "oracle_text": "Nothing."}])
    )
    assert answer.outcome.status is Status.OK
    assert harness.catalog.look_up(["Sol Ring"])["Sol Ring"] == before


def test_a_deck_naming_a_card_the_catalog_does_not_know_is_an_error() -> None:
    harness = a_service()
    answer = harness.service.load_deck(
        {"cards": a_deck_list().with_cards("No Such Card").text(), "commander": ATRAXA}
    )
    assert answer.outcome.status is Status.ERROR
    assert isinstance(answer.outcome.summary, Refused)
    assert answer.outcome.summary.errors[0].kind is ErrorKind.CARDS_NOT_FOUND


def test_a_refused_deck_is_not_kept() -> None:
    harness = a_service()
    harness.service.load_deck({"cards": a_deck_list().of_size(60).text(), "commander": ATRAXA})
    assert harness.stores.decks.checkpoint() == {}


def test_a_deck_failing_only_deck_checks_is_rejected() -> None:
    answer = a_service().service.load_deck(
        {"cards": a_deck_list().of_size(60).text(), "commander": ATRAXA}
    )
    assert answer.outcome.status is Status.REJECTED
    assert isinstance(answer.outcome.summary, Refused)
    assert answer.outcome.summary.checks[0].kind is CheckKind.DECK_SIZE


def test_a_card_whose_data_is_unavailable_makes_the_deck_an_error() -> None:
    harness = a_service(unavailable=["Sol Ring"])
    assert harness.catalog.look_up(["Sol Ring"])["Sol Ring"].status is LookupStatus.UNAVAILABLE
    answer = harness.service.load_deck(load_arguments())
    assert isinstance(answer.outcome.summary, Refused)
    assert answer.outcome.summary.errors[0].kind is ErrorKind.CARD_DATA_UNAVAILABLE


def test_a_refresh_that_is_not_true_or_false_is_a_malformed_argument() -> None:
    answer = a_service().service.load_deck(load_arguments(refresh="yes"))
    assert isinstance(answer.outcome.summary, Refused)
    assert [(e.kind, e.subject) for e in answer.outcome.summary.errors] == [
        (ErrorKind.MALFORMED_ARGUMENT, "refresh")
    ]
