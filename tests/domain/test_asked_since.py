"""Since when the seats to act have been asked: the change number a contested game holds for
it, set when the game is created, kept through mulligans, and set again by a change after
which the seat to act, or what it is asked, is not the same as before."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from mtg_goldfishing.domain.events import GameHasEnded
from mtg_goldfishing.domain.game import calls
from mtg_goldfishing.domain.game.model import (
    Game,
    PendingChoice,
    Reminder,
    StackItem,
    StackItemKind,
    Window,
    WindowKind,
)
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.steps import Step
from tests.domain.test_contested_start import OPPOSING_DECK, a_contested_game, created, deck_of
from tests.support.acting import S1, S2, S3
from tests.support.builders import a_game

pytestmark = pytest.mark.xfail(strict=True, reason="M3: not implemented yet")

# Reached untyped, so that these tests read the same before and after `before` exists.
accept_change: Any = calls.accept_change
NO_FIELD = "the game holds no asked-since change number at all"


def asked_since(game: Game) -> object:
    return vars(game).get("asked_since", NO_FIELD)


def holding(game: Game, change: int | None) -> Game:
    held: Any = game
    held.asked_since = change
    return game


def accepted(before: Game | None, applied: Applied, seat: SeatNumber, tool: str) -> Game:
    """The change counted as the game's next, as the application counts it."""
    accept_change(applied, seat, tool, {}, before=before)
    return applied.game


def changed_to(before: Game, change: Callable[[Game], object], seat: SeatNumber = S1) -> Game:
    """A change made by hand to a copy of the game, counted as the game's next."""
    after = before.copy()
    change(after)
    return accepted(before, Applied(after, GameHasEnded()), seat, "effect")


# ------------------------------------------------------------------ creation and mulligans


# @spec GAME-180
def test_a_new_contested_game_has_its_seats_asked_since_the_change_that_created_it() -> None:
    result = created(OPPOSING_DECK)
    assert isinstance(result, Applied), result

    game = accepted(None, result, result.game.tested.number, "new_game")

    assert (game.change, asked_since(game)) == (1, 1)


def a_mulligan_since_creation() -> Game:
    """Two seats taking mulligans, seat 1 first, asked since change 1, at change 1."""
    game = a_contested_game(OPPOSING_DECK, position=1)
    game.change = 1
    return holding(game, 1)


def mulliganed(game: Game, seat: SeatNumber, *, keep: bool) -> Game:
    result = mulligan(game, deck_of(game, seat), seat, keep=keep)
    assert isinstance(result, Applied), result
    return accepted(game, result, seat, "mulligan")


# @spec GAME-181
def test_a_mulligan_taken_during_mulligans_leaves_the_asked_since_change_as_it_was() -> None:
    game = mulliganed(a_mulligan_since_creation(), S2, keep=False)

    assert (game.change, asked_since(game)) == (2, 1)


# @spec GAME-181
def test_a_keep_that_leaves_another_seat_still_to_keep_leaves_the_asked_since_change() -> None:
    game = mulliganed(a_mulligan_since_creation(), S1, keep=True)

    assert (game.change, asked_since(game)) == (2, 1)


# @spec GAME-182
def test_the_keep_that_starts_the_game_sets_the_asked_since_change_to_its_own() -> None:
    game = mulliganed(a_mulligan_since_creation(), S1, keep=True)
    game = mulliganed(game, S2, keep=True)

    assert (game.change, asked_since(game)) == (3, 3)


# ------------------------------------------------------------------ changes after mulligans


def a_turn_of_seat_1(asked: int | None = 4) -> Game:
    """Seat 1's turn in main1 of table turn 5, two seats, asked since change `asked`, at
    change 6; seat 2 holds a Forest it may be shown reminders for."""
    builder: Any = a_game().in_step(Step.MAIN1, turn=5).with_hand("Forest")
    builder = builder.and_an_opposing_seat().with_battlefield("Forest", "Llanowar Elves")
    game: Game = builder.build().game
    game.change = 6
    return holding(game, asked)


def an_ask_for(seat: SeatNumber, choice_id: str) -> PendingChoice:
    return PendingChoice(choice_id, seat, "Duress", "ask", [], None, asked_by=S1, text="discard")


def a_spell(item: str, controller: SeatNumber = S1) -> StackItem:
    return StackItem(item, controller, StackItemKind.ABILITY, "an ability", "effect")


def asking_about(game: Game, item: str, seat: SeatNumber = S2) -> None:
    game.stack.append(a_spell(item))
    game.window = Window(WindowKind.STACK, seat)


def reminded(game: Game, seat: SeatNumber, step: Step, *names: str) -> None:
    game.step = step
    for card in game.battlefield_of(seat):
        if card.name in names:
            game.seat(seat).reminders.append(Reminder(card.id, card.name, step, turn=game.turn))


# @spec GAME-182
def test_a_change_after_which_the_same_seat_is_asked_the_same_keeps_the_asked_since_change() -> (
    None
):
    game = changed_to(a_turn_of_seat_1(), lambda after: setattr(after.seat(S1), "life", 39))

    assert (game.change, asked_since(game)) == (7, 4)


# @spec GAME-182
def test_a_change_after_which_another_seat_is_asked_sets_the_asked_since_change() -> None:
    game = changed_to(a_turn_of_seat_1(), lambda after: asking_about(after, "s1"))

    assert (game.change, asked_since(game)) == (7, 7)


