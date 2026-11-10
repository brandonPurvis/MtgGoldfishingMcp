"""The `new_game` use case: draw the id and seed, let the domain deal, keep the game."""

from __future__ import annotations

from mtg_goldfishing.application.outcome import Status
from mtg_goldfishing.domain.events import ErrorKind, GameStarted, Refused
from mtg_goldfishing.domain.game.model import GameStatus
from mtg_goldfishing.domain.game.summary import summarize
from tests.support.service import a_service


# @spec GAME-006
def test_a_new_game_s_id_is_g_followed_by_the_id_source_s_ten_characters() -> None:
    harness = a_service(game_ids=["k3v9q2m8x1"])
    answer = harness.started_game()
    assert isinstance(answer.outcome.summary, GameStarted)
    assert answer.outcome.summary.game_id == "gk3v9q2m8x1"


# @spec GAME-004
def test_a_new_game_without_a_seed_is_seeded_from_the_id_source() -> None:
    harness = a_service(seeds=[424242])
    answer = harness.started_game()
    assert isinstance(answer.outcome.summary, GameStarted)
    assert answer.outcome.summary.seed == 424242
    assert harness.game("gabcdefghij").seed == 424242


def test_a_new_game_with_a_seed_uses_that_seed() -> None:
    harness = a_service(seeds=[424242])
    answer = harness.started_game(seed=99)
    assert isinstance(answer.outcome.summary, GameStarted)
    assert answer.outcome.summary.seed == 99


def test_a_new_game_is_kept_at_change_number_one_waiting_for_mulligans() -> None:
    harness = a_service()
    harness.started_game()
    game = harness.game("gabcdefghij")
    assert (game.status, game.change) == (GameStatus.MULLIGAN, 1)


def test_a_new_game_s_first_log_entry_is_numbered_one() -> None:
    harness = a_service()
    harness.started_game()
    assert [(e.seq, e.tool) for e in harness.records("gabcdefghij").entries] == [(1, "new_game")]


# @spec APP-009
def test_a_new_game_s_outcome_carries_the_game_summary() -> None:
    harness = a_service()
    answer = harness.started_game()
    game = harness.game("gabcdefghij")
    deck = harness.stores.decks.get(game.deck_id)
    assert deck is not None
    assert answer.outcome.game == summarize(game, deck)


# @spec APP-008
def test_two_games_from_the_same_ids_and_deck_are_identical() -> None:
    first, second = a_service(), a_service()
    first.started_game()
    second.started_game()
    assert first.game("gabcdefghij") == second.game("gabcdefghij")


def test_a_new_game_on_an_unknown_deck_is_an_error_and_keeps_no_game() -> None:
    harness = a_service()
    answer = harness.service.new_game({"deck_id": "dnosuchdeck"})
    assert answer.outcome.status is Status.ERROR
    assert isinstance(answer.outcome.summary, Refused)
    assert answer.outcome.summary.errors[0].kind is ErrorKind.UNKNOWN_DECK
    assert harness.stores.games.get("gabcdefghij") is None


def test_a_seed_that_is_not_a_whole_number_is_a_malformed_argument() -> None:
    harness = a_service()
    answer = harness.started_game(seed="lucky")
    assert isinstance(answer.outcome.summary, Refused)
    assert [(e.kind, e.subject) for e in answer.outcome.summary.errors] == [
        (ErrorKind.MALFORMED_ARGUMENT, "seed")
    ]


def test_a_new_game_s_call_record_names_the_game_it_started() -> None:
    harness = a_service()
    harness.started_game()
    record = harness.last_call()
    assert (record.game_id, record.tool, record.change) == ("gabcdefghij", "new_game", 1)
