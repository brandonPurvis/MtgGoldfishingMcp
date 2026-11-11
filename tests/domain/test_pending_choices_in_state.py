"""What a seat's state lists of the pending choices it owes in a contested game, so that a seat
that missed the line creating a choice can still find what it must answer."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, acted, passed
from tests.support.builders import Situation, a_game
from tests.support.tables import two_seats

NOT_BUILT = "coherence: get_state does not list a seat's pending choices"
DISCARD = "discard a card"
SACRIFICE = "sacrifice a creature"


def a_duel() -> Situation:
    """Seat 1's turn; each seat has a Forest, a card in hand and a library."""
    builder: Any = a_game().with_hand("Island").with_battlefield("Forest")
    builder = builder.with_library("Swamp", "Plains").and_an_opposing_seat()
    situation: Situation = (
        builder.with_hand("Island").with_battlefield("Forest").with_library("Wastes").build()
    )
    return situation


def immediately(situation: Situation, delta: object, seat: SeatNumber = S1) -> None:
    acted(
        situation,
        effect(
            situation.game,
            situation.deck,
            seat,
            source="a test effect",
            delta=delta,
            immediate=True,
        ),
    )


def choices_of(situation: Situation, seat: SeatNumber) -> Any:
    listing: Any = list_state(situation.game, situation.deck, seat)
    return listing.choices


# @spec GAME-172
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_seat_s_state_lists_the_pending_choices_it_owes_in_the_order_they_are_answered() -> None:
    situation = a_duel()
    immediately(
        situation,
        {"ask": [{"seats": [2], "text": DISCARD}, {"seats": [2], "text": SACRIFICE}]},
    )

    listed = [(choice.choice_id, choice.kind) for choice in choices_of(situation, S2)]

    assert listed == [(choice.choice_id, "ask") for choice in situation.game.pending]


# @spec GAME-173
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_look_is_listed_with_the_cards_it_revealed_by_name_and_instance_id() -> None:
    situation = a_duel()
    immediately(situation, {"look": {"n": 1, "rest": "library_top"}})
    revealed = situation.game.pending[0].revealed
    expected = [(situation.game.instance(i).name, i) for i in revealed]

    [choice] = choices_of(situation, S1)

    assert [(card.name, card.instance_id) for card in choice.revealed] == expected


# @spec GAME-174
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_an_ask_is_listed_with_its_text_and_the_seat_whose_effect_asked() -> None:
    situation = a_duel()
    immediately(situation, {"ask": [{"seats": [2], "text": DISCARD}]})

    [choice] = choices_of(situation, S2)

    assert (choice.text, choice.asked_by) == (DISCARD, S1)


# @spec GAME-175
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_blocks_choice_is_listed_with_the_attackers_it_may_block() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears")
    situation: Situation = builder.and_an_opposing_seat().with_battlefield("Llanowar Elves").build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    passed(situation, S2)
    acted(situation, advance(situation.game, situation.deck, S1, to="declare_blockers"))
    bears = next(c for c in situation.game.cards if c.name == "Grizzly Bears")

    [choice] = choices_of(situation, S2)

    assert [(card.name, card.instance_id) for card in choice.attackers] == [
        ("Grizzly Bears", bears.id)
    ]


# @spec GAME-176
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_resolve_choice_is_listed_with_its_item_source_held_delta_and_destination() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears", disturbed=True, delta={"life": 1}),
        lambda b: b.with_window("stack", asking=2),
    )
    passed(situation, S2)

    [choice] = choices_of(situation, S1)

    assert (choice.item, choice.source, choice.delta, choice.to, choice.error) == (
        "s1",
        "Grizzly Bears",
        {"life": 1},
        None,
        None,
    )


# @spec GAME-177
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_seat_s_state_lists_no_pending_choice_addressed_to_another_seat() -> None:
    situation = a_duel()
    immediately(situation, {"ask": [{"seats": [2], "text": DISCARD}]})

    assert choices_of(situation, S1) == ()