# @spec GAME-182, GAME-183
def test_the_active_seat_asked_again_after_another_seat_is_asked_anew() -> None:
    responding = a_turn_of_seat_1()
    asking_about(responding, "s1")

    def resolved(after: Game) -> None:
        after.stack.clear()
        after.window = None

    game = changed_to(responding, resolved, seat=S2)

    assert asked_since(game) == 7


def both(*changes: Callable[[Game], object]) -> Callable[[Game], None]:
    def change(game: Game) -> None:
        for each in changes:
            each(game)

    return change


def pending(*choices: PendingChoice) -> Callable[[Game], None]:
    def change(game: Game) -> None:
        game.pending = list(choices)

    return change


def turn(table_turn: int) -> Callable[[Game], None]:
    def change(game: Game) -> None:
        game.turn = table_turn

    return change


def window(kind: WindowKind, seat: SeatNumber = S2) -> Callable[[Game], None]:
    def change(game: Game) -> None:
        game.window = Window(kind, seat)

    return change


def stack(*items: str) -> Callable[[Game], None]:
    def change(game: Game) -> None:
        game.stack = [a_spell(item) for item in items]
        game.window = Window(WindowKind.STACK, S2)

    return change


def reminders(step: Step, *names: str) -> Callable[[Game], None]:
    def change(game: Game) -> None:
        game.seat(S2).reminders = []
        reminded(game, S2, step, *names)

    return change


# (what the seat to act is asked before, what it is asked after, whether that is the same)
QUESTIONS: list[Any] = [
    pytest.param(pending(an_ask_for(S2, "x1")), pending(an_ask_for(S2, "x1")), True, id="choice"),
    pytest.param(
        pending(an_ask_for(S2, "x1")),
        pending(an_ask_for(S2, "x2")),
        False,
        id="another choice id",
    ),
    pytest.param(
        reminders(Step.UPKEEP, "Forest"), reminders(Step.UPKEEP, "Forest"), True, id="reminder"
    ),
    pytest.param(
        reminders(Step.UPKEEP, "Forest"),
        reminders(Step.DRAW, "Forest"),
        False,
        id="reminder in another step",
    ),
    pytest.param(
        reminders(Step.UPKEEP, "Forest"),
        reminders(Step.UPKEEP, "Forest", "Llanowar Elves"),
        False,
        id="reminder of other permanents",
    ),
    pytest.param(stack("s1"), stack("s1"), True, id="window"),
    pytest.param(stack("s1"), stack("s1", "s2"), False, id="window about another stack item"),
    pytest.param(
        window(WindowKind.END), window(WindowKind.ATTACK), False, id="window of another kind"
    ),
    pytest.param(turn(5), turn(5), True, id="turn"),
    pytest.param(turn(5), turn(7), False, id="turn of another table turn"),
    pytest.param(
        stack("s1"), both(stack(), pending(an_ask_for(S2, "x1"))), False, id="another kind"
    ),
]


# @spec GAME-183
@pytest.mark.parametrize(("before", "after", "same"), QUESTIONS)
def test_what_a_seat_to_act_is_asked_is_new_when_its_kind_or_what_it_is_about_differs(
    before: Callable[[Game], object], after: Callable[[Game], object], same: bool
) -> None:
    game = a_turn_of_seat_1()
    before(game)

    changed = changed_to(game, after)

    assert asked_since(changed) == (4 if same else 7)


# @spec GAME-183
def test_a_blocks_choice_counts_as_a_pending_choice_like_any_other() -> None:
    game = a_turn_of_seat_1()
    blocks = PendingChoice("x1", S2, "attack", "blocks", [], None)

    changed = changed_to(game, pending(blocks))

    assert asked_since(changed) == 7


# ------------------------------------------------------------------ games that hold none


# @spec GAME-184
def test_a_game_that_holds_none_keeps_none_while_the_seat_to_act_is_asked_the_same() -> None:
    game = changed_to(
        a_turn_of_seat_1(asked=None), lambda after: setattr(after.seat(S1), "life", 1)
    )

    assert asked_since(game) is None


# @spec GAME-184
def test_a_game_that_holds_none_is_given_one_by_a_change_that_asks_anew() -> None:
    game = changed_to(a_turn_of_seat_1(asked=None), lambda after: asking_about(after, "s1"))

    assert asked_since(game) == 7


# @spec GAME-185
def test_a_new_goldfish_game_holds_no_asked_since_change() -> None:
    result = created()
    assert isinstance(result, Applied), result

    game = accepted(None, result, result.game.tested.number, "new_game")

    assert asked_since(game) is None


# @spec GAME-185
def test_a_change_to_a_goldfish_game_holds_no_asked_since_change() -> None:
    game = a_game().with_hand("Forest").build().game

    changed = changed_to(game, turn(9))

    assert asked_since(changed) is None


# @spec GAME-183
def test_three_seats_asked_in_turn_about_one_item_are_each_asked_anew() -> None:
    builder: Any = a_game().in_step(Step.MAIN1, turn=5)
    game = holding(builder.and_an_opposing_seat().and_an_opposing_seat().build().game, 4)
    game.change = 6
    asking_about(game, "s1", S2)

    changed = changed_to(game, window(WindowKind.STACK, S3), seat=S2)

    assert asked_since(changed) == 7
