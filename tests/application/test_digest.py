"""The digest of a contested game: every response to a seat carries the other seats' changes
since that seat's digest baseline, as that seat may see them, assembled from the records."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.domain.events import AlreadyApplied, EffectRecorded
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.steps import Step
from tests.application.test_failures import ChangedByAnotherWriter, SnapshotsCannotBeWritten
from tests.support.builders import a_game
from tests.support.service import ServiceHarness, a_service
from tests.support.stored import a_contested_log_entry

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
IDS = ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "dddddddddd")
GAME = "gaaaaaaaaaa"
HELD = "gtest000001"
S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)


def contested(opposing: int = 1) -> ServiceHarness:
    """A contested game started with the tested seat first in turn order."""
    harness = a_service(game_ids=IDS, seeds=(77,))
    assert harness.started_contested_game(opposing, position=1, seed=11) == GAME
    return harness


def call_as(harness: ServiceHarness, seat: int, tool: str, **arguments: object) -> Answer:
    seat_id = harness.seat_id(GAME, seat)
    answer: Answer = getattr(harness.service, tool)({"game_id": seat_id, **arguments})
    return answer


def started(harness: ServiceHarness) -> None:
    """Every seat keeps in seat order, so seat 1 takes turn 1 in the last seat's call."""
    for seat in harness.game(GAME).seats:
        assert (
            call_as(harness, seat.number.value, "mulligan", keep=True).outcome.status is Status.OK
        )


def digest_of(answer: Answer) -> list[tuple[SeatNumber, int]]:
    digest: Any = answer.outcome.digest  # type: ignore[attr-defined]
    return [(element.seat, element.change) for element in digest]


def gain_a_life(harness: ServiceHarness, seat: int = 1) -> Answer:
    return call_as(harness, seat, "effect", source="a test effect", delta={"life": 1})


# ------------------------------------------------------------------ what a digest holds


# @spec APP-036
@NOT_BUILT
def test_a_digest_holds_each_change_another_seat_made_since_the_seat_s_baseline() -> None:
    harness = contested()
    started(harness)
    gain_a_life(harness)
    gain_a_life(harness)
    assert digest_of(call_as(harness, 2, "get_state")) == [(S1, 4), (S1, 5)]


# @spec APP-081
@NOT_BUILT
def test_a_digest_names_the_card_another_seat_s_call_had_the_seat_draw() -> None:
    harness = contested()
    started(harness)
    digest: Any = call_as(harness, 1, "get_state").outcome.digest  # type: ignore[attr-defined]
    ((seat, change, events),) = [(e.seat, e.change, e.events) for e in digest]
    drawn = [event for event in events if type(event).__name__ == "CardsDrawn"]
    assert (seat, change) == (S2, 3)
    assert [len(event.cards) for event in drawn] == [1]
    assert not [event for event in events if type(event).__name__ == "HiddenCardsDrawn"]


# @spec APP-081
@NOT_BUILT
def test_a_third_seat_s_digest_shows_another_seat_s_draw_as_a_count() -> None:
    harness = contested(opposing=2)
    started(harness)
    digest: Any = call_as(harness, 2, "get_state").outcome.digest  # type: ignore[attr-defined]
    events = [event for element in digest if element.change == 4 for event in element.events]
    assert [type(e).__name__ for e in events if "Drawn" in type(e).__name__] == ["HiddenCardsDrawn"]


# @spec APP-037, APP-038
@NOT_BUILT
def test_a_seat_s_first_digest_holds_every_other_seat_s_change_since_the_game_began() -> None:
    harness = contested()
    call_as(harness, 1, "mulligan", keep=True)
    assert digest_of(call_as(harness, 2, "get_state")) == [(S1, 2)]


# @spec APP-038
@NOT_BUILT
def test_a_digest_holds_no_change_the_seat_itself_made() -> None:
    harness = contested()
    call_as(harness, 1, "mulligan", keep=True)
    call_as(harness, 2, "mulligan", keep=False)
    call_as(harness, 2, "mulligan", keep=True)
    assert digest_of(call_as(harness, 1, "get_state")) == [(S2, 3), (S2, 4)]


# @spec APP-039
@NOT_BUILT
def test_a_digest_takes_an_entry_s_stored_public_events_as_they_are() -> None:
    harness = contested()
    started(harness)
    stored = a_contested_log_entry(4, seat=1, table_turn=1, public=(EffectRecorded("as kept"),))
    harness.stores.records.append_entry(GAME, stored)
    digest: Any = call_as(harness, 2, "get_state").outcome.digest  # type: ignore[attr-defined]
    assert [element.events for element in digest] == [(EffectRecorded("as kept"),)]


