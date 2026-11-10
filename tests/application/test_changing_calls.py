"""The use cases that change a game: they load it, ask the domain, and save what it decided."""

from __future__ import annotations

from collections.abc import Callable

from mtg_goldfishing.application.outcome import Answer, Status
from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.events import (
    AlreadyApplied,
    CardPlayed,
    CardsRevealed,
    CheckKind,
    ErrorKind,
    GameEnded,
    Refused,
)
from mtg_goldfishing.domain.game.model import GameStatus, Zone
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import a_game
from tests.support.service import GAME_ID, ServiceHarness, a_service

HELIX = Card("Lightning Helix", (Face("Lightning Helix", ManaString.parse("{R}{W}"), "Instant"),))
LOOK = {"look": {"n": 2, "from": "top", "rest": "graveyard"}}


def harness_with_forest_in_hand() -> ServiceHarness:
    harness = a_service()
    harness.holding(a_game().with_hand("Forest").build())
    return harness


def errors_of(summary: object) -> list[ErrorKind]:
    assert isinstance(summary, Refused), summary
    return [error.kind for error in summary.errors]


# ------------------------------------------------------------------ each tool reaches its domain


def test_keeping_a_hand_starts_the_game() -> None:
    harness = a_service()
    harness.holding(a_game().in_mulligan().with_hand("Forest").with_library("Island").build())
    answer = harness.service.mulligan({"game_id": GAME_ID, "keep": True})
    assert answer.outcome.status is Status.OK
    assert harness.game().status is GameStatus.ACTIVE


def test_playing_a_land_puts_it_on_the_battlefield() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    assert answer.outcome.status is Status.OK
    assert [card.name for card in harness.game().battlefield] == ["Forest"]


def test_an_effect_changes_the_game_as_its_delta_says() -> None:
    harness = a_service()
    harness.holding(a_game().with_life(40).build())
    harness.service.effect({"game_id": GAME_ID, "source": "Phyrexian Arena", "delta": {"life": -1}})
    assert harness.game().life == 39


def test_an_applied_call_that_leaves_a_choice_pending_is_answered_choice() -> None:
    harness = a_service()
    harness.holding(a_game().with_library("Island", "Forest", "Swamp").build())
    answer = harness.service.effect({"game_id": GAME_ID, "source": "Ponder", "delta": LOOK})
    assert answer.outcome.status is Status.CHOICE


def test_choosing_finishes_the_pending_choice() -> None:
    harness = a_service()
    harness.holding(a_game().with_library("Island", "Forest", "Swamp").build())
    harness.service.effect({"game_id": GAME_ID, "source": "Ponder", "delta": LOOK})
    pending = harness.game().pending_choice
    assert pending is not None
    answer = harness.service.choose(
        {"game_id": GAME_ID, "choice_id": pending.choice_id, "selections": {"hand": ["Forest"]}}
    )
    assert answer.outcome.status is Status.OK
    assert [card.name for card in harness.game().hand] == ["Forest"]


def test_attacking_declares_the_attack() -> None:
    harness = a_service()
    harness.holding(a_game().with_battlefield("Grizzly Bears").build())
    answer = harness.service.attack({"game_id": GAME_ID, "attackers": ["Grizzly Bears"]})
    assert answer.outcome.status is Status.OK
    assert harness.game().declared_attack is not None


def test_advancing_moves_to_the_next_step() -> None:
    harness = a_service()
    harness.holding(a_game().in_step(Step.MAIN1, turn=3).build())
    harness.service.advance({"game_id": GAME_ID})
    assert harness.game().step is Step.BEGIN_COMBAT


def test_ending_a_game_records_the_result() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    answer = harness.service.end_game({"game_id": GAME_ID, "result": "win", "notes": "fast"})
    assert answer.outcome.summary == GameEnded("win", "fast")
    assert harness.game().status is GameStatus.ENDED


# ------------------------------------------------------------------ cards from outside the game


# @spec APP-022
def test_a_card_played_from_outside_the_game_is_made_from_the_catalog_s_card_data() -> None:
    harness = a_service(cards=[HELIX])
    harness.holding(a_game().with_battlefield("Mountain", "Plains").build())
    answer = harness.service.play(
        {"game_id": GAME_ID, "card": "Lightning Helix", "from": "outside"}
    )
    assert answer.outcome.status is Status.OK
    assert [card.name for card in harness.game().in_zone(Zone.GRAVEYARD)] == ["Lightning Helix"]


# @spec APP-022
def test_a_card_from_outside_that_the_catalog_does_not_know_asks_for_a_definition() -> None:
    harness = a_service(cards=[])
    harness.holding(a_game().with_battlefield("Mountain", "Plains").build())
    answer = harness.service.play(
        {"game_id": GAME_ID, "card": "Lightning Helix", "from": "outside"}
    )
    assert errors_of(answer.outcome.summary) == [ErrorKind.CARD_DATA_NEEDED]


# ------------------------------------------------------------------ outcomes and saving


