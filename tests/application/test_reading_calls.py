"""The read-only use cases, `get_state` and `get_log`: they answer and change nothing."""

from __future__ import annotations

import pytest

from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.domain.events import ErrorKind, LogExported, Refused, StateListed
from mtg_goldfishing.domain.game.listing import StateListing
from mtg_goldfishing.domain.game.model import GameStatus
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import a_game
from tests.support.service import GAME_ID, ServiceHarness, a_service


def harness_after_one_play() -> ServiceHarness:
    harness = a_service()
    harness.holding(a_game().with_hand("Forest", "Island").build())
    harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    return harness


# ------------------------------------------------------------------ get_state


def test_get_state_lists_the_zones_in_the_payload() -> None:
    harness = harness_after_one_play()
    answer = harness.service.get_state({"game_id": GAME_ID})
    assert answer.outcome.summary == StateListed("summary")
    assert isinstance(answer.outcome.payload, StateListing)
    assert answer.outcome.payload.hand == ("Island",)


def test_get_state_in_full_detail_lists_the_library_size() -> None:
    harness = a_service()
    harness.holding(a_game().with_library("Island", "Swamp").build())
    answer = harness.service.get_state({"game_id": GAME_ID, "detail": "full"})
    assert answer.outcome.summary == StateListed("full")
    assert isinstance(answer.outcome.payload, StateListing)
    assert answer.outcome.payload.library_size == 2


def test_get_state_with_an_unknown_detail_is_an_error() -> None:
    harness = harness_after_one_play()
    answer = harness.service.get_state({"game_id": GAME_ID, "detail": "everything"})
    assert answer.outcome.status is Status.ERROR


# @spec REC-002
def test_get_state_changes_nothing_and_adds_no_log_entry() -> None:
    harness = harness_after_one_play()
    harness.service.get_state({"game_id": GAME_ID})
    assert (harness.game().change, harness.version()) == (1, 2)
    assert [e.seq for e in harness.records().entries] == [1]


# ------------------------------------------------------------------ get_log


def test_get_log_exports_the_game_s_records_in_the_payload() -> None:
    harness = harness_after_one_play()
    answer = harness.service.get_log({"game_id": GAME_ID})
    assert isinstance(answer.outcome.payload, dict)
    assert [e["tool"] for e in answer.outcome.payload["entries"]] == ["play"]
    assert answer.outcome.summary == LogExported(entries=1, snapshots=0, calls=0)


def test_get_log_includes_call_records_when_asked() -> None:
    harness = harness_after_one_play()
    answer = harness.service.get_log({"game_id": GAME_ID, "include_calls": True})
    assert isinstance(answer.outcome.payload, dict)
    assert [c["tool"] for c in answer.outcome.payload["calls"]] == ["play"]


def test_get_log_since_a_change_number_leaves_out_earlier_entries() -> None:
    harness = harness_after_one_play()
    harness.service.play({"game_id": GAME_ID, "card": "Island", "override": "second land"})
    answer = harness.service.get_log({"game_id": GAME_ID, "since": 1})
    assert isinstance(answer.outcome.payload, dict)
    assert [e["seq"] for e in answer.outcome.payload["entries"]] == [2]


def test_get_log_with_a_since_that_is_not_a_whole_number_is_a_malformed_argument() -> None:
    harness = harness_after_one_play()
    answer = harness.service.get_log({"game_id": GAME_ID, "since": "one"})
    assert isinstance(answer.outcome.summary, Refused)
    assert [(e.kind, e.subject) for e in answer.outcome.summary.errors] == [
        (ErrorKind.MALFORMED_ARGUMENT, "since")
    ]


# @spec REC-023
@pytest.mark.parametrize("status", list(GameStatus))
def test_get_log_is_accepted_in_every_game_status(status: GameStatus) -> None:
    harness = a_service()
    harness.holding(a_game().with_status(status).build())
    assert harness.service.get_log({"game_id": GAME_ID}).outcome.status is Status.OK


# @spec REC-023, REC-002
def test_get_log_changes_nothing_and_adds_no_log_entry() -> None:
    harness = harness_after_one_play()
    harness.service.get_log({"game_id": GAME_ID})
    assert (harness.game().change, harness.version()) == (1, 2)
    assert [e.seq for e in harness.records().entries] == [1]


def test_get_log_of_a_game_in_cleanup_exports_its_snapshot() -> None:
    harness = a_service()
    harness.holding(a_game().in_step(Step.END, turn=4).build())
    harness.service.advance({"game_id": GAME_ID})
    answer = harness.service.get_log({"game_id": GAME_ID})
    assert isinstance(answer.outcome.payload, dict)
    assert [s["turn"] for s in answer.outcome.payload["snapshots"]] == [4]
