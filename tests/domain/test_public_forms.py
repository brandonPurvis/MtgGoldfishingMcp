"""What any seat may see of a call in a contested game: the public form of each event, and
what a seat is shown of an event that touches its own hand or library."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.domain.game import seeing
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted
from tests.support.builders import Situation, a_game

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
SRC = Path(__file__).resolve().parents[2] / "src" / "mtg_goldfishing"
PUBLIC_FORMS = ("HiddenCardsDrawn", "HiddenCardsMoved", "HiddenMulliganTaken", "HiddenHandKept")


def a_table(*, step: Step = Step.MAIN1) -> Situation:
    """Seat 1's turn of three seats; each holds an Island and a Forest, has a Forest and a Sol
    Ring on its battlefield and Forests in its library."""
    builder: Any = a_game().in_step(step)
    for number in (1, 2, 3):
        if number > 1:
            builder = builder.and_an_opposing_seat()
        builder = (
            builder.with_hand("Island", "Grizzly Bears")
            .with_battlefield("Forest", "Sol Ring")
            .with_library("Forest", "Forest", "Forest")
        )
    return builder.build()


def in_mulligans() -> Situation:
    """Two seats taking mulligans, each with seven cards in hand and fourteen in its library."""
    builder: Any = a_game().in_mulligan().with_hand(*["Island"] * 7).with_library(*["Forest"] * 14)
    builder = builder.and_an_opposing_seat().with_hand(*["Island"] * 7)
    return builder.with_library(*["Forest"] * 14).build()


def recorded(situation: Situation, delta: object, seat: SeatNumber = S1) -> Any:
    result = effect(situation.game, situation.deck, seat, source="a test effect", delta=delta)
    return acted(situation, result)


def reported(result: Any) -> tuple[Any, ...]:
    return (result.summary, *result.events)


def public(result: Any) -> tuple[Any, ...]:
    form: Any = seeing.public_form  # type: ignore[attr-defined]
    return tuple(form(reported(result)))


def seen_by(result: Any, seat: SeatNumber) -> tuple[Any, ...]:
    return seeing.as_seen_by(reported(result), seat)


def named(events: tuple[Any, ...], name: str) -> list[Any]:
    return [event for event in events if type(event).__name__ == name]


def looked_at_and_put_on_top(situation: Situation) -> Any:
    """Seat 1 looks at seat 2's hand and puts its Island on top of seat 2's library."""
    recorded(situation, {"look_at_hand": 2})
    (choice,) = situation.game.pending
    result = choose(
        situation.game,
        situation.deck,
        S1,
        choice_id=choice.choice_id,
        selections={"library_top": ["Island"]},
    )
    return acted(situation, result)


# ------------------------------------------------------------------ public forms


# @spec GAME-091
@NOT_BUILT
def test_the_public_form_of_a_draw_gives_the_seat_and_a_count_and_no_names() -> None:
    situation = a_table()
    result = recorded(situation, {"draw": 2})
    (drawn,) = named(public(result), "HiddenCardsDrawn")
    assert (drawn.seat, drawn.count) == (S1, 2)
    assert named(public(result), "CardsDrawn") == []


# @spec GAME-091
@NOT_BUILT
def test_the_public_form_of_a_card_moved_from_hand_to_library_gives_a_count_and_no_name() -> None:
    situation = a_table()
    result = recorded(situation, {"move": {"library_top": ["Island"]}})
    (moved,) = named(public(result), "HiddenCardsMoved")
    assert (moved.seat, moved.from_zone, moved.to, moved.count) == (S1, "hand", "library_top", 1)
    assert "Island" not in repr(public(result))


# @spec GAME-168
@NOT_BUILT
def test_the_public_form_of_a_permanent_returned_to_its_owner_s_hand_names_it() -> None:
    situation = a_table()
    result = recorded(situation, {"move": {"hand": ["Sol Ring"]}})
    (moved,) = named(public(result), "CardMoved")
    assert (moved.card, moved.from_zone, moved.to) == ("Sol Ring", "battlefield", "hand")


# @spec GAME-092
@NOT_BUILT
def test_the_public_form_of_a_card_moved_from_hand_to_a_public_zone_names_it() -> None:
    situation = a_table()
    result = recorded(situation, {"move": {"graveyard": ["Island"]}})
    (moved,) = named(public(result), "CardMoved")
    assert (moved.card, moved.from_zone, moved.to) == ("Island", "hand", "graveyard")


# @spec GAME-093
@NOT_BUILT
def test_the_public_form_of_a_kept_hand_gives_the_numbers_kept_and_bottomed() -> None:
    situation = in_mulligans()
    for _ in range(2):
        acted(situation, mulligan(situation.game, situation.deck, S2, keep=False))
    result = acted(
        situation, mulligan(situation.game, situation.deck, S2, keep=True, bottom=["Forest"])
    )
    (kept,) = named(public(result), "HiddenHandKept")
    assert (kept.seat, kept.kept, kept.bottomed) == (S2, 6, 1)
    assert named(public(result), "HandKept") == []


# @spec GAME-153
@NOT_BUILT
def test_the_public_form_of_a_mulligan_gives_the_seat_and_the_mulligans_taken() -> None:
    situation = in_mulligans()
    acted(situation, mulligan(situation.game, situation.deck, S2, keep=False))
    result = acted(situation, mulligan(situation.game, situation.deck, S2, keep=False))
    (taken,) = named(public(result), "HiddenMulliganTaken")
    assert (taken.seat, taken.mulligans) == (S2, 2)
    assert named(public(result), "MulliganTaken") == []


# @spec GAME-094
@NOT_BUILT
def test_the_public_form_of_a_look_at_a_hand_shows_who_looks_at_whose_hand() -> None:
    situation = a_table()
    result = recorded(situation, {"look_at_hand": 2})
    (look,) = named(public(result), "ChoiceRevealedTo")
    assert (look.kind, look.seat, look.hand_of) == ("hand", S1, S2)
    assert named(public(result), "CardsRevealed") == []


# ------------------------------------------------------------------ what a seat is shown


# @spec GAME-154
def test_a_seat_is_shown_by_name_the_card_it_drew_when_another_seat_s_call_began_its_turn() -> None:
    situation = a_table(step=Step.CLEANUP)
    result = acted(situation, advance(situation.game, situation.deck, S1))
    (drawn,) = named(seen_by(result, S2), "CardsDrawn")
    assert drawn.cards == ("Forest",)


# @spec GAME-154
def test_a_seat_is_shown_by_name_its_card_another_seat_s_call_put_into_its_library() -> None:
    situation = a_table()
    result = looked_at_and_put_on_top(situation)
    (placed,) = named(seen_by(result, S2), "ChoiceResolved")
    assert [(p.card, p.to) for p in placed.placements] == [("Island", "library_top")]


# @spec GAME-095
@NOT_BUILT
def test_a_third_seat_sees_a_card_put_into_another_seat_s_library_only_as_a_count() -> None:
    situation = a_table()
    result = looked_at_and_put_on_top(situation)
    (moved,) = named(seen_by(result, S3), "HiddenCardsMoved")
    assert (moved.seat, moved.to, moved.count) == (S2, "library_top", 1)
    assert "Island" not in repr(seen_by(result, S3))


# @spec GAME-095
@NOT_BUILT
def test_the_seat_whose_call_moved_another_seat_s_hidden_card_sees_only_its_public_form() -> None:
    situation = a_table()
    result = looked_at_and_put_on_top(situation)
    assert named(seen_by(result, S1), "HiddenCardsMoved") != []
    assert "Island" not in repr(seen_by(result, S1))


# @spec GAME-095
def test_a_seat_sees_another_seat_s_draw_only_as_a_count() -> None:
    situation = a_table(step=Step.CLEANUP)
    result = acted(situation, advance(situation.game, situation.deck, S1))
    (drawn,) = named(seen_by(result, S3), "HiddenCardsDrawn")
    assert (drawn.seat, drawn.count) == (S2, 1)


# ------------------------------------------------------------------ the filter's one home


def _constructed_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


# @spec APP-033
@NOT_BUILT
def test_public_forms_are_made_by_the_domain_filter_and_nowhere_outside_the_domain() -> None:
    outside = [
        f"{path.relative_to(SRC)} builds {name}"
        for ring in ("application", "adapters")
        for path in sorted((SRC / ring).rglob("*.py"))
        for name in _constructed_names(path) & set(PUBLIC_FORMS)
    ]
    assert outside == []
    assert callable(seeing.public_form)  # type: ignore[attr-defined]
