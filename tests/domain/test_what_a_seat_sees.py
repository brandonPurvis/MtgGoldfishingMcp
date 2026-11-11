"""What a seat of a contested game may see: its own hand, every public zone, and only the sizes
of other seats' hands and libraries."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.events import NoticeKind
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.play.playing import play
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import Situation, a_game

S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)
ATRAXA = "Atraxa, Praetors' Voice"
KENRITH = "Kenrith, the Returned King"


def a_table_of_three() -> Situation:
    """Seat 2's turn: each seat with its own hand, library, battlefield and graveyard."""
    builder: Any = (
        a_game()
        .in_step(Step.MAIN1)
        .in_turn_of(2)
        .with_commander(ATRAXA)
        .with_hand("Counterspell", "Ancestral Vision")
        .with_battlefield("Island", "Sol Ring")
        .with_graveyard("Ponder")
        .with_exile("Lightning Bolt")
        .with_library("Plains", "Plains", "Plains")
    )
    builder = (
        builder.and_an_opposing_seat()
        .with_commander(KENRITH)
        .with_hand("Shivan Dragon")
        .with_battlefield("Mountain", "Llanowar Elves")
        .controlled_by("Llanowar Elves", 1)
        .with_library("Swamp")
        .with_life(31)
    )
    return (
        builder.and_an_opposing_seat()
        .with_hand("Serra Angel", "Goblin Guide", "Fireball")
        .with_battlefield("Forest")
        .with_graveyard("Rampant Growth")
        .with_library("Wastes", "Wastes")
        .eliminated()
        .build()
    )


def listed(situation: Situation, seat: SeatNumber, detail: str = "summary") -> Any:
    return list_state(situation.game, situation.deck, seat, detail)


def seat_listing(listing: Any, seat: SeatNumber) -> Any:
    return next(each for each in listing.seats if each.seat == seat)


# @spec GAME-121, GAME-088
def test_a_seat_s_state_lists_its_own_hand_and_no_other_seat_s() -> None:
    listing = listed(a_table_of_three(), S1)
    assert listing.hand == ("Counterspell", "Ancestral Vision")
    shown = repr(listing)
    assert "Shivan Dragon" not in shown
    assert "Serra Angel" not in shown


# @spec GAME-121
def test_a_seat_s_state_lists_every_seat_s_public_zones_in_turn_order() -> None:
    listing = listed(a_table_of_three(), S3)
    assert [each.seat for each in listing.seats] == [S1, S2, S3]
    first, second, third = listing.seats
    assert [p.name for p in first.battlefield] == ["Island", "Sol Ring", "Llanowar Elves"]
    assert [p.name for p in second.battlefield] == ["Mountain"]
    assert (first.graveyard, third.graveyard) == (("Ponder",), ("Rampant Growth",))
    assert (first.command, second.command, third.command) == ((ATRAXA,), (KENRITH,), ())


# @spec GAME-121
def test_a_seat_s_state_lists_the_current_notices() -> None:
    situation = a_table_of_three()
    situation.game.notices.append(NoticeKind.TURN_LIMIT)
    assert listed(situation, S2).notices == (NoticeKind.TURN_LIMIT,)


# @spec GAME-089, GAME-122
def test_a_seat_s_state_gives_each_seat_s_life_hand_and_library_sizes_and_who_is_out() -> None:
    listing = listed(a_table_of_three(), S1)
    assert [
        (each.seat, each.life, each.hand_size, each.library_size, each.eliminated)
        for each in listing.seats
    ] == [(S1, 40, 2, 3, False), (S2, 31, 1, 1, False), (S3, 40, 3, 2, True)]


# @spec GAME-124
def test_a_permanent_another_seat_owns_is_listed_with_its_controller_naming_its_owner() -> None:
    listing = listed(a_table_of_three(), S2)
    elves = next(p for p in seat_listing(listing, S1).battlefield if p.name == "Llanowar Elves")
    island = next(p for p in seat_listing(listing, S1).battlefield if p.name == "Island")
    assert (elves.owner, island.owner) == (S2, None)


# @spec GAME-125
def test_the_full_state_adds_every_seat_s_exile() -> None:
    listing = listed(a_table_of_three(), S2, "full")
    assert [each.exile for each in listing.seats] == [("Lightning Bolt",), (), ()]


# @spec GAME-125
def test_the_full_state_adds_each_commander_s_casts_and_damage_to_each_other_seat() -> None:
    situation = a_table_of_three()
    situation.game.seat(S1).commander_casts["c1"] = 2
    tested: Any = situation.game.seat(S1)
    tested.commander_damage = {"c1": {"2": 7}}
    listing = listed(situation, S3, "full")
    (atraxa,) = seat_listing(listing, S1).commanders
    assert (atraxa.name, atraxa.casts, atraxa.damage) == (ATRAXA, 2, (7, 0))


# @spec GAME-125
def test_the_full_state_adds_the_calling_seat_s_payments_this_turn() -> None:
    builder: Any = a_game().in_step(Step.MAIN1).in_turn_of(2).with_battlefield("Forest")
    situation = (
        builder.and_an_opposing_seat()
        .with_battlefield("Forest")
        .with_hand("Llanowar Elves")
        .build()
    )
    result: Any = play(situation.game, situation.deck, S2, card="Llanowar Elves")
    situation.game = result.game
    assert [p.mana_spent for p in listed(situation, S2, "full").payments] == [1]
    assert listed(situation, S1, "full").payments == ()


# ------------------------------------------------------------------ the status line's facts


# @spec GAME-089
def test_a_seat_s_summary_gives_its_own_figures_and_every_other_seat_s_life() -> None:
    situation = a_table_of_three()
    summary: Any = summarize(situation.game, situation.deck, S2)
    assert (summary.hand, summary.life, summary.table.seat, summary.table.active) == (
        1,
        31,
        S2,
        S2,
    )
    assert [(o.seat, o.life, o.eliminated) for o in summary.table.others] == [
        (S1, 40, False),
        (S3, 40, True),
    ]
