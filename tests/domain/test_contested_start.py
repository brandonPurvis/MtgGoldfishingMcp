"""Starting a contested game: its seats, their decks and starting life, turn order and shuffles,
and the mulligans every seat takes before turn 1 begins."""

from __future__ import annotations

import hashlib
import random
from typing import Any

import pytest

from mtg_goldfishing.domain.deck.model import DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.game import creation
from mtg_goldfishing.domain.game.model import Game, GameStatus, Zone
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.game.shuffling import shuffled
from mtg_goldfishing.domain.steps import Step
from tests.support.library import LIBRARY

ATRAXA = "Atraxa, Praetors' Voice"
KENRITH = "Kenrith, the Returned King"
GAME_ID = "gabcdefghij"
SEAT_IDS = ("gseatnumber1", "gseatnumber2", "gseatnumber3")

# What new_game is asked for, reached untyped so these tests read the same before and after.
OpposingDeck: Any = creation.OpposingDeck


def a_deck(deck_id: str, commander: str, *names: str) -> LoadedDeck:
    """A loaded deck of library cards; a name given several times is that many copies."""
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return LoadedDeck(
        deck_id=deck_id,
        commanders=(commander,),
        entries=tuple(DeckEntry(n, c) for n, c in sorted(counts.items())),
        cards=tuple(DeckCard(*LIBRARY[n]) for n in sorted({*names, commander})),
    )


TESTED_DECK = a_deck("dtested", ATRAXA, *("Forest",) * 20, *("Island",) * 10, *("Ponder",) * 10)
OPPOSING_DECK = a_deck("dopposing", KENRITH, *("Forest",) * 25, *("Llanowar Elves",) * 15)


def opposing(*decks: LoadedDeck | None, ids: tuple[str, ...] = SEAT_IDS) -> list[Any]:
    return [
        OpposingDeck(deck.deck_id if deck else "dnosuchdeck", deck, seat_id)
        for deck, seat_id in zip(decks, ids, strict=False)
    ]


def created(*decks: LoadedDeck | None, seed: int = 11, **arguments: object) -> Any:
    return creation.new_game(
        TESTED_DECK,
        deck_id=TESTED_DECK.deck_id,
        game_id=GAME_ID,
        seed=seed,
        opposing=opposing(*decks),
        **arguments,
    )


def a_contested_game(*decks: LoadedDeck, seed: int = 11, **arguments: object) -> Game:
    result = created(*decks, seed=seed, **arguments)
    assert isinstance(result, Applied), result
    return result.game


def a_goldfish_game(seed: int = 11, **arguments: object) -> Game:
    result = creation.new_game(
        TESTED_DECK, deck_id=TESTED_DECK.deck_id, game_id=GAME_ID, seed=seed, **arguments
    )
    assert isinstance(result, Applied), result
    return result.game


def refused_kinds(result: object) -> list[str]:
    assert isinstance(result, Refusal), result
    return [error.kind.value for error in result.errors]


def the_seat_of(game: Game, deck_id: str) -> Any:
    return next(seat for seat in game.seats if seat.deck_id == deck_id)


def drawn_order(items: list[str], text: str) -> list[str]:
    """The Fisher–Yates walk of the design, seeded from the SHA-256 of `text`."""
    generator = random.Random(int(hashlib.sha256(text.encode()).hexdigest(), 16))
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        j = int(generator.random() * (i + 1))
        result[i], result[j] = result[j], result[i]
    return result


def keys_in_turn_order(game: Game) -> list[str]:
    """Each seat in turn order, by its shuffle key: "" for the tested seat, "o1"... otherwise."""
    return [seat.shuffle_key for seat in game.seats]


# ------------------------------------------------------------------ the seats of a new game


# @spec GAME-055
def test_a_game_asked_for_with_an_empty_list_of_opponents_is_a_goldfish_game() -> None:
    result = creation.new_game(
        TESTED_DECK, deck_id="dtested", game_id=GAME_ID, seed=11, opposing=[]
    )
    assert isinstance(result, Applied), result
    game = result.game
    assert [(seat.number, seat.tested) for seat in game.seats] == [(SeatNumber(1), True)]
    assert game.imaginary is not None


# @spec GAME-056
@pytest.mark.parametrize("count", [1, 2, 3])
def test_a_game_with_opponents_has_one_opposing_seat_for_each(count: int) -> None:
    game = a_contested_game(*[OPPOSING_DECK] * count)
    assert len(game.seats) == count + 1
    assert [seat.tested for seat in game.seats].count(True) == 1
    assert sorted(seat.shuffle_key for seat in game.seats if not seat.tested) == [
        f"o{k}" for k in range(1, count + 1)
    ]


# @spec GAME-056
def test_a_contested_game_has_no_imaginary_opponents() -> None:
    assert a_contested_game(OPPOSING_DECK).imaginary is None


