"""Seats inside the game: what each seat holds, who owns and controls a card, whose turn it is."""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable
from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.events import NoticeKind
from mtg_goldfishing.domain.game import calls, seats
from mtg_goldfishing.domain.game.creation import new_game
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.shuffling import shuffled
from mtg_goldfishing.domain.mana import ManaPool
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import a_deck, a_game

not_built = pytest.mark.xfail(strict=True, reason="M2: seats inside the game are not built")

FORTY_CARDS = ("Forest",) * 20 + ("Island",) * 10 + ("Cultivate", "Ponder") * 5
GOBLIN = {"name": "Goblin", "types": "Creature — Goblin", "pt": "1/1"}
ATRAXA = "Atraxa, Praetors' Voice"

# The seat model is reached untyped here, so the tests read the same before and after it exists.
SeatNumber: Any = seats.SeatNumber
SeatId: Any = seats.SeatId
accept_change: Any = calls.accept_change
resend_of: Any = calls.resend_of
OPERATIONS: dict[str, Any] = {
    "mulligan": mulligan,
    "play": play,
    "effect": effect,
    "choose": choose,
    "attack": attack,
    "advance": advance,
    "end_game": end_game,
}


def the_tested_seat() -> Any:
    return SeatNumber(1)


def the_opposing_seat() -> Any:
    return SeatNumber(2)


def started(seed: int = 11) -> Any:
    result = new_game(a_deck(*FORTY_CARDS), deck_id="dtest", game_id="gabcdefghij", seed=seed)
    assert isinstance(result, Applied)
    return result.game


def applied(situation: Any, tool: str, seat: Any, **arguments: object) -> Applied:
    """Apply an operation as a seat and keep the changed game."""
    result = OPERATIONS[tool](situation.game, situation.deck, seat, **arguments)
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def recorded(situation: Any, seat: Any, delta: object) -> Applied:
    return applied(situation, "effect", seat, source="test", delta=delta)


def a_game_of_two_seats() -> Any:
    builder: Any = (
        a_game()
        .with_hand("Forest", "Sol Ring")
        .with_battlefield("Forest", "Grizzly Bears")
        .with_library("Island", "Plains", "Swamp")
    )
    return (
        builder.and_an_opposing_seat()
        .with_hand("Island", "Llanowar Elves")
        .with_battlefield("Island", "Llanowar Elves")
        .with_library("Forest", "Cultivate", "Ponder", "Sol Ring")
        .build()
    )


def a_mulligan_of_two_seats() -> Any:
    builder: Any = a_game().in_mulligan().with_hand("Forest").with_library(*("Island",) * 8)
    return (
        builder.and_an_opposing_seat().with_hand("Sol Ring").with_library(*("Forest",) * 8).build()
    )


def names(cards: Any) -> list[str]:
    return [card.name for card in cards]


# ------------------------------------------------------------------ naming a seat


# @spec APP-032
@not_built
@pytest.mark.parametrize("number", [0, -1, True, "1", 1.5])
def test_a_seat_number_is_a_whole_number_from_one(number: object) -> None:
    with pytest.raises(ValueError, match="seat number"):
        SeatNumber(number)