# @spec APP-009
def test_an_applied_call_s_outcome_carries_the_changed_game_s_summary() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    deck = harness.stores.decks.get("dtest")
    assert deck is not None
    assert answer.outcome.game == summarize(harness.game(), deck)


# @spec APP-009
def test_a_refused_call_s_outcome_carries_the_unchanged_game_s_summary() -> None:
    harness = a_service()
    harness.holding(a_game().with_hand("Sol Ring").build())
    before = harness.game()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Sol Ring"})
    deck = harness.stores.decks.get("dtest")
    assert deck is not None
    assert answer.outcome.game == summarize(before, deck)


def test_an_applied_call_increases_the_change_number() -> None:
    harness = harness_with_forest_in_hand()
    harness.service.play({"game_id": GAME_ID, "card": "Forest"})
    assert harness.game().change == 1


# @spec APP-017
def test_an_applied_call_saves_the_game_and_its_log_entry() -> None:
    harness = harness_with_forest_in_hand()
    harness.service.play({"game_id": GAME_ID, "card": "Forest", "reason": "land drop"})
    entries = harness.records().entries
    assert [(e.seq, e.tool, e.card, e.reason) for e in entries] == [
        (1, "play", "Forest", "land drop")
    ]
    assert harness.version() == 2


# @spec APP-017
def test_an_applied_call_entering_cleanup_saves_the_turn_snapshot() -> None:
    harness = a_service()
    harness.holding(a_game().in_step(Step.END, turn=4).build())
    harness.service.advance({"game_id": GAME_ID})
    assert [(s.turn, s.written_by) for s in harness.records().snapshots] == [(4, 1)]


# @spec APP-006, APP-023
def test_a_call_failing_a_rule_check_is_answered_rejected_with_the_domain_s_checks() -> None:
    harness = a_service()
    harness.holding(a_game().with_hand("Sol Ring").build())
    answer = harness.service.play({"game_id": GAME_ID, "card": "Sol Ring"})
    assert answer.outcome.status is Status.REJECTED
    assert isinstance(answer.outcome.summary, Refused)
    assert [check.kind for check in answer.outcome.summary.checks] == [CheckKind.COST_NOT_PAYABLE]


def test_a_call_with_an_error_is_answered_error() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Island"})
    assert answer.outcome.status is Status.ERROR
    assert errors_of(answer.outcome.summary) == [ErrorKind.CARD_NOT_IN_ZONE]


# @spec APP-018, REC-002
def test_a_refused_call_saves_nothing_about_the_game() -> None:
    harness = a_service()
    harness.holding(a_game().with_hand("Sol Ring").build())
    before = harness.game()
    harness.service.play({"game_id": GAME_ID, "card": "Sol Ring"})
    assert (harness.game(), harness.version()) == (before, 1)
    assert harness.records().entries == ()


def test_an_overridden_rule_check_is_applied() -> None:
    harness = a_service()
    harness.holding(a_game().with_hand("Sol Ring").build())
    answer = harness.service.play(
        {"game_id": GAME_ID, "card": "Sol Ring", "override": "paid with a ritual"}
    )
    assert answer.outcome.status is Status.OK
    assert harness.records().entries[0].override == "paid with a ritual"


def test_an_override_that_is_not_text_is_a_malformed_argument() -> None:
    harness = a_service()
    harness.holding(a_game().with_hand("Sol Ring").build())
    answer = harness.service.play({"game_id": GAME_ID, "card": "Sol Ring", "override": 1})
    assert isinstance(answer.outcome.summary, Refused)
    assert [(e.kind, e.subject) for e in answer.outcome.summary.errors] == [
        (ErrorKind.MALFORMED_ARGUMENT, "override")
    ]


# ------------------------------------------------------------------ games and statuses


# @spec GAME-053
def test_a_call_naming_no_game_is_an_error_with_no_game_summary() -> None:
    harness = a_service()
    answer = harness.service.play({"game_id": "gnosuchgame", "card": "Forest"})
    assert errors_of(answer.outcome.summary) == [ErrorKind.UNKNOWN_GAME]
    assert answer.outcome.game is None


# @spec GAME-053
def test_a_call_naming_no_game_creates_no_game() -> None:
    harness = a_service()
    harness.service.advance({"game_id": "gnosuchgame"})
    assert harness.stores.games.get("gnosuchgame") is None


def test_a_tool_the_game_s_status_does_not_accept_is_an_error() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.mulligan({"game_id": GAME_ID, "keep": True})
    assert errors_of(answer.outcome.summary) == [ErrorKind.NOT_ACCEPTED_IN_STATUS]


# ------------------------------------------------------------------ the change number


def test_a_call_following_the_current_change_number_is_applied() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest", "after": 0})
    assert answer.outcome.status is Status.OK


def test_a_call_following_a_stale_change_number_is_an_error() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest", "after": 5})
    assert errors_of(answer.outcome.summary) == [ErrorKind.STALE_CHANGE]


