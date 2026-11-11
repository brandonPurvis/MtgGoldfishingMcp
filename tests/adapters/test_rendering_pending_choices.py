"""The pending choices a seat owes, as its `get_state` listing shows them in a contested game; a
goldfish game's listing shows none."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.definitions import TOOL_DEFINITIONS
from mtg_goldfishing.adapters.mcp.listing_lines import state_lines
from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, acted, passed
from tests.support.builders import TESTED, Situation, a_game
from tests.support.tables import two_seats

NOT_BUILT = "coherence: get_state does not list a seat's pending choices"
HEADER = "Your pending choices"
DISCARD = "discard a card"


def a_duel() -> Situation:
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


def listing_lines(situation: Situation, seat: SeatNumber, detail: str = "summary") -> list[str]:
    listing: Any = list_state(situation.game, situation.deck, seat, detail)
    return state_lines(listing)


def choice_lines(lines: list[str]) -> list[str]:
    start = next(i for i, line in enumerate(lines) if line.startswith(HEADER))
    return lines[start : start + 1 + int(lines[start].split("(")[1].split(")")[0])]


# @spec TOOL-074
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_an_ask_owed_is_listed_with_the_asking_seat_and_its_text() -> None:
    situation = a_duel()
    immediately(situation, {"ask": [{"seats": [2], "text": DISCARD}]})
    choice = situation.game.pending[0].choice_id

    lines = listing_lines(situation, S2)

    assert choice_lines(lines) == [f"{HEADER} (1):", f"  {choice} (ask) from S1: {DISCARD}"]


# @spec TOOL-074
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_look_owed_is_listed_with_the_cards_it_revealed() -> None:
    situation = a_duel()
    immediately(situation, {"look": {"n": 1, "rest": "library_top"}})
    pending = situation.game.pending[0]
    card = situation.game.instance(pending.revealed[0])

    lines = listing_lines(situation, S1)

    assert choice_lines(lines)[1] == (
        f"  {pending.choice_id} (look): revealed {card.name} ({card.id})"
    )


# @spec TOOL-074
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_blocks_choice_owed_is_listed_with_the_attackers() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears")
    situation: Situation = builder.and_an_opposing_seat().with_battlefield("Llanowar Elves").build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    passed(situation, S2)
    acted(situation, advance(situation.game, situation.deck, S1, to="declare_blockers"))
    choice = situation.game.pending[0].choice_id
    bears = next(c for c in situation.game.cards if c.name == "Grizzly Bears")

    lines = listing_lines(situation, S2)

    assert choice_lines(lines)[1] == f"  {choice} (blocks): attacked by Grizzly Bears ({bears.id})"


# @spec TOOL-074
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_a_resolve_choice_owed_is_listed_with_its_item_held_delta_and_destination() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears", disturbed=True, delta={"life": 1}),
        lambda b: b.with_window("stack", asking=2),
    )
    passed(situation, S2)
    choice = situation.game.pending[0].choice_id

    lines = listing_lines(situation, S1)

    assert choice_lines(lines)[1] == (
        f'  {choice} (resolve): s1 Grizzly Bears holds delta {{"life": 1}}'
        " and goes to its default destination"
    )


# @spec TOOL-074
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_the_pending_choices_come_after_every_seat_and_before_the_payments() -> None:
    situation = a_duel()
    immediately(situation, {"ask": [{"seats": [2], "text": DISCARD}]})

    lines = listing_lines(situation, S2, "full")

    header = next(i for i, line in enumerate(lines) if line.startswith(HEADER))
    last_seat = max(i for i, line in enumerate(lines) if line.startswith("S1 ·"))
    payments = next(i for i, line in enumerate(lines) if line.startswith("Payments this turn"))
    assert last_seat < header < payments


# @spec TOOL-074, GAME-177
def test_a_seat_that_owes_no_pending_choice_has_no_pending_choices_line() -> None:
    situation = a_duel()
    immediately(situation, {"ask": [{"seats": [2], "text": DISCARD}]})

    lines = listing_lines(situation, S1)

    assert not any(line.startswith(HEADER) for line in lines)


# @spec GAME-178
def test_a_goldfish_game_s_listing_shows_no_pending_choice() -> None:
    situation: Situation = a_game().with_library("Swamp", "Plains").build()
    acted(
        situation,
        effect(
            situation.game,
            situation.deck,
            TESTED,
            source="Ponder",
            delta={"look": {"n": 2, "rest": "library_top"}},
        ),
    )
    assert situation.game.pending

    listing: Any = list_state(situation.game, situation.deck, TESTED)
    text = "\n".join(state_lines(listing))

    assert HEADER not in text
    assert "Swamp" not in text


# @spec TOOL-075
@pytest.mark.xfail(strict=True, reason=NOT_BUILT)
def test_get_state_says_a_contested_listing_includes_the_seat_s_pending_choices() -> None:
    get_state = next(d for d in TOOL_DEFINITIONS if d.name == "get_state")
    description = get_state.description
    contested = description[description.index("Contested games:") :]

    assert "pending choices" in contested
