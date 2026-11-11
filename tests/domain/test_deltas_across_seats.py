"""Deltas that reach other seats in a contested game: other seats' public cards, life and
damage per seat, changes of control, and the names a delta may and may not resolve."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.playing import effect, play
from tests.support.acting import S1, S2, S3, acted, error_kinds, errors_of, events_named
from tests.support.builders import Situation, a_game

ATRAXA = "Atraxa, Praetors' Voice"
GOBLIN = {"name": "Goblin", "types": "Creature — Goblin", "pt": "1/1"}


def two_seats(*, opposing: Any = None, tested: Any = None) -> Situation:
    """Seat 1's turn, in its first main step of table turn 3; each seat as the functions given
    describe it."""
    builder: Any = (tested or (lambda b: b))(a_game())
    builder = builder.and_an_opposing_seat()
    builder = (opposing or (lambda b: b))(builder)
    return builder.build()


def three_seats(*, first: Any = None, second: Any = None, third: Any = None) -> Situation:
    builder: Any = (first or (lambda b: b))(a_game())
    builder = (second or (lambda b: b))(builder.and_an_opposing_seat())
    builder = (third or (lambda b: b))(builder.and_an_opposing_seat())
    return builder.build()


def recorded(situation: Situation, delta: object, seat: SeatNumber = S1) -> Any:
    return effect(situation.game, situation.deck, seat, source="a test effect", delta=delta)


def card_of(situation: Situation, name: str, owner: SeatNumber) -> Any:
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


def id_of(situation: Situation, name: str, owner: SeatNumber) -> str:
    return str(card_of(situation, name, owner).id)


# ------------------------------------------------------------------ keys only a contested game has


# @spec PLAY-074
@pytest.mark.parametrize(
    "delta",
    [
        {"control": {"1": ["Grizzly Bears"]}},
        {"ask": [{"seats": "opponents", "text": "discard a card"}]},
        {"look_at_hand": 2},
        {"life": {"1": 2}},
        {"damage": {"1": 2}},
    ],
    ids=["control", "ask", "look_at_hand", "life map", "damage map"],
)
def test_a_goldfish_delta_may_not_use_a_key_only_a_contested_game_has(delta: object) -> None:
    situation = a_game().with_battlefield("Grizzly Bears").build()
    assert error_kinds(recorded(situation, delta)) == ["contested_only"]


# @spec PLAY-075
def test_damage_in_a_contested_delta_is_a_map_from_seat_number_not_one_number() -> None:
    assert error_kinds(recorded(two_seats(), {"damage": 3})) == ["damage_needs_seats"]


# @spec PLAY-126
@pytest.mark.parametrize(
    "control",
    [["Grizzly Bears"], {"two": ["Grizzly Bears"]}, {"2": 5}, {"0": ["Grizzly Bears"]}],
    ids=["a list", "a word for a seat", "a number for cards", "seat zero"],
)
def test_control_that_is_not_a_map_from_seat_number_to_cards_is_malformed(control: object) -> None:
    situation = two_seats(opposing=lambda b: b.with_battlefield("Grizzly Bears"))
    assert error_kinds(recorded(situation, {"control": control})) == ["malformed_argument"]


# @spec PLAY-127
@pytest.mark.parametrize(
    "entry",
    [
        {"text": "discard a card"},
        {"seats": [2]},
        {"seats": [2], "text": "discard a card", "count": 1},
        {"seats": "everyone", "text": "discard a card"},
        {"seats": 2, "text": "discard a card"},
    ],
    ids=["no seats", "no text", "another field", "a word for seats", "one number for seats"],
)
def test_an_ask_entry_without_seats_and_text_alone_is_malformed(entry: object) -> None:
    assert error_kinds(recorded(two_seats(), {"ask": [entry]})) == ["malformed_argument"]


# @spec PLAY-128
def test_look_at_hand_given_a_list_of_seats_is_malformed() -> None:
    situation = two_seats(opposing=lambda b: b.with_hand("Island"))
    assert error_kinds(recorded(situation, {"look_at_hand": [2]})) == ["malformed_argument"]


# @spec PLAY-128
def test_look_at_hand_may_not_name_the_acting_seat() -> None:
    situation = two_seats(tested=lambda b: b.with_hand("Island"))
    assert error_kinds(recorded(situation, {"look_at_hand": 1})) == ["look_at_own_hand"]


# @spec PLAY-076
@pytest.mark.parametrize(
    "reveal",
    [{"look": {"n": 1, "rest": "library_top"}}, {"search": {}}],
    ids=["look", "search"],
)
def test_look_at_hand_with_a_look_or_search_in_one_delta_is_an_error(
    reveal: dict[str, Any],
) -> None:
    situation = two_seats(
        tested=lambda b: b.with_library("Forest"), opposing=lambda b: b.with_hand("Island")
    )
    delta = {"look_at_hand": 2, **reveal}
    assert error_kinds(recorded(situation, delta)) == ["too_many_reveals"]


# @spec PLAY-077
@pytest.mark.parametrize(
    "delta",
    [
        {"control": {"5": ["Grizzly Bears"]}},
        {"life": {"5": 1}},
        {"damage": {"5": 1}},
        {"ask": [{"seats": [5], "text": "discard a card"}]},
        {"look_at_hand": 5},
    ],
    ids=["control", "life", "damage", "ask", "look_at_hand"],
)
def test_a_seat_number_not_in_the_game_is_an_error(delta: object) -> None:
    situation = two_seats(tested=lambda b: b.with_battlefield("Grizzly Bears"))
    assert error_kinds(recorded(situation, delta)) == ["no_such_seat"]


# @spec PLAY-077
@pytest.mark.parametrize(
    "delta",
    [
        {"control": {"3": ["Grizzly Bears"]}},
        {"life": {"3": 1}},
        {"damage": {"3": 1}},
        {"ask": [{"seats": [3], "text": "discard a card"}]},
        {"look_at_hand": 3},
    ],
    ids=["control", "life", "damage", "ask", "look_at_hand"],
)
def test_a_seat_number_of_an_eliminated_seat_is_an_error(delta: object) -> None:
    situation = three_seats(
        first=lambda b: b.with_battlefield("Grizzly Bears"),
        third=lambda b: b.with_hand("Island").eliminated(),
    )
    assert error_kinds(recorded(situation, delta)) == ["seat_out"]


# ------------------------------------------------------------------ other seats' hidden zones


# @spec PLAY-079, GAME-157
@pytest.mark.parametrize("key", ["move", "discard", "fetch", "tap"])
@pytest.mark.parametrize("zone", ["hand", "library"])
def test_an_instance_id_in_another_seat_s_hidden_zone_is_a_hidden_zone_error(
    key: str, zone: str
) -> None:
    situation = two_seats(
        opposing=lambda b: b.with_hand("Island") if zone == "hand" else b.with_library("Island")
    )
    island = id_of(situation, "Island", S2)
    delta: dict[str, object] = {
        "move": {"graveyard": [island]},
        "discard": [island],
        "fetch": {"hand": [island]},
        "tap": [island],
    }
    (error,) = errors_of(recorded(situation, {key: delta[key]}))
    assert (error.kind.value, error.subject, error.number) == ("hidden_zone", island, 2)
    assert error.zone is None
    assert error.through_ask


# @spec PLAY-114, GAME-156
@pytest.mark.parametrize("key", ["move", "discard", "fetch", "tap"])
def test_a_name_held_only_in_another_seat_s_hand_gets_the_error_of_a_name_held_nowhere(
    key: str,
) -> None:
    def holding(names: tuple[str, ...]) -> Situation:
        return two_seats(
            tested=lambda b: b.with_hand("Forest").with_library("Forest"),
            opposing=lambda b: b.with_hand(*names).with_library(*names),
        )

    delta: dict[str, object] = {
        "move": {"graveyard": ["Lightning Bolt"]},
        "discard": ["Lightning Bolt"],
        "fetch": {"hand": ["Lightning Bolt"]},
        "tap": ["Lightning Bolt"],
    }
    held = errors_of(recorded(holding(("Lightning Bolt",)), {key: delta[key]}))
    nowhere = errors_of(recorded(holding(("Island",)), {key: delta[key]}))
    assert held == nowhere


# @spec PLAY-115
@pytest.mark.parametrize(
    "delta",
    [
        {"move": {"graveyard": ["Lightning Bolt"]}},
        {"discard": ["Lightning Bolt"]},
        {"fetch": {"hand": ["Lightning Bolt"]}},
        {"tap": ["Lightning Bolt"]},
    ],
    ids=["move", "discard", "fetch", "tap"],
)
def test_a_delta_name_found_nowhere_in_view_adds_that_hidden_zones_are_reached_through_ask(
    delta: object,
) -> None:
    situation = two_seats(tested=lambda b: b.with_library("Forest"))
    (error,) = errors_of(recorded(situation, delta))
    assert error.through_ask


# @spec GAME-157
def test_playing_an_instance_id_from_another_seat_s_hand_is_a_hidden_zone_error() -> None:
    situation = two_seats(opposing=lambda b: b.with_hand("Lightning Bolt"))
    bolt = id_of(situation, "Lightning Bolt", S2)
    (error,) = errors_of(play(situation.game, situation.deck, S1, card=bolt))
    assert (error.kind.value, error.number, error.through_ask) == ("hidden_zone", 2, False)


# @spec GAME-096
def test_a_name_for_a_hidden_zone_is_resolved_among_the_acting_seat_s_own_cards_only() -> None:
    situation = two_seats(opposing=lambda b: b.with_hand("Lightning Bolt"))
    (error,) = errors_of(play(situation.game, situation.deck, S1, card="Lightning Bolt"))
    assert (error.kind.value, error.found_in) == ("card_not_in_zone", None)


# ------------------------------------------------------------------ names in public zones


# @spec GAME-097
def test_a_name_resolves_to_the_acting_seat_s_own_permanent_before_another_seat_s() -> None:
    situation = two_seats(
        tested=lambda b: b.with_battlefield("Forest", tapped=True),
        opposing=lambda b: b.with_battlefield("Forest"),
    )
    acted(situation, recorded(situation, {"tap": ["Forest"]}))
    assert card_of(situation, "Forest", S2).tapped is False


# @spec GAME-097
def test_a_name_no_acting_seat_card_matches_resolves_among_seats_from_the_next_one() -> None:
    builder: Any = a_game().in_turn_of(2).with_battlefield("Grizzly Bears")
    builder = builder.and_an_opposing_seat().and_an_opposing_seat()
    situation = builder.with_battlefield("Grizzly Bears").build()
    acted(situation, recorded(situation, {"tap": ["Grizzly Bears"]}, S2))
    assert card_of(situation, "Grizzly Bears", S3).tapped
    assert not card_of(situation, "Grizzly Bears", S1).tapped


# @spec GAME-098
def test_an_instance_id_names_another_seat_s_permanent() -> None:
    situation = two_seats(
        tested=lambda b: b.with_battlefield("Grizzly Bears"),
        opposing=lambda b: b.with_battlefield("Grizzly Bears"),
    )
    theirs = id_of(situation, "Grizzly Bears", S2)
    acted(situation, recorded(situation, {"tap": [theirs]}))
    assert card_of(situation, "Grizzly Bears", S2).tapped
    assert not card_of(situation, "Grizzly Bears", S1).tapped


# @spec GAME-099
def test_the_chosen_instance_is_named_when_the_matching_cards_differ_in_controller() -> None:
    situation = two_seats(
        tested=lambda b: b.with_battlefield("Grizzly Bears"),
        opposing=lambda b: b.with_battlefield("Grizzly Bears"),
    )
    result = acted(situation, recorded(situation, {"counters": {"Grizzly Bears": {"+1/+1": 1}}}))
    chosen = events_named(result, "InstanceChosen")
    assert [event.instance_id for event in chosen] == [id_of(situation, "Grizzly Bears", S1)]


# ------------------------------------------------------------------ moving other seats' cards


# @spec PLAY-087
def test_move_finds_another_seat_s_permanent_before_the_acting_seat_s_graveyard_card() -> None:
    situation = two_seats(
        tested=lambda b: b.with_graveyard("Grizzly Bears"),
        opposing=lambda b: b.with_battlefield("Grizzly Bears"),
    )
    acted(situation, recorded(situation, {"move": {"exile": ["Grizzly Bears"]}}))
    assert situation.names_in(Zone.EXILE, S2) == ["Grizzly Bears"]
    assert situation.names_in(Zone.GRAVEYARD, S1) == ["Grizzly Bears"]


# @spec PLAY-088
@pytest.mark.parametrize(
    ("destination", "zone"),
    [("graveyard", Zone.GRAVEYARD), ("hand", Zone.HAND), ("library_top", Zone.LIBRARY)],
)
def test_a_card_moved_by_another_seat_goes_to_its_owner_s_zone(
    destination: str, zone: Zone
) -> None:
    situation = two_seats(opposing=lambda b: b.with_battlefield("Grizzly Bears"))
    acted(situation, recorded(situation, {"move": {destination: ["Grizzly Bears"]}}))
    assert situation.names_in(zone, S2) == ["Grizzly Bears"]
    assert situation.names_in(zone, S1) == []


# @spec PLAY-089
def test_a_card_moved_onto_the_battlefield_enters_under_the_acting_seat_s_control() -> None:
    situation = two_seats(opposing=lambda b: b.with_graveyard("Grizzly Bears"))
    acted(situation, recorded(situation, {"move": {"battlefield": ["Grizzly Bears"]}}))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.zone, bears.controller, bears.owner) == (Zone.BATTLEFIELD, S1, S2)


# @spec PLAY-119
def test_a_permanent_moved_to_the_battlefield_from_the_battlefield_arrives_again() -> None:
    situation = two_seats(
        opposing=lambda b: b.with_battlefield(
            "Grizzly Bears", tapped=True, entered_turn=1, counters={"+1/+1": 2}
        )
    )
    acted(situation, recorded(situation, {"move": {"battlefield": ["Grizzly Bears"]}}))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.controller, bears.tapped, bears.counters) == (S1, False, {})
    assert bears.entered_turn == situation.game.turn


# @spec PLAY-095
def test_a_delta_taps_untaps_and_puts_counters_on_another_seat_s_permanents() -> None:
    situation = two_seats(
        opposing=lambda b: b.with_battlefield("Grizzly Bears").with_battlefield(
            "Llanowar Elves", tapped=True
        )
    )
    delta = {
        "tap": ["Grizzly Bears"],
        "untap": ["Llanowar Elves"],
        "counters": {"Grizzly Bears": {"-1/-1": 1}},
    }
    acted(situation, recorded(situation, delta))
    bears, elves = card_of(situation, "Grizzly Bears", S2), card_of(situation, "Llanowar Elves", S2)
    assert (bears.tapped, bears.counters, elves.tapped) == (True, {"-1/-1": 1}, False)


# @spec PLAY-095
def test_a_delta_moves_another_seat_s_card_out_of_its_graveyard() -> None:
    situation = two_seats(opposing=lambda b: b.with_graveyard("Lightning Bolt"))
    acted(situation, recorded(situation, {"move": {"exile": ["Lightning Bolt"]}}))
    assert situation.names_in(Zone.EXILE, S2) == ["Lightning Bolt"]


# ------------------------------------------------------------------ life and damage per seat


# @spec PLAY-091
def test_life_as_a_map_changes_each_named_seat_s_life() -> None:
    situation = three_seats()
    acted(situation, recorded(situation, {"life": {"1": 3, "3": -4}}))
    assert [seat.life for seat in situation.game.seats] == [43, 40, 36]


# @spec PLAY-092
def test_damage_as_a_map_is_taken_from_each_named_seat_s_life() -> None:
    situation = three_seats()
    result = acted(situation, recorded(situation, {"damage": {"2": 3, "3": 5}}))
    assert [seat.life for seat in situation.game.seats] == [40, 37, 35]
    assert [(e.seat, e.amount, e.life) for e in events_named(result, "SeatDamaged")] == [
        (S2, 3, 37),
        (S3, 5, 35),
    ]


# @spec PLAY-093
def test_a_delta_s_damage_never_counts_as_commander_damage() -> None:
    situation = two_seats(tested=lambda b: b.with_commander(ATRAXA, zone=Zone.BATTLEFIELD))
    acted(situation, recorded(situation, {"damage": {"2": 5}}))
    assert situation.game.seat(S1).commander_damage == {}


# @spec PLAY-091
def test_life_as_one_number_in_a_contested_game_is_the_acting_seat_s_own() -> None:
    situation = two_seats()
    acted(situation, recorded(situation, {"life": -2}))
    assert [seat.life for seat in situation.game.seats] == [38, 40]


# ------------------------------------------------------------------ control


# @spec PLAY-094
def test_control_makes_the_named_seat_the_controller_of_the_listed_permanents() -> None:
    situation = two_seats(opposing=lambda b: b.with_battlefield("Grizzly Bears"))
    result = acted(situation, recorded(situation, {"control": {"1": ["Grizzly Bears"]}}))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.controller, bears.owner) == (S1, S2)
    assert situation.names_in(Zone.BATTLEFIELD, S1) == ["Grizzly Bears"]
    assert [(e.card, e.seat) for e in events_named(result, "ControlChanged")] == [
        ("Grizzly Bears", S1)
    ]


# @spec PLAY-117
def test_a_permanent_that_changes_controller_counts_as_arrived_and_keeps_its_state() -> None:
    situation = two_seats(
        opposing=lambda b: b.with_battlefield(
            "Grizzly Bears", tapped=True, entered_turn=1, counters={"+1/+1": 1}
        )
    )
    acted(situation, recorded(situation, {"control": {"1": ["Grizzly Bears"]}}))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.entered_turn, bears.tapped, bears.counters) == (
        situation.game.turn,
        True,
        {"+1/+1": 1},
    )


# @spec PLAY-118
def test_control_given_to_the_seat_that_already_controls_it_changes_nothing_and_says_so() -> None:
    situation = two_seats(opposing=lambda b: b.with_battlefield("Grizzly Bears", entered_turn=1))
    result = acted(situation, recorded(situation, {"control": {"2": ["Grizzly Bears"]}}))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.controller, bears.entered_turn) == (S2, 1)
    assert [e.kind.value for e in events_named(result, "AlreadySo")] == ["already_controlled"]


# @spec PLAY-124
def test_control_naming_a_card_not_on_the_battlefield_is_an_error() -> None:
    situation = two_seats(opposing=lambda b: b.with_graveyard("Grizzly Bears"))
    result = recorded(situation, {"control": {"1": ["Grizzly Bears"]}})
    assert error_kinds(result) == ["card_not_in_zone"]


# @spec PLAY-085
def test_tokens_are_created_before_control_is_given_in_one_delta() -> None:
    situation = two_seats()
    delta = {"control": {"2": ["Goblin"]}, "tokens": [GOBLIN]}
    acted(situation, recorded(situation, delta))
    goblin = next(c for c in situation.game.cards if c.name == "Goblin")
    assert (goblin.owner, goblin.controller) == (S1, S2)


# ------------------------------------------------------------------ playing other seats' cards


# @spec PLAY-080
def test_a_seat_casts_another_seat_s_card_from_that_seat_s_graveyard() -> None:
    situation = two_seats(
        tested=lambda b: b.with_battlefield("Forest", "Forest"),
        opposing=lambda b: b.with_graveyard("Grizzly Bears"),
    )
    acted(
        situation,
        play(situation.game, situation.deck, S1, card="Grizzly Bears", from_zone="graveyard"),
    )
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.zone, bears.controller, bears.owner) == (Zone.BATTLEFIELD, S1, S2)


# @spec PLAY-129
def test_casting_another_seat_s_commander_pays_its_tax_and_raises_it_for_its_owner() -> None:
    situation = two_seats(
        opposing=lambda b: b.with_commander(ATRAXA).with_commander_casts(ATRAXA, 2)
    )
    result = acted(
        situation,
        play(
            situation.game,
            situation.deck,
            S1,
            card=ATRAXA,
            from_zone="command",
            override="paid with a test",
        ),
    )
    (paid,) = events_named(result, "CostPaid")
    atraxa = card_of(situation, ATRAXA, S2)
    face = situation.deck.card(ATRAXA)
    assert face is not None
    assert paid.cost == face.card.front.mana_cost + ManaString.parse("{4}")
    assert situation.game.seat(S2).commander_casts[atraxa.id] == 3


# @spec PLAY-007
def test_play_without_from_looks_only_in_the_acting_seat_s_own_command_zone() -> None:
    situation = two_seats(opposing=lambda b: b.with_commander(ATRAXA))
    (error,) = errors_of(play(situation.game, situation.deck, S1, card=ATRAXA))
    assert error.kind.value == "card_not_in_zone"


# ------------------------------------------------------------------ expect


# @spec PLAY-108
def test_damage_dealt_is_no_expect_key_in_a_contested_game() -> None:
    situation = two_seats()
    result = effect(
        situation.game,
        situation.deck,
        S1,
        source="x",
        delta={},
        expect={"damage_dealt": 0},
    )
    (error,) = errors_of(result)
    assert error.kind.value == "unknown_expect_key"
    assert "damage_dealt" not in error.names


# @spec PLAY-109
def test_expected_lands_count_the_lands_the_acting_seat_controls_whoever_owns_them() -> None:
    situation = two_seats(
        tested=lambda b: b.with_battlefield("Forest"),
        opposing=lambda b: b.with_battlefield("Island").controlled_by("Island", 1),
    )
    result = acted(
        situation,
        effect(situation.game, situation.deck, S1, source="x", delta={}, expect={"lands": 2}),
    )
    assert events_named(result, "ExpectationMismatched") == []


# ------------------------------------------------------------------ immediate


# @spec PLAY-084
@pytest.mark.parametrize("immediate", [True, False])
def test_immediate_changes_nothing_in_a_goldfish_game(immediate: bool) -> None:
    situation = a_game().with_library("Forest", "Island").build()
    without = effect(situation.game, situation.deck, S1, source="x", delta={"draw": 1})
    given = effect(
        situation.game,
        situation.deck,
        S1,
        source="x",
        delta={"draw": 1},
        immediate=immediate,  # type: ignore[call-arg]
    )
    assert given == without
