"""Moves that reach another seat's zones: a contested game's event for a card moved by a
delta's `move`, or by the answer to a `hand` pending choice, names the seat whose zone the card
left or entered whenever that seat is not the one whose delta or answer moved it."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from tests.support.acting import S1, S2, acted, events_named
from tests.support.builders import Situation, a_game


def two_seats(*, first: Any = None, second: Any = None) -> Situation:
    """Seat 1's turn in its first main step; each seat as the functions given describe it."""
    builder: Any = (first or (lambda b: b))(a_game())
    builder = (second or (lambda b: b))(builder.and_an_opposing_seat())
    situation: Situation = builder.build()
    return situation


def moved(situation: Situation, delta: object, seat: SeatNumber = S1) -> Any:
    result = effect(
        situation.game, situation.deck, seat, source="a test effect", delta=delta, immediate=True
    )
    return acted(situation, result)


def named_seats(event: Any) -> tuple[object, object]:
    """The seats a move event names with the zone left and the zone entered."""
    fields = vars(event)
    return fields.get("from_seat", "no from_seat"), fields.get("to_seat", "no to_seat")


def the_move(result: Any) -> Any:
    (event,) = events_named(result, "CardMoved")
    return event


# ------------------------------------------------------------------ a delta's move


# @spec PLAY-144
@pytest.mark.parametrize(
    ("zone", "describe"),
    [
        ("graveyard", lambda b: b.with_graveyard("Grizzly Bears")),
        ("exile", lambda b: b.with_exile("Grizzly Bears")),
        ("battlefield", lambda b: b.with_battlefield("Grizzly Bears")),
    ],
)
def test_a_move_from_another_seat_s_zone_names_that_seat_with_the_zone_left(
    zone: str, describe: Any
) -> None:
    situation = two_seats(second=describe)

    event = the_move(moved(situation, {"move": {"battlefield": ["Grizzly Bears"]}}))

    assert (event.from_zone, named_seats(event)) == (zone, (S2, None))


# @spec PLAY-144
def test_a_move_from_another_seat_s_command_zone_names_that_seat() -> None:
    situation = two_seats(second=lambda b: b.with_commander("Kenrith, the Returned King"))

    event = the_move(moved(situation, {"move": {"hand": ["Kenrith, the Returned King"]}}))

    assert named_seats(event) == (S2, S2)


# @spec PLAY-144
def test_a_permanent_another_seat_controls_is_named_with_its_controller_not_its_owner() -> None:
    situation = two_seats(
        first=lambda b: b.with_battlefield("Grizzly Bears").controlled_by("Grizzly Bears", 2)
    )

    event = the_move(moved(situation, {"move": {"exile": ["Grizzly Bears"]}}))

    assert named_seats(event) == (S2, None)


# @spec PLAY-145
@pytest.mark.parametrize("destination", ["hand", "graveyard", "exile", "library_top"])
def test_a_move_into_another_seat_s_zone_names_that_seat_with_the_destination(
    destination: str,
) -> None:
    situation = two_seats(second=lambda b: b.with_battlefield("Grizzly Bears"))

    event = the_move(moved(situation, {"move": {destination: ["Grizzly Bears"]}}))

    assert named_seats(event) == (S2, S2)


# @spec PLAY-145
def test_another_seat_s_commander_sent_to_its_command_zone_instead_names_that_seat() -> None:
    situation = two_seats(
        second=lambda b: b.with_commander("Kenrith, the Returned King", zone=Zone.BATTLEFIELD)
    )

    event = the_move(moved(situation, {"move": {"graveyard": ["Kenrith, the Returned King"]}}))

    assert (event.to, event.commander_redirected, named_seats(event)) == ("command", True, (S2, S2))


# @spec PLAY-145
def test_a_move_to_the_battlefield_names_no_seat_with_the_destination() -> None:
    situation = two_seats(second=lambda b: b.with_graveyard("Grizzly Bears"))

    event = the_move(moved(situation, {"move": {"battlefield_tapped": ["Grizzly Bears"]}}))

    assert named_seats(event)[1] is None


# @spec PLAY-145
def test_a_countered_spell_of_another_seat_names_its_owner_with_the_graveyard_it_goes_to() -> None:
    builder: Any = a_game().and_an_opposing_seat().with_spell_on_stack("Shivan Dragon")
    situation = builder.build()

    event = the_move(moved(situation, {"counter": ["s1"]}))

    assert (event.from_zone, named_seats(event)) == ("stack", (None, S2))


# @spec PLAY-147
def test_a_move_between_the_acting_seat_s_own_zones_names_no_seat() -> None:
    situation = two_seats(first=lambda b: b.with_graveyard("Grizzly Bears"))

    event = the_move(moved(situation, {"move": {"hand": ["Grizzly Bears"]}}))

    assert named_seats(event) == (None, None)


# @spec PLAY-147
def test_the_acting_seat_s_own_countered_spell_names_no_seat() -> None:
    situation = a_game().with_spell_on_stack("Shivan Dragon").and_an_opposing_seat().build()

    event = the_move(moved(situation, {"counter": ["s1"]}, seat=S2))

    assert named_seats(event) == (None, S1)


# @spec PLAY-147
def test_a_goldfish_move_names_no_seat() -> None:
    situation = a_game().with_graveyard("Grizzly Bears").build()
    result = effect(
        situation.game,
        situation.deck,
        S1,
        source="a test effect",
        delta={"move": {"hand": ["Grizzly Bears"]}},
    )

    assert named_seats(the_move(acted(situation, result))) == (None, None)


# ------------------------------------------------------------------ a hand choice's answer


def looked_at_hand_of_seat_2() -> Situation:
    situation = two_seats(second=lambda b: b.with_hand("Lightning Bolt", "Grizzly Bears"))
    moved(situation, {"look_at_hand": 2})
    return situation


def answered(situation: Situation, **answer: object) -> Any:
    choosing: Any = choose
    choice = situation.game.pending[0].choice_id
    return acted(
        situation, choosing(situation.game, situation.deck, S1, choice_id=choice, **answer)
    )


def the_placement(result: Any) -> Any:
    (resolved,) = events_named(result, "ChoiceResolved")
    (placement,) = resolved.placements
    return placement


# @spec PLAY-146
@pytest.mark.parametrize("destination", ["graveyard", "exile", "library_bottom", "battlefield"])
def test_a_card_taken_from_another_seat_s_hand_names_that_seat_at_both_ends(
    destination: str,
) -> None:
    situation = looked_at_hand_of_seat_2()

    placement = the_placement(answered(situation, selections={destination: ["Lightning Bolt"]}))

    assert named_seats(placement) == (S2, S2)


# @spec PLAY-146, PLAY-147
def test_a_card_taken_from_another_seat_s_hand_onto_the_answering_seat_s_battlefield() -> None:
    situation = looked_at_hand_of_seat_2()

    placement = the_placement(
        answered(
            situation,
            selections={"battlefield": ["Grizzly Bears"]},
            delta={"control": {"1": ["Grizzly Bears"]}},
        )
    )

    assert named_seats(placement) == (S2, None)
