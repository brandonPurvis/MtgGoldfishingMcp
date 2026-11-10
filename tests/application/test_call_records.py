"""Every call gets a call record holding the response exactly as rendered."""

from __future__ import annotations

from datetime import UTC, datetime

from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.domain.events import ErrorKind, Refused
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.records.model import CallRecord
from tests.support.builders import a_game
from tests.support.decks import ATRAXA, a_deck_list
from tests.support.rendering import plain_text, size_note
from tests.support.service import GAME_ID, ServiceHarness, a_service


def harness_with_forest_in_hand() -> ServiceHarness:
    harness = a_service()
    harness.holding(a_game().with_hand("Forest", "Sol Ring").build())
    return harness


# @spec APP-019, REC-017
def test_an_applied_call_gets_a_call_record_of_everything_about_it() -> None:
    harness = harness_with_forest_in_hand()
    harness.clock.set(datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC))
    arguments: dict[str, object] = {"game_id": GAME_ID, "card": "Forest", "after": 0}
    answer = harness.service.play(arguments)
    assert harness.calls() == (
        CallRecord(
            time=datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC),
            game_id=GAME_ID,
            tool="play",
            arguments=arguments,
            status="OK",
            response=answer.response,
            is_override=False,
            change=1,
            id=1,
        ),
    )


# @spec APP-019, REC-017
def test_a_refused_call_gets_a_call_record() -> None:
    harness = harness_with_forest_in_hand()
    harness.service.play({"game_id": GAME_ID, "card": "Sol Ring"})
    assert [(c.tool, c.status, c.change) for c in harness.calls()] == [("play", "REJECTED", 0)]


# @spec REC-017
def test_a_call_carrying_an_override_is_recorded_as_one() -> None:
    harness = harness_with_forest_in_hand()
    harness.service.play({"game_id": GAME_ID, "card": "Sol Ring", "override": "ritual"})
    assert harness.last_call().is_override


# @spec APP-019, REC-017
def test_a_call_naming_no_game_gets_a_call_record_with_the_id_as_supplied() -> None:
    harness = a_service()
    harness.service.get_state({"game_id": "gnosuchgame"})
    record = harness.last_call()
    assert (record.game_id, record.status, record.change) == ("gnosuchgame", "ERROR", None)


# @spec APP-019, REC-017
def test_a_load_deck_call_gets_a_call_record_with_its_cards_as_received() -> None:
    harness = a_service()
    cards = a_deck_list().text()
    harness.service.load_deck({"cards": cards, "commander": ATRAXA})
    record = harness.last_call()
    assert (record.tool, record.game_id, record.arguments["cards"]) == ("load_deck", None, cards)


# @spec APP-019
def test_a_read_only_call_gets_a_call_record() -> None:
    harness = harness_with_forest_in_hand()
    harness.service.get_state({"game_id": GAME_ID})
    assert [(c.tool, c.status) for c in harness.calls()] == [("get_state", "OK")]


# @spec APP-026, APP-010
def test_the_response_is_the_text_the_renderer_produced() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    assert answer.response == plain_text(answer.outcome)


# @spec APP-026
def test_the_call_record_keeps_the_text_the_renderer_produced() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Sol Ring"})
    assert harness.last_call().response == answer.response


# @spec REC-018
def test_a_successful_get_log_s_call_record_keeps_a_note_of_the_export_s_size() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.get_log({"game_id": GAME_ID})
    assert harness.last_call().response == size_note(answer.outcome.payload)


# ------------------------------------------------------- calls the adapter could not shape


# @spec APP-027
def test_a_call_that_could_not_be_shaped_is_an_error_naming_each_problem() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.malformed_call("play", {"game_id": GAME_ID}, ["card"])
    assert answer.outcome.status is Status.ERROR
    assert isinstance(answer.outcome.summary, Refused)
    assert [(e.kind, e.subject) for e in answer.outcome.summary.errors] == [
        (ErrorKind.MALFORMED_ARGUMENT, "card")
    ]


# @spec APP-027
def test_a_call_that_could_not_be_shaped_carries_the_summary_of_the_game_it_names() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.malformed_call("play", {"game_id": GAME_ID, "card": 3}, ["card"])
    deck = harness.stores.decks.get("dtest")
    assert deck is not None
    assert answer.outcome.game == summarize(harness.game(), deck)


# @spec APP-027
def test_a_call_that_could_not_be_shaped_and_names_no_game_carries_no_summary() -> None:
    harness = a_service()
    answer = harness.service.malformed_call("play", {"game_id": "gnosuchgame"}, ["card"])
    assert answer.outcome.game is None


# @spec APP-027, APP-019
def test_a_call_that_could_not_be_shaped_gets_a_call_record() -> None:
    harness = harness_with_forest_in_hand()
    arguments: dict[str, object] = {"game_id": GAME_ID, "keep": "maybe"}
    answer = harness.service.malformed_call("mulligan", arguments, ["keep"])
    record = harness.last_call()
    assert (record.tool, record.arguments, record.status, record.response, record.change) == (
        "mulligan",
        arguments,
        "ERROR",
        answer.response,
        0,
    )


# @spec APP-027
def test_a_call_that_could_not_be_shaped_changes_nothing() -> None:
    harness = harness_with_forest_in_hand()
    before = harness.game()
    harness.service.malformed_call("play", {"game_id": GAME_ID}, ["card"])
    assert (harness.game(), harness.version(), harness.records().entries) == (before, 1, ())