# @spec GAME-056
def test_the_tested_seat_plays_the_deck_id_and_each_opposing_seat_its_opponent_deck() -> None:
    game = a_contested_game(OPPOSING_DECK)
    assert game.tested.deck_id == "dtested"
    assert [seat.deck_id for seat in game.seats if not seat.tested] == ["dopposing"]


# @spec GAME-057
def test_an_opposing_seat_may_play_the_tested_seat_s_own_deck() -> None:
    game = a_contested_game(TESTED_DECK)
    assert [seat.deck_id for seat in game.seats] == ["dtested", "dtested"]


# @spec GAME-057
def test_several_opposing_seats_may_play_the_same_deck() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK)
    assert sorted(seat.deck_id for seat in game.seats) == ["dopposing", "dopposing", "dtested"]


# @spec GAME-058
def test_more_than_three_opponents_is_an_error() -> None:
    four = [OpposingDeck("dopposing", OPPOSING_DECK, f"gseat{n:07d}") for n in range(4)]
    result = creation.new_game(
        TESTED_DECK, deck_id="dtested", game_id=GAME_ID, seed=11, opposing=four
    )
    assert refused_kinds(result) == ["too_many_opponents"]


# @spec GAME-059
def test_an_opponent_that_names_no_loaded_deck_is_an_error() -> None:
    result = created(OPPOSING_DECK, None)
    assert refused_kinds(result) == ["unknown_deck"]
    assert isinstance(result, Refusal)
    assert result.errors[0].subject == "dnosuchdeck"


# @spec GAME-060
def test_a_new_contested_game_waits_for_mulligans_with_no_turn_round_step_or_active_seat() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK)
    assert (game.status, game.turn, game.round, game.step, game.active) == (
        GameStatus.MULLIGAN,
        0,
        0,
        None,
        None,
    )


# @spec GAME-060
def test_each_seat_holds_its_own_commander_in_its_command_zone_and_its_deck_in_its_library() -> (
    None
):
    game = a_contested_game(OPPOSING_DECK)
    tested, other = game.tested, the_seat_of(game, "dopposing")
    assert [c.name for c in game.in_zone(Zone.COMMAND, tested.number)] == [ATRAXA]
    assert [c.name for c in game.in_zone(Zone.COMMAND, other.number)] == [KENRITH]
    assert len(other.library) + len(game.hand_of(other.number)) == 40
    assert {game.instance(i).owner for i in other.library} == {other.number}


# @spec GAME-062
def test_instance_ids_go_seat_by_seat_tested_seat_first_then_opponents_in_their_order() -> None:
    game = a_contested_game(OPPOSING_DECK, TESTED_DECK)
    by_key = {seat.shuffle_key: seat.number for seat in game.seats}

    def ids_of(key: str) -> list[int]:
        return sorted(card.number for card in game.cards if card.owner == by_key[key])

    assert ids_of("") == list(range(1, 42))
    assert ids_of("o1") == list(range(42, 83))
    assert ids_of("o2") == list(range(83, 124))
    assert game.instance("c42").name == KENRITH
    assert game.instance("c43").name == "Forest"


# @spec GAME-063
def test_the_tested_seat_s_cards_have_the_same_ids_as_in_a_goldfish_game() -> None:
    goldfish, contested = a_goldfish_game(), a_contested_game(OPPOSING_DECK)
    tested = contested.tested.number
    assert sorted((c.id, c.name) for c in goldfish.cards) == sorted(
        (c.id, c.name) for c in contested.cards if c.owner == tested
    )


# @spec GAME-065
def test_every_seat_is_dealt_seven_cards_from_its_own_shuffled_library() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK)
    for seat in game.seats:
        hand = game.hand_of(seat.number)
        assert len(hand) == 7
        assert {card.owner for card in hand} == {seat.number}
        assert seat.shuffles == 1


# @spec GAME-083
def test_an_opposing_seat_s_library_is_shuffled_on_its_own_keyed_stream() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK, seed=21)
    for key, first in (("o1", 42), ("o2", 83)):
        seat = next(s for s in game.seats if s.shuffle_key == key)
        dealt = shuffled([f"c{n}" for n in range(first + 1, first + 41)], 21, 0, key)
        assert {card.id for card in game.hand_of(seat.number)} == set(dealt[:7])
        assert seat.library == dealt[7:]


# @spec GAME-086
def test_the_tested_seat_s_hand_and_library_are_the_same_as_in_a_goldfish_game() -> None:
    goldfish = a_goldfish_game(seed=5)
    contested = a_contested_game(OPPOSING_DECK, OPPOSING_DECK, OPPOSING_DECK, seed=5)
    assert [c.id for c in contested.hand_of(contested.tested.number)] == [
        c.id for c in goldfish.hand_of(goldfish.tested.number)
    ]
    assert contested.tested.library == goldfish.tested.library