# @spec APP-040
@NOT_BUILT
def test_a_goldfish_outcome_holds_no_digest_and_no_seat() -> None:
    harness = a_service(game_ids=IDS)
    harness.started_game()
    outcome: Any = harness.service.mulligan({"game_id": GAME, "keep": True}).outcome
    assert (outcome.digest, outcome.seat) == (None, None)


# @spec APP-079
@NOT_BUILT
def test_get_log_carries_no_digest_and_does_not_move_the_baseline() -> None:
    harness = contested()
    started(harness)
    call_as(harness, 2, "get_state")
    gain_a_life(harness)
    log: Any = call_as(harness, 2, "get_log").outcome
    assert log.digest is None
    assert digest_of(call_as(harness, 2, "get_state")) == [(S1, 4)]


# @spec APP-038, APP-036
@NOT_BUILT
def test_a_seat_whose_previous_response_carried_a_digest_is_not_shown_those_changes_again() -> None:
    harness = contested()
    started(harness)
    gain_a_life(harness)
    call_as(harness, 2, "get_state")
    assert digest_of(call_as(harness, 2, "get_state")) == []


# ------------------------------------------------------------------ every answer carries one


# @spec APP-058
@NOT_BUILT
def test_a_call_refused_because_it_is_not_the_seat_s_carries_the_digest() -> None:
    harness = contested()
    started(harness)
    gain_a_life(harness)
    answer = call_as(harness, 2, "advance")
    assert answer.outcome.status is Status.ERROR
    assert digest_of(answer) == [(S1, 4)]


# @spec APP-058
@NOT_BUILT
def test_a_call_whose_arguments_could_not_be_shaped_carries_the_digest() -> None:
    harness = contested()
    started(harness)
    gain_a_life(harness)
    seat_id = harness.seat_id(GAME, 2)
    answer = harness.service.malformed_call("play", {"game_id": seat_id, "card": 5}, ["card"])
    assert digest_of(answer) == [(S1, 4)]


# @spec APP-058
@NOT_BUILT
def test_a_call_whose_save_lost_a_race_carries_the_digest() -> None:
    harness = a_service(games=ChangedByAnotherWriter)
    harness.holding(a_game().and_an_opposing_seat().build(), HELD)
    harness.stores.records.append_entry(HELD, a_contested_log_entry(1, seat=2, table_turn=3))
    answer = harness.service.effect({"game_id": HELD, "source": "x", "delta": {"life": 1}})
    assert answer.outcome.status is Status.ERROR
    digest: Any = answer.outcome.digest  # type: ignore[attr-defined]
    assert [(element.seat, element.change) for element in digest] == [(S2, 1)]


# @spec APP-084
@NOT_BUILT
def test_a_failure_inside_the_service_carries_the_digest_assembled_after_the_rollback() -> None:
    harness = a_service(records=SnapshotsCannotBeWritten)
    harness.holding(a_game().in_step(Step.END).and_an_opposing_seat().build(), HELD)
    harness.stores.records.append_entry(HELD, a_contested_log_entry(1, seat=2, table_turn=3))
    answer = harness.service.advance({"game_id": HELD, "to": "cleanup"})
    assert answer.outcome.status is Status.ERROR
    digest: Any = answer.outcome.digest  # type: ignore[attr-defined]
    assert [(element.seat, element.change) for element in digest] == [(S2, 1)]


# @spec APP-082, GAME-126
@NOT_BUILT
def test_a_resend_carries_the_digest_of_the_moment_it_is_answered() -> None:
    harness = contested()
    call_as(harness, 1, "mulligan", keep=False, after=1)
    call_as(harness, 2, "mulligan", keep=False)
    answer = call_as(harness, 1, "mulligan", keep=False, after=1)
    assert any(isinstance(event, AlreadyApplied) for event in answer.outcome.events)
    assert digest_of(answer) == [(S2, 3)]


# @spec APP-083
def test_a_resend_s_game_summary_is_the_game_as_it_stands_when_the_resend_is_answered() -> None:
    harness = contested()
    call_as(harness, 1, "mulligan", keep=False, after=1)
    call_as(harness, 2, "mulligan", keep=False)
    answer = call_as(harness, 1, "mulligan", keep=False, after=1)
    assert answer.outcome.game is not None
    assert answer.outcome.game.change == 3


# @spec APP-083
def test_a_goldfish_resend_s_game_summary_is_the_game_as_it_stands() -> None:
    harness = a_service(game_ids=IDS)
    harness.started_game()
    harness.service.mulligan({"game_id": GAME, "keep": False, "after": 1})
    answer = harness.service.mulligan({"game_id": GAME, "keep": False, "after": 1})
    assert answer.outcome.game is not None
    assert answer.outcome.game.change == 2