def test_an_after_that_is_not_a_whole_number_is_a_malformed_argument() -> None:
    harness = harness_with_forest_in_hand()
    answer = harness.service.play({"game_id": GAME_ID, "card": "Forest", "after": "0"})
    assert isinstance(answer.outcome.summary, Refused)
    assert [(e.kind, e.subject) for e in answer.outcome.summary.errors] == [
        (ErrorKind.MALFORMED_ARGUMENT, "after")
    ]


def test_a_resend_is_answered_with_the_original_report_and_already_applied() -> None:
    harness = harness_with_forest_in_hand()
    call = {"game_id": GAME_ID, "card": "Forest", "after": 0}
    first = harness.service.play(call)
    again = harness.service.play(call)
    assert isinstance(again.outcome.summary, CardPlayed)
    assert again.outcome.summary == first.outcome.summary
    assert again.outcome.events == (*first.outcome.events, AlreadyApplied(1))


# @spec REC-002
def test_a_resend_changes_nothing_and_adds_no_log_entry() -> None:
    harness = harness_with_forest_in_hand()
    call = {"game_id": GAME_ID, "card": "Forest", "after": 0}
    harness.service.play(call)
    harness.service.play(call)
    assert (harness.game().change, harness.version()) == (1, 2)
    assert [e.seq for e in harness.records().entries] == [1]


# ------------------------------------------------------------- resends after the status changed


def sent_twice(send: Callable[[dict[str, object]], Answer], call: dict[str, object]) -> Answer:
    """The answer to the second of two identical calls."""
    send(call)
    return send(call)


def is_a_resend(answer: Answer) -> bool:
    return any(isinstance(event, AlreadyApplied) for event in answer.outcome.events)


# @spec GAME-054
def test_end_game_resent_after_the_game_ended_is_answered_as_a_resend() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    call = {"game_id": GAME_ID, "result": "win", "notes": "fast", "after": 0}
    again = sent_twice(harness.service.end_game, call)
    assert (again.outcome.summary, is_a_resend(again)) == (GameEnded("win", "fast"), True)


# @spec GAME-054
def test_keeping_a_hand_resent_once_the_game_is_active_is_answered_as_a_resend() -> None:
    harness = a_service()
    harness.holding(a_game().in_mulligan().with_hand("Forest").with_library("Island").build())
    call = {"game_id": GAME_ID, "keep": True, "after": 0}
    again = sent_twice(harness.service.mulligan, call)
    assert (again.outcome.status, is_a_resend(again)) == (Status.OK, True)


# @spec GAME-054
def test_an_effect_that_left_a_choice_pending_resent_is_answered_choice_with_its_cards() -> None:
    harness = a_service()
    harness.holding(a_game().with_library("Island", "Forest", "Swamp").build())
    call = {"game_id": GAME_ID, "source": "Ponder", "delta": LOOK, "after": 0}
    again = sent_twice(harness.service.effect, call)
    revealed = [event for event in again.outcome.events if isinstance(event, CardsRevealed)]
    assert (again.outcome.status, len(revealed), is_a_resend(again)) == (Status.CHOICE, 1, True)


# @spec GAME-054
def test_a_play_that_left_a_choice_pending_resent_is_answered_choice_with_its_cards() -> None:
    harness = a_service()
    harness.holding(
        a_game()
        .with_hand("Ponder")
        .with_battlefield("Island")
        .with_library("Island", "Forest", "Swamp")
        .build()
    )
    call = {"game_id": GAME_ID, "card": "Ponder", "delta": LOOK, "after": 0}
    again = sent_twice(harness.service.play, call)
    revealed = [event for event in again.outcome.events if isinstance(event, CardsRevealed)]
    assert (again.outcome.status, len(revealed), is_a_resend(again)) == (Status.CHOICE, 1, True)


# @spec GAME-054
def test_a_choice_resent_after_it_was_made_is_answered_as_a_resend() -> None:
    harness = a_service()
    harness.holding(a_game().with_library("Island", "Forest", "Swamp").build())
    harness.service.effect({"game_id": GAME_ID, "source": "Ponder", "delta": LOOK})
    pending = harness.game().pending_choice
    assert pending is not None
    call = {
        "game_id": GAME_ID,
        "choice_id": pending.choice_id,
        "selections": {"hand": ["Forest"]},
        "after": 1,
    }
    again = sent_twice(harness.service.choose, call)
    assert (again.outcome.status, is_a_resend(again)) == (Status.OK, True)


# @spec GAME-054
def test_a_resend_after_the_status_changed_changes_nothing() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    call = {"game_id": GAME_ID, "result": "win", "notes": "fast", "after": 0}
    sent_twice(harness.service.end_game, call)
    assert (harness.game().change, [e.seq for e in harness.records().entries]) == (1, [1])


# @spec GAME-052
def test_a_call_that_is_not_a_resend_is_refused_in_a_status_that_does_not_accept_it() -> None:
    harness = a_service()
    harness.holding(a_game().build())
    harness.service.end_game({"game_id": GAME_ID, "result": "win", "after": 0})
    answer = harness.service.end_game({"game_id": GAME_ID, "result": "loss", "after": 0})
    assert errors_of(answer.outcome.summary) == [ErrorKind.NOT_ACCEPTED_IN_STATUS]
