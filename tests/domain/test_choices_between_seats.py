"""Pending choices addressed to a seat in a contested game: what another seat's effect asks of
it, a look at another seat's hand, and the seat to act while such a choice waits."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.events import CardsRevealed
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.model import GameStatus, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from tests.support.acting import S1, S2, S3, acted, error_kinds, events_named
from tests.support.builders import Situation, a_game

M3B = pytest.mark.xfail(strict=True, reason="M3b: not built")
DISCARD = "discard a card"


def table_of(seats: int = 3, *, third_out: bool = False) -> Situation:
    """Seat 1's turn; every seat holds an Island, a Lightning Bolt and a Grizzly Bears, and
    has a Forest on its battlefield and in its library."""
    builder: Any = a_game()
    for number in range(1, seats + 1):
        if number > 1:
            builder = builder.and_an_opposing_seat()
        builder = (
            builder.with_hand("Island", "Lightning Bolt", "Grizzly Bears")
            .with_battlefield("Forest")
            .with_library("Forest", "Swamp")
        )
        if third_out and number == 3:
            builder = builder.eliminated()
    return builder.build()


def recorded(situation: Situation, delta: object, seat: SeatNumber = S1) -> Any:
    return effect(situation.game, situation.deck, seat, source="Mind Rot", delta=delta)


def asking(situation: Situation, *entries: dict[str, object]) -> Any:
    return acted(situation, recorded(situation, {"ask": list(entries)}))


def answered(situation: Situation, seat: SeatNumber, **answer: object) -> Any:
    choice = situation.game.pending[0].choice_id
    return choose(situation.game, situation.deck, seat, choice_id=choice, **answer)  # type: ignore[arg-type]


def card_of(situation: Situation, name: str, owner: SeatNumber) -> Any:
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


def pending_of(situation: Situation) -> list[tuple[str, SeatNumber, Any, str]]:
    return [(c.kind, c.seat, c.asked_by, c.text) for c in situation.game.pending]


# ------------------------------------------------------------------ ask


# @spec PLAY-097
@M3B
def test_ask_creates_a_pending_choice_per_seat_entry_by_entry_in_turn_order_from_the_next() -> None:
    situation = table_of()
    asking(
        situation,
        {"seats": [3, 2], "text": DISCARD},
        {"seats": "opponents", "text": "sacrifice a creature"},
    )
    assert pending_of(situation) == [
        ("ask", S2, S1, DISCARD),
        ("ask", S3, S1, DISCARD),
        ("ask", S2, S1, "sacrifice a creature"),
        ("ask", S3, S1, "sacrifice a creature"),
    ]


# @spec PLAY-120
@M3B
def test_an_ask_naming_the_acting_seat_addresses_it_last_of_its_entry() -> None:
    situation = table_of()
    asking(situation, {"seats": [1, 2, 3], "text": DISCARD})
    assert [seat for _, seat, _, _ in pending_of(situation)] == [S2, S3, S1]


# @spec PLAY-098
@M3B
def test_an_ask_of_the_opponents_names_every_other_seat_still_in_the_game() -> None:
    situation = table_of(third_out=True)
    asking(situation, {"seats": "opponents", "text": DISCARD})
    assert [seat for _, seat, _, _ in pending_of(situation)] == [S2]


# @spec GAME-109, GAME-120
@M3B
def test_while_an_ask_waits_the_seat_it_is_addressed_to_is_the_seat_to_act() -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": DISCARD})
    waiting = acting.seats_to_act(situation.game)
    assert waiting is not None
    assert (waiting.seats, waiting.kind.value, waiting.choice) == ((S2,), "choice", "ask")
    assert situation.game.status is GameStatus.PENDING_CHOICE


# @spec PLAY-099
@M3B
def test_an_ask_is_answered_with_the_answering_seat_s_own_delta_applied_at_once() -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": DISCARD})
    acted(situation, answered(situation, S2, delta={"discard": ["Island"]}))
    assert situation.names_in(Zone.GRAVEYARD, S2) == ["Island"]
    assert situation.names_in(Zone.HAND, S1) == ["Island", "Lightning Bolt", "Grizzly Bears"]
    assert situation.game.pending == []
    assert situation.game.status is GameStatus.ACTIVE


# @spec PLAY-121, PLAY-101
@M3B
@pytest.mark.parametrize("answer", [{}, {"delta": {}}], ids=["no delta", "an empty delta"])
def test_an_ask_answered_with_nothing_is_accepted_and_changes_nothing_else(
    answer: dict[str, object],
) -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": DISCARD})
    before = [(c.id, c.zone, c.tapped) for c in situation.game.cards]
    acted(situation, answered(situation, S2, **answer))
    assert [(c.id, c.zone, c.tapped) for c in situation.game.cards] == before
    assert situation.game.pending == []


# @spec PLAY-122
@M3B
def test_an_ask_answer_reaches_other_seats_as_any_delta_of_that_seat_may() -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": "deal 2 damage to any player"})
    delta = {"damage": {"1": 2}, "tap": [card_of(situation, "Forest", S1).id]}
    acted(situation, answered(situation, S2, delta=delta))
    assert situation.game.seat(S1).life == 38
    assert card_of(situation, "Forest", S1).tapped


# @spec PLAY-100
@M3B
@pytest.mark.parametrize(
    "delta",
    [
        {"ask": [{"seats": [1], "text": DISCARD}]},
        {"look_at_hand": 1},
        {"look": {"n": 1, "rest": "library_top"}},
        {"search": {}},
    ],
    ids=["ask", "look_at_hand", "look", "search"],
)
def test_an_ask_answer_may_not_create_a_pending_choice(delta: object) -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": DISCARD})
    assert error_kinds(answered(situation, S2, delta=delta)) == ["answer_may_not_reveal"]


# @spec PLAY-105
@M3B
def test_only_the_oldest_waiting_pending_choice_may_be_answered() -> None:
    situation = table_of()
    asking(situation, {"seats": [2, 3], "text": DISCARD})
    later = situation.game.pending[1].choice_id
    result = choose(situation.game, situation.deck, S3, choice_id=later, delta={})  # type: ignore[call-arg]
    assert error_kinds(result) == ["wrong_choice"]


# @spec PLAY-106
@M3B
def test_a_seat_may_not_answer_a_pending_choice_addressed_to_another_seat() -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": DISCARD})
    error = acting.may_call(situation.game, S3, "choose")
    assert error is not None
    assert error.kind.value == "not_your_call"


# @spec PLAY-107
@M3B
@pytest.mark.parametrize(
    ("argument", "value"),
    [("selections", {"graveyard": ["Island"]}), ("rest_order", ["Island"]), ("blocks", {})],
)
def test_an_ask_is_answered_only_with_a_delta(argument: str, value: object) -> None:
    situation = table_of()
    asking(situation, {"seats": [2], "text": DISCARD})
    assert error_kinds(answered(situation, S2, **{argument: value})) == ["wrong_answer"]


# @spec PLAY-107
@M3B
@pytest.mark.parametrize(
    ("reveal", "argument", "value"),
    [
        ({"look": {"n": 1, "rest": "library_top"}}, "delta", {}),
        ({"look": {"n": 1, "rest": "library_top"}}, "blocks", {}),
        ({"search": {}}, "rest_order", ["Forest"]),
    ],
    ids=["look with delta", "look with blocks", "search with rest_order"],
)
def test_a_look_or_search_is_answered_only_with_its_own_arguments(
    reveal: object, argument: str, value: object
) -> None:
    situation = a_game().with_library("Forest", "Swamp").build()
    acted(situation, recorded(situation, reveal))
    result = answered(situation, S1, selections={}, **{argument: value})
    assert error_kinds(result) == ["wrong_answer"]


# ------------------------------------------------------------------ look_at_hand


# @spec PLAY-102
@M3B
def test_look_at_hand_reveals_the_named_seat_s_hand_to_the_looking_seat() -> None:
    situation = table_of()
    result = acted(situation, recorded(situation, {"look_at_hand": 2}))
    (choice,) = situation.game.pending
    hand = [card.id for card in situation.game.hand_of(S2)]
    assert (choice.kind, choice.seat, choice.asked_by, choice.hand_of) == ("hand", S1, S1, S2)
    assert choice.revealed == hand
    (revealed,) = events_named(result, "CardsRevealed")
    assert [card.instance_id for card in revealed.cards] == hand


# @spec PLAY-104
@M3B
def test_look_at_an_empty_hand_creates_no_pending_choice() -> None:
    situation = a_game().and_an_opposing_seat().build()
    result = acted(situation, recorded(situation, {"look_at_hand": 2}))
    assert situation.game.pending == []
    assert [e.kind for e in events_named(result, "NothingRevealed")] == ["hand"]


# @spec PLAY-116
@M3B
def test_a_look_at_hand_beside_an_ask_shows_the_hand_the_answers_left() -> None:
    situation = table_of()
    asking_and_looking = {"ask": [{"seats": [2], "text": DISCARD}], "look_at_hand": 2}
    acted(situation, recorded(situation, asking_and_looking))
    assert [choice.kind for choice in situation.game.pending] == ["ask"]
    result = acted(situation, answered(situation, S2, delta={"discard": ["Island"]}))
    (choice,) = situation.game.pending
    assert choice.kind == "hand"
    shown = {situation.game.instance(i).name for i in choice.revealed}
    assert shown == {"Lightning Bolt", "Grizzly Bears"}
    assert len(events_named(result, "CardsRevealed")) == 1


# @spec PLAY-103, GAME-155
@M3B
def test_cards_selected_from_a_hand_go_to_their_owner_s_zones_and_the_rest_stay() -> None:
    situation = table_of()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    acted(situation, answered(situation, S1, selections={"graveyard": ["Lightning Bolt"]}))
    assert situation.names_in(Zone.GRAVEYARD, S2) == ["Lightning Bolt"]
    assert situation.names_in(Zone.GRAVEYARD, S1) == []
    assert situation.names_in(Zone.HAND, S2) == ["Island", "Grizzly Bears"]
    assert situation.names_in(Zone.HAND, S1) == ["Island", "Lightning Bolt", "Grizzly Bears"]


# @spec PLAY-103, GAME-155
@M3B
def test_a_hand_choice_may_select_nothing_or_a_card_by_its_instance_id() -> None:
    situation = table_of()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    island = card_of(situation, "Island", S2).id
    acted(situation, answered(situation, S1, selections={"exile": [island]}))
    assert situation.names_in(Zone.EXILE, S2) == ["Island"]


# @spec PLAY-111
@M3B
def test_a_card_selected_from_a_hand_to_the_battlefield_enters_under_its_owner() -> None:
    situation = table_of()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    acted(situation, answered(situation, S1, selections={"battlefield": ["Grizzly Bears"]}))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.zone, bears.controller) == (Zone.BATTLEFIELD, S2)


# @spec PLAY-112
@M3B
def test_a_hand_answer_s_control_puts_the_selected_card_under_the_seat_named() -> None:
    situation = table_of()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    answer = {
        "selections": {"battlefield": ["Grizzly Bears"]},
        "delta": {"control": {"1": ["Grizzly Bears"]}},
    }
    acted(situation, answered(situation, S1, **answer))
    bears = card_of(situation, "Grizzly Bears", S2)
    assert (bears.zone, bears.controller, bears.owner) == (Zone.BATTLEFIELD, S1, S2)


# @spec PLAY-113
@M3B
@pytest.mark.parametrize(
    "answer",
    [
        {"selections": {"battlefield": ["Grizzly Bears"]}, "delta": {"draw": 1}},
        {
            "selections": {"graveyard": ["Grizzly Bears"]},
            "delta": {"control": {"1": ["Grizzly Bears"]}},
        },
    ],
    ids=["another key", "control of a card not put onto the battlefield"],
)
def test_a_hand_answer_s_delta_holds_only_control_of_cards_it_puts_onto_the_battlefield(
    answer: dict[str, object],
) -> None:
    situation = table_of()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    assert error_kinds(answered(situation, S1, **answer)) == ["hand_answer_delta"]


# @spec PLAY-107
@M3B
def test_a_hand_choice_takes_no_rest_order() -> None:
    situation = table_of()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    result = answered(situation, S1, selections={}, rest_order=["Island"])
    assert error_kinds(result) == ["wrong_answer"]


# @spec GAME-090
@M3B
def test_cards_revealed_by_a_look_at_a_hand_are_shown_only_to_the_looking_seat() -> None:
    situation = table_of()
    result = acted(situation, recorded(situation, {"look_at_hand": 2}))
    events = (result.summary, *result.events)
    assert any(isinstance(e, CardsRevealed) for e in as_seen_by(events, S1))
    assert not any(isinstance(e, CardsRevealed) for e in as_seen_by(events, S3))
    assert not any(isinstance(e, CardsRevealed) for e in as_seen_by(events, S2))


# @spec GAME-094
@M3B
def test_the_public_form_of_a_look_at_a_hand_gives_its_kind_and_seats_but_no_cards() -> None:
    situation = table_of()
    result = acted(situation, recorded(situation, {"look_at_hand": 2}))
    seen = as_seen_by((result.summary, *result.events), S3)
    (public,) = [e for e in seen if getattr(e, "kind", None) == "hand"]
    assert (public.seat, public.hand_of) == (S1, S2)
    assert not hasattr(public, "cards")


# ------------------------------------------------------------------ the seat to act


# @spec GAME-117
@pytest.mark.parametrize("tool", ["play", "effect", "attack", "advance"])
def test_an_active_seat_with_its_own_pending_choice_may_only_choose(tool: str) -> None:
    situation = table_of(2)
    acted(situation, recorded(situation, {"look": {"n": 1, "rest": "library_top"}}))
    error = acting.may_call(situation.game, S1, tool)
    assert error is not None
    assert error.kind.value == "not_accepted_now"
    assert acting.may_call(situation.game, S1, "choose") is None


# @spec GAME-117
@pytest.mark.parametrize("tool", ["play", "effect", "attack", "advance"])
def test_with_nothing_waiting_the_active_seat_may_play_and_move_the_game(tool: str) -> None:
    assert acting.may_call(table_of(2).game, S1, tool) is None


# @spec CMBT-029, TURN-044
@M3B
@pytest.mark.parametrize("tool", ["attack", "advance", "play", "effect"])
def test_the_active_seat_may_not_act_while_a_choice_waits_on_another_seat(tool: str) -> None:
    situation = table_of(2)
    asking(situation, {"seats": [2], "text": DISCARD})
    error = acting.may_call(situation.game, S1, tool)
    assert error is not None
    assert error.kind.value == "not_your_call"