# ------------------------------------------------------------------ starting life


# @spec GAME-066
def test_a_single_starting_life_is_every_seat_s_life() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK, starting_life=30)
    assert [seat.life for seat in game.seats] == [30, 30, 30]


# @spec GAME-066
def test_a_single_starting_life_is_the_goldfish_seat_s_life() -> None:
    assert a_goldfish_game(starting_life=20).tested.life == 20


# @spec GAME-067
def test_a_list_of_starting_lives_goes_tested_seat_first_then_opponents_in_order() -> None:
    game = a_contested_game(OPPOSING_DECK, TESTED_DECK, starting_life=[40, 30, 20])
    life_by_key = {seat.shuffle_key: seat.life for seat in game.seats}
    assert life_by_key == {"": 40, "o1": 30, "o2": 20}


# @spec GAME-068
def test_every_seat_starts_at_forty_life_when_none_is_given() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK)
    assert [seat.life for seat in game.seats] == [40, 40, 40]


# @spec GAME-069
@pytest.mark.parametrize("lives", [[40], [40, 30, 20]])
def test_a_list_of_starting_lives_must_have_one_per_seat(lives: list[int]) -> None:
    assert refused_kinds(created(OPPOSING_DECK, starting_life=lives)) == ["bad_starting_life"]


# @spec GAME-070
@pytest.mark.parametrize("life", [0, -5, [40, 0]])
def test_a_starting_life_below_one_is_an_error(life: object) -> None:
    assert refused_kinds(created(OPPOSING_DECK, starting_life=life)) == ["bad_starting_life"]


# @spec GAME-071
def test_a_list_of_starting_lives_for_a_goldfish_game_is_an_error() -> None:
    result = creation.new_game(
        TESTED_DECK, deck_id="dtested", game_id=GAME_ID, seed=11, starting_life=[40]
    )
    assert refused_kinds(result) == ["bad_starting_life"]


# ------------------------------------------------------------------ turn order


# @spec GAME-072
def test_a_position_for_a_goldfish_game_is_an_error() -> None:
    result = creation.new_game(TESTED_DECK, deck_id="dtested", game_id=GAME_ID, seed=11, position=1)
    assert refused_kinds(result) == ["bad_position"]


# @spec GAME-073
@pytest.mark.parametrize("position", [0, 3, -1])
def test_a_position_outside_the_seats_is_an_error(position: int) -> None:
    assert refused_kinds(created(OPPOSING_DECK, position=position)) == ["bad_position"]


# @spec GAME-079, GAME-080
@pytest.mark.parametrize("seed", [1, 2, 3, 99])
def test_turn_order_is_drawn_from_the_seed_and_numbers_the_seats_from_one(seed: int) -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK, OPPOSING_DECK, seed=seed)
    assert keys_in_turn_order(game) == drawn_order(["", "o1", "o2", "o3"], f"{seed}:order")
    assert [seat.number for seat in game.seats] == [SeatNumber(n) for n in (1, 2, 3, 4)]


# @spec GAME-081
@pytest.mark.parametrize("position", [1, 2, 3])
def test_a_position_places_the_tested_seat_and_the_seed_orders_the_others(position: int) -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK, seed=4, position=position)
    others = drawn_order(["o1", "o2"], "4:order")
    assert keys_in_turn_order(game) == [*others[: position - 1], "", *others[position - 1 :]]
    assert game.tested.number == SeatNumber(position)


# @spec GAME-082
def test_the_same_decks_position_and_seed_give_the_same_turn_order_and_opening_hands() -> None:
    first = a_contested_game(OPPOSING_DECK, TESTED_DECK, seed=8, position=2)
    second = a_contested_game(OPPOSING_DECK, TESTED_DECK, seed=8, position=2)
    assert keys_in_turn_order(first) == keys_in_turn_order(second)
    for seat in first.seats:
        assert [c.id for c in first.hand_of(seat.number)] == [
            c.id for c in second.hand_of(seat.number)
        ]


# ------------------------------------------------------------------ the outcome of new_game


# @spec GAME-074
def test_the_outcome_lists_each_seat_in_turn_order_with_its_id_deck_life_and_testedness() -> None:
    result = created(OPPOSING_DECK, seed=3, starting_life=[40, 25])
    assert isinstance(result, Applied), result
    summary: Any = result.summary
    listed = [
        (seat.number, seat.seat_id, seat.deck_id, seat.life, seat.tested) for seat in summary.seats
    ]
    game = result.game
    assert listed == [
        (seat.number, seat.seat_id.value, seat.deck_id, seat.life, seat.tested)
        for seat in game.seats
    ]
    assert summary.seed == 3


