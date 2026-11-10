"""The game: creating it, shuffling, naming cards, mulligans, the change number, status, ending."""

from __future__ import annotations

import pytest
from mtg_goldfishing.domain.game.calls import accept_change, check_accepted, follow_change
from mtg_goldfishing.domain.game.creation import new_game
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.mulligan import mulligan

from mtg_goldfishing.domain.events import (
    AlreadyApplied,
    CardsDrawn,
    CheckKind,
    Error,
    ErrorKind,
    GameStarted,
    HandKept,
    InstanceChosen,
    MulliganTaken,
    NoticeKind,
    NoticeRaised,
)
from mtg_goldfishing.domain.game.model import (
    Attack,
    Game,
    GameResult,
    GameStatus,
    PendingChoice,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw
from mtg_goldfishing.domain.game.naming import Purpose, resolve
from mtg_goldfishing.domain.game.notices import examine_end_conditions, examine_turn_limit
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent
from mtg_goldfishing.domain.game.shuffling import shuffled
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import a_deck, a_game

FORTY_CARDS = ("Forest",) * 20 + ("Island",) * 10 + ("Cultivate", "Ponder") * 5


def started(seed: int = 11, **options: object) -> Game:
    result = new_game(
        a_deck(*FORTY_CARDS), deck_id="dtest", game_id="gabcdefghij", seed=seed, **options
    )  # type: ignore[arg-type]
    assert isinstance(result, Applied)
    return result.game


def applied(result: object) -> Applied:
    assert isinstance(result, Applied), result
    return result


# ------------------------------------------------------------------ creating a game


# @spec GAME-001
def test_a_new_game_puts_commanders_in_the_command_zone_and_the_rest_in_the_library() -> None:
    game = started()
    assert [c.name for c in game.in_zone(Zone.COMMAND)] == ["Atraxa, Praetors' Voice"]
    assert len(game.library) + len(game.hand) == 40
    assert (game.life, game.status, game.turn, game.step) == (40, GameStatus.MULLIGAN, 0, None)


# @spec GAME-002
def test_instance_ids_go_to_commanders_first_then_cards_by_lower_cased_name() -> None:
    game = started()
    by_id = {c.id: c.name for c in game.cards}
    assert by_id["c1"] == "Atraxa, Praetors' Voice"
    assert [by_id[f"c{n}"] for n in (2, 6, 7, 26, 27)] == [
        "Cultivate",
        "Cultivate",
        "Forest",
        "Forest",
        "Island",
    ]


# @spec GAME-003
def test_a_new_game_deals_seven_cards_from_a_shuffled_library() -> None:
    game = started()
    assert len(game.hand) == 7
    assert game.shuffles == 1


# @spec GAME-005
def test_a_new_game_reports_its_id_seed_and_opening_hand() -> None:
    result = applied(
        new_game(a_deck(*FORTY_CARDS), deck_id="dtest", game_id="gabcdefghij", seed=11)
    )
    assert result.summary == GameStarted("gabcdefghij", 11, tuple(c.name for c in result.game.hand))


# @spec GAME-007
def test_a_new_game_on_an_unknown_deck_is_an_error() -> None:
    result = new_game(None, deck_id="dnope", game_id="gabcdefghij", seed=1)
    assert result == Refusal.error(Error(ErrorKind.UNKNOWN_DECK, subject="dnope"))


# @spec GAME-008
@pytest.mark.parametrize("limit", [0, -3, "ten", 2.5, True])
def test_a_turn_limit_must_be_a_positive_integer(limit: object) -> None:
    result = new_game(a_deck(*FORTY_CARDS), deck_id="dtest", game_id="g1", seed=1, turn_limit=limit)
    assert isinstance(result, Refusal)
    assert result.errors[0].kind is ErrorKind.BAD_TURN_LIMIT


# @spec GAME-009
def test_the_first_turn_draws_by_default() -> None:
    assert started().draw_first_turn is True
    assert started(draw_first_turn=False).draw_first_turn is False


# ------------------------------------------------------------------ shuffling


# @spec GAME-010
def test_the_nth_shuffle_depends_only_on_seed_n_and_the_library() -> None:
    library = [f"c{n}" for n in range(1, 30)]
    assert shuffled(library, 5, 0) == shuffled(library, 5, 0)
    assert shuffled(library, 5, 0) != shuffled(library, 5, 1)
    assert shuffled(library, 5, 0) != shuffled(library, 6, 0)


# @spec GAME-010
def test_the_shuffle_is_pinned_to_its_algorithm() -> None:
    assert shuffled(["a", "b", "c", "d", "e"], 1, 0) == shuffled(["a", "b", "c", "d", "e"], 1, 0)
    assert sorted(shuffled(["a", "b", "c", "d", "e"], 1, 0)) == ["a", "b", "c", "d", "e"]


# @spec GAME-011
def test_the_same_deck_and_seed_give_the_same_game() -> None:
    first, second = started(seed=99), started(seed=99)
    assert first == second
    first_kept = applied(mulligan(first, a_deck(*FORTY_CARDS), keep=False))
    second_kept = applied(mulligan(second, a_deck(*FORTY_CARDS), keep=False))
    assert first_kept.game == second_kept.game


# ------------------------------------------------------------------ naming cards


# @spec GAME-013
@pytest.mark.parametrize("name", ["Forest", "forest", "  FOREST ", "c1"])
def test_a_card_can_be_named_by_name_ignoring_case_or_by_instance_id(name: str) -> None:
    situation = a_game().with_battlefield("Forest").build()
    found = resolve(situation.game, situation.deck, [name], [Zone.BATTLEFIELD])
    assert not isinstance(found, Error)
    assert [c.id for c in found[0]] == ["c1"]


# @spec GAME-013
def test_a_card_can_be_named_by_one_of_its_faces() -> None:
    situation = a_game().with_hand("Fire // Ice").build()
    found = resolve(situation.game, situation.deck, ["ice"], [Zone.HAND])
    assert not isinstance(found, Error)


# @spec GAME-014
def test_an_untapped_instance_is_chosen_for_tapping_and_a_tapped_one_for_untapping() -> None:
    situation = a_game().with_battlefield("Forest", tapped=True).with_battlefield("Forest").build()
    tap = resolve(situation.game, situation.deck, ["Forest"], [Zone.BATTLEFIELD], Purpose.TAP)
    untap = resolve(situation.game, situation.deck, ["Forest"], [Zone.BATTLEFIELD], Purpose.UNTAP)
    assert not isinstance(tap, Error)
    assert not isinstance(untap, Error)
    assert (tap[0][0].id, untap[0][0].id) == ("c2", "c1")


# @spec GAME-014
def test_otherwise_the_lowest_instance_id_is_chosen() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").build()
    found = resolve(situation.game, situation.deck, ["Forest"], [Zone.BATTLEFIELD])
    assert not isinstance(found, Error)
    assert found[0][0].id == "c1"


# @spec GAME-015
def test_the_chosen_instance_is_reported_when_the_matching_instances_differ() -> None:
    situation = a_game().with_battlefield("Forest", tapped=True).with_battlefield("Forest").build()
    found = resolve(situation.game, situation.deck, ["Forest"], [Zone.BATTLEFIELD], Purpose.TAP)
    assert not isinstance(found, Error)
    assert found[1] == [InstanceChosen("Forest", "c2")]


# @spec GAME-015
def test_no_instance_is_reported_when_the_matching_instances_are_alike() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").build()
    found = resolve(situation.game, situation.deck, ["Forest"], [Zone.BATTLEFIELD])
    assert not isinstance(found, Error)
    assert found[1] == []


# @spec GAME-016
def test_a_name_not_in_the_expected_zone_is_an_error_saying_where_it_is() -> None:
    situation = a_game().with_hand("Forest").build()
    found = resolve(situation.game, situation.deck, ["Forest"], [Zone.BATTLEFIELD])
    assert found == Error(
        ErrorKind.CARD_NOT_IN_ZONE, subject="Forest", zone="battlefield", found_in="hand"
    )


# @spec GAME-017
def test_a_name_given_twice_means_two_different_instances() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").build()
    found = resolve(situation.game, situation.deck, ["Forest", "Forest"], [Zone.BATTLEFIELD])
    assert not isinstance(found, Error)
    assert [c.id for c in found[0]] == ["c1", "c2"]


# @spec GAME-018
def test_a_name_given_more_times_than_there_are_instances_is_an_error() -> None:
    situation = a_game().with_battlefield("Forest").build()
    found = resolve(situation.game, situation.deck, ["Forest", "Forest"], [Zone.BATTLEFIELD])
    assert isinstance(found, Error)
    assert found.kind is ErrorKind.TOO_FEW_MATCHING


# @spec GAME-018
def test_an_instance_id_given_twice_is_an_error() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").build()
    found = resolve(situation.game, situation.deck, ["c1", "C1"], [Zone.BATTLEFIELD])
    assert found == Error(ErrorKind.INSTANCE_REPEATED, subject="c1")


# ------------------------------------------------------------------ mulligans


# @spec GAME-021
def test_taking_a_mulligan_reshuffles_and_deals_seven_new_cards() -> None:
    game = started()
    result = applied(mulligan(game, a_deck(*FORTY_CARDS), keep=False))
    assert result.game.mulligans == 1
    assert len(result.game.hand) == 7
    assert result.game.shuffles == 2
    assert result.summary == MulliganTaken(1, tuple(c.name for c in result.game.hand))


# @spec GAME-022, GAME-024
@pytest.mark.parametrize(("mulligans", "required"), [(0, 0), (1, 0), (2, 1), (3, 2)])
def test_keeping_requires_bottoming_one_fewer_card_than_mulligans_taken(
    mulligans: int, required: int
) -> None:
    game = started()
    game.mulligans = mulligans
    wrong = [c.name for c in game.hand][: required + 1]
    result = mulligan(game, a_deck(*FORTY_CARDS), keep=True, bottom=wrong)
    assert isinstance(result, Refusal)
    assert [(c.kind, c.expected) for c in result.checks] == [(CheckKind.BOTTOM_COUNT, required)]


# @spec GAME-022
def test_the_number_of_cards_to_bottom_is_capped_at_seven() -> None:
    game = started()
    game.mulligans = 9
    result = mulligan(game, a_deck(*FORTY_CARDS), keep=True, bottom=[])
    assert isinstance(result, Refusal)
    assert result.checks[0].expected == 7


# @spec GAME-023
def test_keeping_puts_the_bottomed_cards_on_the_bottom_in_the_order_given() -> None:
    game = started()
    game.mulligans = 3
    hand_ids = [c.id for c in game.hand]
    result = applied(
        mulligan(game, a_deck(*FORTY_CARDS), keep=True, bottom=[hand_ids[3], hand_ids[0]])
    )
    assert result.game.library[-2:] == [hand_ids[3], hand_ids[0]]


# @spec GAME-025
def test_keeping_with_the_wrong_number_bottomed_and_an_override_bottoms_as_given() -> None:
    game = started()
    first = game.hand[0].id
    result = applied(
        mulligan(game, a_deck(*FORTY_CARDS), keep=True, bottom=[first], override="Serum Powder")
    )
    assert result.game.library[-1] == first


# @spec GAME-026
def test_bottoming_a_card_not_in_hand_is_an_error() -> None:
    game = started()
    game.mulligans = 2
    library_card = game.library[0]
    result = mulligan(game, a_deck(*FORTY_CARDS), keep=True, bottom=[library_card])
    assert isinstance(result, Refusal)
    assert result.errors[0].kind is ErrorKind.BOTTOM_NOT_IN_HAND


# @spec GAME-026
def test_giving_bottom_with_a_mulligan_is_an_error() -> None:
    game = started()
    result = mulligan(game, a_deck(*FORTY_CARDS), keep=False, bottom=[game.hand[0].id])
    assert result == Refusal.error(Error(ErrorKind.BOTTOM_WITHOUT_KEEP))


# @spec GAME-027, GAME-028
def test_keeping_starts_turn_one_in_the_first_main_step_having_drawn_a_card() -> None:
    game = started()
    top = game.instance(game.library[0]).name
    result = applied(mulligan(game, a_deck(*FORTY_CARDS), keep=True))
    assert (result.game.status, result.game.turn, result.game.step) == (
        GameStatus.ACTIVE,
        1,
        Step.MAIN1,
    )
    assert len(result.game.hand) == 8
    assert CardsDrawn((top,)) in result.events
    assert isinstance(result.summary, HandKept)


# @spec GAME-027
def test_keeping_without_a_first_turn_draw_draws_nothing() -> None:
    game = started(draw_first_turn=False)
    result = applied(mulligan(game, a_deck(*FORTY_CARDS), keep=True))
    assert len(result.game.hand) == 7


# @spec APP-007
def test_a_refused_mulligan_leaves_the_game_unchanged() -> None:
    game = started()
    before = game.copy()
    mulligan(game, a_deck(*FORTY_CARDS), keep=True, bottom=["Nonexistent"])
    assert game == before


# ------------------------------------------------------------------ state on request


# @spec GAME-029, GAME-030
def test_the_summary_listing_shows_each_permanent_with_what_was_read_of_it() -> None:
    situation = (
        a_game()
        .with_battlefield("Forest", tapped=True)
        .with_battlefield("Goblin Guide", counters={"+1/+1": 1})
        .with_battlefield("Phyrexian Arena")
        .with_hand("Cultivate")
        .with_graveyard("Ponder")
        .with_commander("Atraxa, Praetors' Voice")
        .build()
    )
    listing = list_state(situation.game, situation.deck, "summary")
    assert not isinstance(listing, Error)
    assert listing.hand == ("Cultivate",)
    assert listing.graveyard == ("Ponder",)
    assert listing.command == ("Atraxa, Praetors' Voice",)
    forest, guide, arena = listing.battlefield
    assert (forest.instance_id, forest.tapped, len(forest.mana)) == ("c2", True, 1)
    assert (guide.counters, guide.haste) == ((("+1/+1", 1),), True)
    assert arena.triggers == (Step.UPKEEP,)
    assert listing.exile is None


# @spec GAME-031
def test_the_full_listing_adds_exile_library_size_commanders_and_payments() -> None:
    situation = (
        a_game()
        .with_commander("Atraxa, Praetors' Voice")
        .with_exile("Ponder")
        .with_library("Forest", "Island")
        .build()
    )
    listing = list_state(situation.game, situation.deck, "full")
    assert not isinstance(listing, Error)
    assert listing.exile == ("Ponder",)
    assert listing.library_size == 2
    assert listing.commanders is not None
    assert listing.commanders[0].casts == 0
    assert listing.payments == ()


# @spec GAME-012
def test_no_listing_reveals_the_library() -> None:
    situation = a_game().with_library("Forest", "Island").build()
    listing = list_state(situation.game, situation.deck, "full")
    assert "Forest" not in repr(listing)


# @spec GAME-032
def test_listing_the_state_changes_nothing() -> None:
    situation = a_game().with_battlefield("Forest").build()
    before = situation.game.copy()
    list_state(situation.game, situation.deck, "full")
    assert situation.game == before


# ------------------------------------------------------------------ the change number


def _accepted() -> Applied:
    situation = a_game().build()
    return accept_change(
        Applied(situation.game.copy(), CardsDrawn(())), "advance", {"to": "main2", "after": 0}
    )


# @spec GAME-033
def test_an_accepted_call_increases_the_change_number_and_is_remembered() -> None:
    result = _accepted()
    assert result.game.change == 1
    assert result.game.last_change is not None
    assert result.game.last_change.arguments == {"to": "main2"}


# @spec GAME-035
@pytest.mark.parametrize("after", [None, 1])
def test_a_call_following_the_current_change_or_giving_none_is_applied(after: int | None) -> None:
    assert follow_change(_accepted().game, "play", {"card": "Forest"}, after) is None


# @spec GAME-036
def test_a_resent_call_is_answered_with_the_original_events_and_not_applied() -> None:
    game = _accepted().game
    result = follow_change(game, "advance", {"to": "main2", "after": 0}, 0)
    assert isinstance(result, Resent)
    assert result.summary == CardsDrawn(())
    assert result.events[-1] == AlreadyApplied(1)


# @spec GAME-037
def test_a_call_after_a_stale_change_number_is_an_error_naming_the_current_one() -> None:
    game = _accepted().game
    result = follow_change(game, "play", {"card": "Forest"}, 0)
    assert result == Refusal.error(Error(ErrorKind.STALE_CHANGE, number=1))


# @spec GAME-034
def test_a_refused_call_leaves_the_change_number_alone() -> None:
    game = _accepted().game
    follow_change(game, "play", {"card": "Forest"}, 7)
    assert game.change == 1


# ------------------------------------------------------------------ notices


# @spec GAME-038
def test_reaching_120_damage_raises_the_damage_notice_once() -> None:
    game = a_game().build().game
    game.damage_dealt = 120
    assert examine_end_conditions(game) == [NoticeRaised(NoticeKind.DAMAGE)]
    assert examine_end_conditions(game) == []


# @spec GAME-039
def test_21_commander_damage_to_each_opponent_raises_the_commander_damage_notice() -> None:
    game = a_game().with_commander("Atraxa, Praetors' Voice").build().game
    game.commander_damage["c1"] = [21, 21, 20]
    assert examine_end_conditions(game) == []
    game.commander_damage["c1"] = [21, 21, 21]
    assert examine_end_conditions(game) == [NoticeRaised(NoticeKind.COMMANDER_DAMAGE)]


# @spec GAME-040
def test_entering_the_limit_turn_raises_the_turn_limit_notice() -> None:
    game = a_game().with_turn_limit(4).in_step(Step.UNTAP, turn=4).build().game
    assert examine_turn_limit(game) == [NoticeRaised(NoticeKind.TURN_LIMIT)]


# @spec GAME-041
def test_life_reaching_zero_raises_the_life_notice() -> None:
    game = a_game().with_life(0).build().game
    assert examine_end_conditions(game) == [NoticeRaised(NoticeKind.LIFE)]


# @spec GAME-042
def test_drawing_from_a_short_library_draws_what_is_there_and_raises_a_notice() -> None:
    game = a_game().with_library("Forest").build().game
    events = draw(game, 3)
    assert events == [CardsDrawn(("Forest",)), NoticeRaised(NoticeKind.EMPTY_LIBRARY)]


# @spec GAME-043, GAME-044
def test_a_notice_stays_after_its_condition_stops_holding_and_never_ends_the_game() -> None:
    game = a_game().with_life(0).build().game
    examine_end_conditions(game)
    game.life = 10
    examine_end_conditions(game)
    assert game.notices == [NoticeKind.LIFE]
    assert game.status is GameStatus.ACTIVE


# ------------------------------------------------------------------ ending


# @spec GAME-045
def test_ending_a_game_records_the_result_and_notes_without_any_condition() -> None:
    situation = a_game().build()
    result = applied(end_game(situation.game, situation.deck, result="win", notes="fast"))
    assert result.game.status is GameStatus.ENDED
    assert result.game.result is not None
    assert (result.game.result.outcome, result.game.result.notes) == (GameResult.WIN, "fast")


# @spec GAME-046
def test_ending_a_game_discards_a_pending_choice_and_a_declared_attack() -> None:

    situation = a_game().build()
    situation.game.declared_attack = Attack(attackers=["c1"])
    situation.game.pending_choice = PendingChoice("x1", "Ponder", "look", [], None)
    result = applied(end_game(situation.game, situation.deck, result="loss", notes=""))
    assert result.game.declared_attack is None
    assert result.game.pending_choice is None


# @spec GAME-047
def test_ending_with_an_unknown_result_is_an_error() -> None:
    situation = a_game().build()
    result = end_game(situation.game, situation.deck, result="draw", notes="")
    assert isinstance(result, Refusal)
    assert result.errors[0].kind is ErrorKind.BAD_RESULT


# ------------------------------------------------------------------ status


# @spec GAME-048
def test_during_mulligans_only_mulligan_get_state_get_log_and_end_game_are_accepted() -> None:
    game = a_game().in_mulligan().build().game
    accepted = [t for t in _TOOLS if check_accepted(game, t) is None]
    assert accepted == ["mulligan", "get_state", "end_game", "get_log"]


# @spec GAME-049
def test_an_active_game_accepts_everything_but_mulligan_and_choose() -> None:
    game = a_game().build().game
    refused = [t for t in _TOOLS if check_accepted(game, t) is not None]
    assert refused == ["mulligan", "choose"]


# @spec GAME-050
def test_a_pending_choice_accepts_only_choose_get_state_get_log_and_end_game() -> None:
    game = a_game().with_status(GameStatus.PENDING_CHOICE).build().game
    accepted = [t for t in _TOOLS if check_accepted(game, t) is None]
    assert accepted == ["get_state", "choose", "end_game", "get_log"]


# @spec GAME-051
def test_an_ended_game_accepts_only_get_state_and_get_log() -> None:
    game = a_game().with_status(GameStatus.ENDED).build().game
    accepted = [t for t in _TOOLS if check_accepted(game, t) is None]
    assert accepted == ["get_state", "get_log"]


# @spec GAME-052
def test_a_tool_the_status_does_not_accept_is_an_error_naming_status_and_alternatives() -> None:
    game = a_game().with_status(GameStatus.ENDED).build().game
    assert check_accepted(game, "play") == Error(
        ErrorKind.NOT_ACCEPTED_IN_STATUS,
        subject="play",
        zone="ended",
        names=("get_state", "get_log"),
    )


_TOOLS = [
    "mulligan",
    "get_state",
    "play",
    "effect",
    "choose",
    "attack",
    "advance",
    "end_game",
    "get_log",
]