# @spec APP-032
@not_built
def test_seat_numbers_compare_by_value_and_never_change() -> None:
    assert SeatNumber(2) == SeatNumber(2)
    assert SeatNumber(2) != SeatNumber(3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        SeatNumber(2).value = 3


# @spec APP-032
@not_built
@pytest.mark.parametrize("text", ["", "   ", "g abc", 7])
def test_a_seat_id_is_text_without_spaces(text: object) -> None:
    with pytest.raises(ValueError, match="seat id"):
        SeatId(text)


# @spec APP-032
@not_built
def test_seat_ids_compare_by_value_and_never_change() -> None:
    assert SeatId("gabcdefghij") == SeatId("gabcdefghij")
    assert SeatId("gabcdefghij") != SeatId("gklmnopqrst")
    with pytest.raises(dataclasses.FrozenInstanceError):
        SeatId("gabcdefghij").value = "g"


# ------------------------------------------------------------------ the seats of a game


# @spec GAME-055
@not_built
def test_a_game_started_without_opponents_has_one_seat_the_tested_seat_numbered_one() -> None:
    game = started()
    assert [(seat.number, seat.tested) for seat in game.seats] == [(the_tested_seat(), True)]


# @spec GAME-055
@not_built
def test_a_goldfish_game_keeps_tallies_against_three_imaginary_opponents() -> None:
    game = started()
    assert game.imaginary is not None
    assert (game.imaginary.damage_dealt, game.imaginary.commander_damage) == (0, {"c1": [0, 0, 0]})


# @spec GAME-076
@not_built
def test_the_tested_seat_s_seat_id_is_the_game_id() -> None:
    assert started().tested.seat_id == SeatId("gabcdefghij")


# @spec APP-030
@not_built
def test_a_seat_is_reached_through_its_game_by_its_seat_number() -> None:
    game = a_game_of_two_seats().game
    assert game.seat(the_opposing_seat()) is game.seats[1]
    assert game.seat(the_opposing_seat()).number == the_opposing_seat()


# @spec GAME-061
@not_built
def test_a_seat_s_hand_library_and_battlefield_hold_only_its_own_cards() -> None:
    game = a_game_of_two_seats().game
    assert names(game.hand_of(the_opposing_seat())) == ["Island", "Llanowar Elves"]
    assert names(game.in_zone(Zone.LIBRARY, the_tested_seat())) == ["Island", "Plains", "Swamp"]
    assert names(game.battlefield_of(the_tested_seat())) == ["Forest", "Grizzly Bears"]


# @spec GAME-061
@not_built
def test_a_life_change_reaches_only_the_acting_seat() -> None:
    situation = a_game_of_two_seats()
    recorded(situation, the_opposing_seat(), {"life": -3})
    assert [seat.life for seat in situation.game.seats] == [40, 37]


# @spec GAME-061
@not_built
def test_a_land_played_uses_only_the_acting_seat_s_land_drop() -> None:
    situation = a_game_of_two_seats()
    applied(situation, "play", the_opposing_seat(), card="Island")
    assert [seat.land_drops_used for seat in situation.game.seats] == [0, 1]


# @spec GAME-061
@not_built
def test_a_commander_cast_counts_only_for_the_seat_that_cast_it() -> None:
    builder: Any = a_game().with_commander(ATRAXA)
    situation = builder.and_an_opposing_seat().with_commander(ATRAXA).build()
    applied(situation, "play", the_opposing_seat(), card=ATRAXA, override="testing")
    assert [seat.commander_casts for seat in situation.game.seats] == [{"c1": 0}, {"c2": 1}]


# @spec GAME-061, GAME-103
@not_built
def test_a_mulligan_changes_only_the_seat_that_took_it() -> None:
    situation = a_mulligan_of_two_seats()
    before = situation.game.copy()
    applied(situation, "mulligan", the_opposing_seat(), keep=False)
    game = situation.game
    assert game.seat(the_tested_seat()) == before.seat(the_tested_seat())
    assert game.hand_of(the_tested_seat()) == before.hand_of(the_tested_seat())
    assert game.seat(the_opposing_seat()).mulligans == 1


# @spec GAME-105
@not_built
def test_a_game_stays_in_mulligans_until_every_seat_has_kept() -> None:
    situation = a_mulligan_of_two_seats()
    applied(situation, "mulligan", the_opposing_seat(), keep=True)
    game = situation.game
    assert (game.status.value, game.step, game.active) == ("mulligan", None, None)
    assert [seat.kept for seat in game.seats] == [False, True]


# ------------------------------------------------------------------ each seat's mana pool


# @spec PAY-044
@not_built
def test_mana_a_seat_makes_goes_to_its_own_pool() -> None:
    situation = a_game_of_two_seats()
    recorded(situation, the_opposing_seat(), {"mana": "{G}{G}"})
    assert [str(seat.mana_pool) for seat in situation.game.seats] == [str(ManaPool()), "{G}{G}"]


# @spec PAY-044
@not_built
def test_a_seat_cannot_pay_with_another_seat_s_pool() -> None:
    builder: Any = a_game().with_hand("Llanowar Elves")
    situation = builder.and_an_opposing_seat().with_pool("{G}").build()
    result = play(situation.game, situation.deck, the_tested_seat(), card="Llanowar Elves")
    assert isinstance(result, Refusal), result
    assert [check.kind.value for check in result.checks] == ["cost_not_payable"]


# @spec PAY-044
@not_built
def test_a_seat_pays_from_its_own_pool() -> None:
    builder: Any = a_game().with_pool("{G}")
    situation = builder.and_an_opposing_seat().with_hand("Llanowar Elves").with_pool("{G}").build()
    applied(situation, "play", the_opposing_seat(), card="Llanowar Elves")
    assert [str(seat.mana_pool) for seat in situation.game.seats] == ["{G}", str(ManaPool())]


# ------------------------------------------------------------------ owner and controller


# @spec GAME-100
@not_built
def test_every_card_of_a_new_goldfish_game_is_owned_and_controlled_by_the_tested_seat() -> None:
    game = started()
    assert {(card.owner, card.controller) for card in game.cards} == {
        (the_tested_seat(), the_tested_seat())
    }


# @spec GAME-100
@not_built
def test_a_card_s_controller_is_recorded_apart_from_its_owner() -> None:
    situation = a_game_of_two_seats()
    bears = situation.named("Grizzly Bears")
    bears.controller = the_opposing_seat()
    game = situation.game
    assert bears.owner == the_tested_seat()
    assert "Grizzly Bears" in names(game.battlefield_of(the_opposing_seat()))
    assert "Grizzly Bears" not in names(game.battlefield_of(the_tested_seat()))


# @spec GAME-101
@not_built
def test_a_permanent_that_leaves_the_battlefield_returns_to_its_owner_s_control() -> None:
    situation = a_game_of_two_seats()
    situation.named("Grizzly Bears").controller = the_opposing_seat()
    recorded(situation, the_opposing_seat(), {"move": {"graveyard": ["Grizzly Bears"]}})
    bears = situation.named("Grizzly Bears")
    assert (bears.zone, bears.owner, bears.controller) == (
        Zone.GRAVEYARD,
        the_tested_seat(),
        the_tested_seat(),
    )
    assert names(situation.game.in_zone(Zone.GRAVEYARD, the_tested_seat())) == ["Grizzly Bears"]


# @spec PLAY-086
@not_built
def test_a_token_is_owned_and_controlled_by_the_seat_whose_delta_creates_it() -> None:
    situation = a_game_of_two_seats()
    recorded(situation, the_opposing_seat(), {"tokens": [GOBLIN]})
    goblin = situation.named("Goblin")
    assert (goblin.owner, goblin.controller) == (the_opposing_seat(), the_opposing_seat())


# ------------------------------------------------------------------ instance ids


# @spec GAME-064
@not_built
def test_a_token_takes_the_number_after_the_highest_issued_across_every_seat() -> None:
    situation = a_game_of_two_seats()
    highest = max(card.number for card in situation.game.cards)
    recorded(situation, the_tested_seat(), {"tokens": [GOBLIN]})
    assert situation.named("Goblin").id == f"c{highest + 1}"


# @spec GAME-064
@not_built
def test_the_number_of_a_card_that_has_left_the_game_is_never_used_again() -> None:
    situation: Any = a_game().with_battlefield("Forest").build()
    recorded(situation, the_tested_seat(), {"tokens": [GOBLIN]})
    first = situation.named("Goblin").id
    recorded(situation, the_tested_seat(), {"move": {"graveyard": ["Goblin"]}})
    recorded(situation, the_tested_seat(), {"tokens": [GOBLIN]})
    assert (first, situation.named("Goblin").id) == ("c2", "c3")


# ------------------------------------------------------------------ each seat's shuffles


# @spec GAME-084
@not_built
def test_a_library_is_in_ascending_instance_order_before_its_first_shuffle() -> None:
    game = started(seed=5)
    dealt = shuffled([f"c{n}" for n in range(2, 42)], 5, 0)
    assert {card.id for card in game.hand_of(the_tested_seat())} == set(dealt[:7])
    assert game.tested.library == dealt[7:]


# @spec GAME-083
@not_built
def test_an_opposing_seat_s_shuffle_is_seeded_with_its_shuffle_key() -> None:
    situation = a_game_of_two_seats()
    before = list(situation.game.seat(the_opposing_seat()).library)
    recorded(situation, the_opposing_seat(), {"search": {"filter": "dragon"}})
    seat = situation.game.seat(the_opposing_seat())
    keyed: Any = shuffled
    assert seat.shuffle_key == "o1"
    assert seat.library == keyed(before, situation.game.seed, 0, "o1")
    assert seat.library != shuffled(before, situation.game.seed, 0)


# @spec GAME-085
@not_built
def test_one_seat_s_shuffle_leaves_another_seat_s_library_and_shuffle_count_alone() -> None:
    situation = a_game_of_two_seats()
    before = list(situation.game.seat(the_tested_seat()).library)
    recorded(situation, the_opposing_seat(), {"search": {"filter": "dragon"}})
    seat = situation.game.seat(the_tested_seat())
    assert (seat.library, seat.shuffles) == (before, 0)
    assert situation.game.seat(the_opposing_seat()).shuffles == 1


# @spec GAME-151
@not_built
def test_a_mulligan_bottoms_the_hand_in_ascending_instance_order_before_shuffling() -> None:
    game = started(seed=5)
    hand = [card.id for card in game.hand_of(the_tested_seat())]
    expected = shuffled([*game.tested.library, *hand], 5, game.tested.shuffles)
    result = mulligan(game, a_deck(*FORTY_CARDS), the_tested_seat(), keep=False)
    assert isinstance(result, Applied), result
    assert result.game.tested.library == expected[7:]
    assert {card.id for card in result.game.hand_of(the_tested_seat())} == set(expected[:7])


# ------------------------------------------------------------------ the active seat and rounds


# @spec TURN-032
@not_built
def test_a_goldfish_game_has_no_active_seat_during_mulligans() -> None:
    assert started().active is None


# @spec TURN-032
@not_built
def test_the_tested_seat_is_the_active_seat_of_every_turn_of_a_goldfish_game() -> None:
    situation: Any = a_game().in_mulligan().with_hand("Forest").with_library(*("Island",) * 4)
    situation = situation.build()
    applied(situation, "mulligan", the_tested_seat(), keep=True)
    first = situation.game.active
    applied(situation, "advance", the_tested_seat(), to="upkeep")
    assert (first, situation.game.active, situation.game.turn) == (
        the_tested_seat(),
        the_tested_seat(),
        2,
    )


# @spec TURN-034
@not_built
def test_the_round_of_a_goldfish_game_is_its_turn() -> None:
    situation: Any = a_game().in_step(Step.CLEANUP, turn=4).with_library("Forest").build()
    applied(situation, "advance", the_tested_seat(), to="main1")
    game = situation.game
    assert (game.turn, game.round, game.tested.turns) == (5, 5, 5)


# ------------------------------------------------------------------ the tested seat stays in


# @spec GAME-140
@not_built
def test_a_goldfish_seat_at_zero_life_gets_the_life_notice_and_is_not_eliminated() -> None:
    situation: Any = a_game().with_life(2).build()
    recorded(situation, the_tested_seat(), {"life": -5})
    assert situation.game.tested.eliminated is False
    assert situation.game.notices == [NoticeKind.LIFE]


# ------------------------------------------------------------------ each seat's most recent change


# @spec GAME-033
@not_built
def test_an_accepted_change_is_remembered_as_the_calling_seat_s_own() -> None:
    situation = a_game_of_two_seats()
    result = recorded(situation, the_opposing_seat(), {"life": -1})
    game = accept_change(result, the_opposing_seat(), "effect", {"source": "test", "after": 0}).game
    last = game.seat(the_opposing_seat()).last_change
    assert game.seat(the_tested_seat()).last_change is None
    assert (game.change, last.tool, last.arguments, last.change) == (
        1,
        "effect",
        {"source": "test"},
        1,
    )


# @spec GAME-036
@not_built
def test_a_seat_s_resend_is_judged_against_its_own_most_recent_change() -> None:
    situation = a_game_of_two_seats()
    result = recorded(situation, the_opposing_seat(), {"life": -1})
    game = accept_change(result, the_opposing_seat(), "effect", {"source": "test"}).game
    assert resend_of(game, the_opposing_seat(), "effect", {"source": "test"}, 0) is not None
    assert resend_of(game, the_tested_seat(), "effect", {"source": "test"}, 0) is None


# ------------------------------------------------------------------ records


# @spec REC-070
@not_built
def test_ending_a_game_during_mulligans_writes_no_snapshot() -> None:
    situation: Any = a_game().in_mulligan().with_hand("Forest").build()
    result = applied(situation, "end_game", the_tested_seat(), result="stalled")
    assert result.snapshots == ()


# ------------------------------------------------------------------ operations are made by a seat


# @spec APP-031
@not_built
@pytest.mark.parametrize("operation", list(OPERATIONS.values()), ids=list(OPERATIONS))
def test_every_operation_a_tool_causes_takes_the_acting_seat(
    operation: Callable[..., object],
) -> None:
    parameters = inspect.signature(operation).parameters
    assert list(parameters)[:3] == ["game", "deck", "seat"]
    assert parameters["seat"].annotation in (seats.SeatNumber, "SeatNumber")