# @spec GAME-075
def test_the_outcome_of_a_new_contested_game_shows_no_seat_s_hand() -> None:
    result = created(OPPOSING_DECK)
    assert isinstance(result, Applied), result
    hands = {c.name for c in result.game.cards if c.zone is Zone.HAND}
    shown = repr((result.summary, result.events))
    assert not any(f"'{name}'" in shown for name in hands)


# @spec GAME-077
def test_each_opposing_seat_has_the_seat_id_it_was_given_and_the_tested_seat_the_game_id() -> None:
    game = a_contested_game(OPPOSING_DECK, OPPOSING_DECK)
    ids = {seat.shuffle_key: seat.seat_id.value for seat in game.seats}
    assert ids == {"": GAME_ID, "o1": SEAT_IDS[0], "o2": SEAT_IDS[1]}


# ------------------------------------------------------------------ the same game every time


def _mulligan_everyone(game: Game, decks: dict[str, LoadedDeck]) -> Game:
    """Every seat takes two mulligans, then keeps with one card bottomed, in turn order."""
    for seat in list(game.seats):
        deck = decks[seat.deck_id]
        for _ in range(2):
            result = mulligan(game, deck, seat.number, keep=False)
            assert isinstance(result, Applied), result
            game = result.game
    for seat in list(game.seats):
        deck = decks[seat.deck_id]
        bottom = [game.hand_of(seat.number)[0].id]
        result = mulligan(game, deck, seat.number, keep=True, bottom=bottom)
        assert isinstance(result, Applied), result
        game = result.game
    return game


# @spec GAME-087
def test_the_same_decks_and_seed_with_the_same_calls_give_the_same_game() -> None:
    decks = {"dtested": TESTED_DECK, "dopposing": OPPOSING_DECK}
    first = _mulligan_everyone(a_contested_game(OPPOSING_DECK, seed=6), decks)
    second = _mulligan_everyone(a_contested_game(OPPOSING_DECK, seed=6), decks)
    assert first == second


# ------------------------------------------------------------------ mulligans


def a_mulligan_of_two_seats(seed: int = 11) -> Game:
    return a_contested_game(OPPOSING_DECK, seed=seed, position=1)


def deck_of(game: Game, seat: SeatNumber) -> LoadedDeck:
    return TESTED_DECK if game.seat(seat).tested else OPPOSING_DECK


def keep(game: Game, seat: SeatNumber) -> Applied:
    result = mulligan(game, deck_of(game, seat), seat, keep=True)
    assert isinstance(result, Applied), result
    return result


# @spec GAME-102
def test_seats_take_their_mulligans_in_any_order() -> None:
    game = a_mulligan_of_two_seats()
    second = mulligan(game, OPPOSING_DECK, SeatNumber(2), keep=False)
    assert isinstance(second, Applied), second
    first = mulligan(second.game, TESTED_DECK, SeatNumber(1), keep=False)
    assert isinstance(first, Applied), first
    assert [seat.mulligans for seat in first.game.seats] == [1, 1]


# @spec GAME-106
def test_when_the_last_seat_keeps_the_first_seat_in_turn_order_takes_turn_one() -> None:
    game = keep(a_mulligan_of_two_seats(), SeatNumber(1)).game
    started = keep(game, SeatNumber(2)).game
    assert (started.status, started.active, started.step) == (
        GameStatus.ACTIVE,
        SeatNumber(1),
        Step.MAIN1,
    )
    assert (started.turn, started.round, started.seat(SeatNumber(1)).turns) == (1, 1, 1)
    assert started.seat(SeatNumber(2)).turns == 0


# @spec GAME-106
def test_the_first_seat_draws_on_the_first_turn_when_the_last_seat_to_keep_is_another() -> None:
    game = keep(a_mulligan_of_two_seats(), SeatNumber(1)).game
    started = keep(game, SeatNumber(2)).game
    assert [len(started.hand_of(seat.number)) for seat in started.seats] == [8, 7]


# @spec GAME-106
def test_the_first_turn_skips_the_first_seat_s_draw_when_draw_first_turn_is_false() -> None:
    game = keep(a_contested_game(OPPOSING_DECK, position=1, draw_first_turn=False), SeatNumber(2))
    started = keep(game.game, SeatNumber(1)).game
    assert [len(started.hand_of(seat.number)) for seat in started.seats] == [7, 7]


# @spec GAME-107
def test_the_card_the_first_seat_drew_is_named_only_to_that_seat() -> None:
    game = keep(a_mulligan_of_two_seats(), SeatNumber(1)).game
    drawn = game.instance(game.seat(SeatNumber(1)).library[0]).name
    result = keep(game, SeatNumber(2))
    to_the_drawer = repr(as_seen_by(result.events, SeatNumber(1)))
    to_the_keeper = repr(as_seen_by(result.events, SeatNumber(2)))
    assert f"'{drawn}'" in to_the_drawer
    assert f"'{drawn}'" not in to_the_keeper
