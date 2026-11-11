"""Response windows of a contested game: when they open, whom they ask and in what order,
automatic passes, `pass`, the asking waiting on choices, and who the seat to act is."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import PendingChoice, Zone
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import play
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import (
    S1,
    S2,
    S3,
    acted,
    asking,
    cast,
    check_kinds,
    events_named,
    passed,
    recorded,
    stack_ids,
)
from tests.support.builders import a_game
from tests.support.tables import bolt_at, same, three_seats, two_seats

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M4: not built")


def window_kind(situation: Any) -> str | None:
    window = situation.game.window
    return None if window is None else window.kind.value


def passed_seats(situation: Any) -> tuple[Any, ...]:
    window = situation.game.window
    return () if window is None else window.passed


def asked(situation: Any) -> tuple[tuple[Any, ...], str, str | None]:
    """The seats to act, what they are asked, and the choice kind if any."""
    found: Any = acting.seats_to_act(situation.game)
    return found.seats, found.kind.value, found.choice


def refusal_kind(situation: Any, seat: Any, tool: str) -> str:
    error: Any = acting.may_call(situation.game, seat, tool)
    assert error is not None, f"{tool} from {seat} was accepted"
    return str(error.kind.value)


def accepted(situation: Any, seat: Any, tool: str) -> bool:
    return acting.may_call(situation.game, seat, tool) is None


def advanced(situation: Any, seat: Any = S1, **arguments: Any) -> Any:
    return acted(situation, advance(situation.game, situation.deck, seat, **arguments))


def a_pending_look(situation: Any, seat: Any) -> None:
    situation.game.pending.append(PendingChoice("x9", seat, "a look", "look", [], None))


# ------------------------------------------------------------------ when windows open


# @spec STACK-034
@NOT_BUILT
def test_an_item_put_on_the_stack_opens_a_window_asking_the_seat_after_its_controller() -> None:
    situation = three_seats(lambda b: b.with_hand("Lightning Bolt"))

    cast(situation, S1, "Lightning Bolt", delta=bolt_at(3))

    assert (window_kind(situation), asking(situation)) == ("stack", S2)


# @spec STACK-034
@NOT_BUILT
def test_an_item_of_another_seat_is_asked_about_from_the_seat_after_it() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_hand("Lightning Bolt").with_window("stack", asking=2),
    )

    cast(situation, S2, "Lightning Bolt", delta=bolt_at(1))

    assert asking(situation) == S3


# @spec STACK-035
@NOT_BUILT
def test_after_the_top_item_resolves_the_window_asks_about_the_new_top_item() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}),
        lambda b: b.with_window("stack", asking=1, passed=(3,)),
    )

    passed(situation, S1)

    assert stack_ids(situation) == ["s1"]
    assert (window_kind(situation), asking(situation), passed_seats(situation)) == (
        "stack",
        S2,
        (),
    )


# @spec STACK-036
@NOT_BUILT
def test_declaring_attackers_opens_a_window_asking_the_seat_after_the_active_seat() -> None:
    situation = three_seats(lambda b: b.with_battlefield("Grizzly Bears"))

    acted(
        situation,
        attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"], targets=2),
    )

    assert (window_kind(situation), asking(situation)) == ("attack", S2)


# @spec STACK-037
@NOT_BUILT
def test_entering_the_end_step_opens_a_window_asking_the_seat_after_the_active_seat() -> None:
    situation = three_seats(step=Step.MAIN2)

    advanced(situation)

    assert situation.game.step is Step.END
    assert (window_kind(situation), asking(situation)) == ("end", S2)


# @spec STACK-038
def test_no_other_step_opens_a_window() -> None:
    situation = two_seats()

    advanced(situation, to="main2")

    assert situation.game.window is None


# ------------------------------------------------------------------ the asking


# @spec STACK-039
@NOT_BUILT
def test_a_response_begins_the_asking_again_from_the_seat_after_the_responder() -> None:
    situation = three_seats(
        lambda b: b.with_hand("Grizzly Bears"), third=lambda b: b.with_hand("Lightning Bolt")
    )
    cast(situation, S1, "Grizzly Bears")
    passed(situation, S2)

    cast(situation, S3, "Lightning Bolt", delta=bolt_at(2))

    assert (asking(situation), passed_seats(situation)) == (S1, ())


# @spec STACK-040
@NOT_BUILT
def test_when_the_stack_empties_inside_an_attack_window_the_asking_begins_again() -> None:
    situation = three_seats(
        second=lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}),
        third=lambda b: b.with_window("attack", asking=1, passed=(3,)),
    )

    passed(situation, S1)

    assert situation.game.stack == []
    assert (window_kind(situation), asking(situation), passed_seats(situation)) == (
        "attack",
        S2,
        (),
    )


# @spec STACK-041, STACK-044
@NOT_BUILT
def test_an_attack_window_closes_once_every_other_seat_has_passed_and_the_active_seat_acts() -> (
    None
):
    situation = two_seats(
        lambda b: b.with_battlefield("Grizzly Bears", tapped=True),
        lambda b: b.with_window("attack", asking=2),
        step=Step.DECLARE_ATTACKERS,
    )

    passed(situation, S2)

    assert situation.game.window is None
    assert situation.game.step is Step.DECLARE_ATTACKERS
    assert situation.game.pending == []
    assert asked(situation)[:2] == ((S1,), "turn")


# @spec STACK-045
@NOT_BUILT
def test_when_the_end_window_closes_the_active_seat_continues_with_advance() -> None:
    situation = two_seats(second=lambda b: b.with_window("end", asking=2), step=Step.END)

    passed(situation, S2)

    assert situation.game.window is None
    assert asked(situation)[:2] == ((S1,), "turn")
    assert accepted(situation, S1, "advance")


# @spec STACK-084, TURN-061
@NOT_BUILT
def test_an_end_window_of_an_eliminated_active_seat_closes_once_the_stack_is_empty() -> None:
    situation = three_seats(
        third=lambda b: b.with_window("end", asking=3),
        step=Step.END,
        active=2,
    )

    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))

    assert situation.game.active == S3
    assert situation.game.window is None


# @spec STACK-084, TURN-061, TURN-037
@NOT_BUILT
def test_an_eliminated_active_seats_window_asks_about_items_but_does_not_begin_again() -> None:
    situation = three_seats(
        third=lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}).with_window(
            "end", asking=1
        ),
        step=Step.END,
        active=2,
    )
    acted(situation, end_game(situation.game, situation.deck, S2, result="loss"))
    assert situation.game.active == S2

    passed(situation, S1)

    assert situation.game.seat(S3).life == 41
    assert situation.game.active == S3


# @spec STACK-085, TURN-068, TURN-069
@NOT_BUILT
def test_an_end_window_every_other_seat_is_passed_on_automatically_closes_in_the_advance() -> None:
    situation = two_seats(step=Step.MAIN2, lands=False)

    result = advanced(situation, to="cleanup")

    assert situation.game.step is Step.CLEANUP
    assert [event.seat for event in events_named(result, "AutomaticPass")] == [S2]


# @spec TURN-056
@NOT_BUILT
def test_an_advance_stops_in_the_end_step_while_its_window_waits_on_a_seat() -> None:
    situation = two_seats(step=Step.MAIN2)

    result = advanced(situation, to="cleanup")

    assert situation.game.step is Step.END
    assert asking(situation) == S2
    (stopped,) = events_named(result, "AdvanceStopped")
    assert (stopped.reason.value, stopped.seat) == ("end_window", S2)


# @spec TURN-059
def test_a_goldfish_advance_through_the_end_step_does_not_stop_for_a_window() -> None:
    situation = a_game().in_step(Step.MAIN2).build()

    advanced(situation, to="cleanup")

    assert situation.game.step is Step.CLEANUP


# @spec STACK-077
def test_a_land_played_in_an_open_window_leaves_the_asking_as_it_was() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_hand("Forest").with_window("stack", asking=2),
    )
    window = situation.game.window

    cast(situation, S2, "Forest", override="a land played at instant speed")

    assert situation.game.window == window


# ------------------------------------------------------------------ waiting on choices


def bolt_that_asks_over_a_trick() -> Any:
    """S2's trick waits under S1's Bolt, which asks S2 to discard; S1 has only Sol Ring,
    untapped; S2 is asked about the Bolt."""
    builder: Any = a_game().in_step(Step.MAIN1, turn=5).with_battlefield("Sol Ring")
    builder = builder.and_an_opposing_seat().with_battlefield("Island").with_hand("Forest")
    builder = builder.with_ability_on_stack("a trick", delta={"life": 1})
    builder = builder.with_ability_on_stack(
        "a discard", delta={"ask": [{"seats": [2], "text": "discard a card"}]}, controller=1
    )
    return builder.with_window("stack", asking=2).build()


# @spec STACK-070
@NOT_BUILT
def test_while_a_pending_choice_waits_no_seat_is_asked_and_nothing_resolves() -> None:
    situation = bolt_that_asks_over_a_trick()

    result = passed(situation, S2)

    assert situation.game.pending[0].kind == "ask"
    assert stack_ids(situation) == ["s1"]
    assert situation.game.seat(S2).life == 40
    assert events_named(result, "AutomaticPass") == []


# @spec STACK-071
@NOT_BUILT
def test_once_the_choice_is_answered_the_asking_goes_on_judging_the_board_as_it_is_then() -> None:
    situation = bolt_that_asks_over_a_trick()
    passed(situation, S2)
    choice = situation.game.pending[0]

    result = acted(
        situation,
        choose(
            situation.game,
            situation.deck,
            S2,
            choice_id=choice.choice_id,
            delta={"tap": ["Sol Ring"], "discard": ["Forest"]},
        ),
    )

    assert [event.seat for event in events_named(result, "AutomaticPass")] == [S1]


# @spec STACK-083
@NOT_BUILT
def test_the_end_window_opens_on_entering_the_step_but_asks_only_after_reminders() -> None:
    situation = two_seats(
        second=lambda b: b.with_battlefield("Bloodchief Ascension"), step=Step.MAIN2
    )

    advanced(situation)

    assert window_kind(situation) == "end"
    assert asked(situation)[:2] == ((S2,), "trigger")


# @spec STACK-083, TURN-054
@NOT_BUILT
def test_the_end_window_asks_once_the_reminded_seat_has_answered_and_the_stack_is_empty() -> None:
    situation = two_seats(
        second=lambda b: b.with_battlefield("Bloodchief Ascension"), step=Step.MAIN2
    )
    advanced(situation)
    recorded(situation, S2, "Bloodchief Ascension", {"life": {"1": -2}})
    passed(situation, S1)

    assert situation.game.stack == []
    assert (window_kind(situation), asking(situation)) == ("end", S2)


# ------------------------------------------------------------------ automatic passes


# @spec STACK-046, STACK-047
@NOT_BUILT
def test_a_seat_with_no_untapped_permanents_is_passed_automatically() -> None:
    situation = three_seats(
        lambda b: b.with_hand("Grizzly Bears"),
        lambda b: b.with_battlefield("Forest", tapped=True),
        lambda b: b.with_battlefield("Island"),
        lands=False,
    )

    result = cast(situation, S1, "Grizzly Bears", override="paid by the test")

    assert [event.seat for event in events_named(result, "AutomaticPass")] == [S2]


# @spec STACK-046
@NOT_BUILT
def test_the_seat_after_an_automatic_pass_is_asked() -> None:
    situation = three_seats(
        lambda b: b.with_hand("Grizzly Bears"),
        lambda b: b,
        lambda b: b.with_battlefield("Island"),
        lands=False,
    )

    cast(situation, S1, "Grizzly Bears", override="paid by the test")

    assert asking(situation) == S3


# @spec STACK-048
@NOT_BUILT
def test_an_automatic_pass_is_shown_to_the_other_seats() -> None:
    situation = three_seats(
        lambda b: b.with_hand("Grizzly Bears"),
        lambda b: b,
        lambda b: b.with_battlefield("Island"),
        lands=False,
    )

    result = cast(situation, S1, "Grizzly Bears", override="paid by the test")

    shown = as_seen_by((result.summary, *result.events), S3)
    assert [type(event).__name__ for event in shown].count("AutomaticPass") == 1


# @spec STACK-049
@NOT_BUILT
def test_an_item_every_other_seat_is_passed_on_automatically_resolves_within_its_call() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"), lands=False)

    result = cast(situation, S1, "Grizzly Bears", override="paid by the test")

    assert situation.game.stack == []
    assert [event.item for event in events_named(result, "ItemResolved")] == ["s1"]


# ------------------------------------------------------------------ pass


# @spec STACK-002
def test_pass_in_a_goldfish_game_is_an_error() -> None:
    situation = a_game().build()

    assert refusal_kind(situation, S1, "pass") == "not_accepted_in_status"


# @spec STACK-050
@NOT_BUILT
def test_a_pass_records_the_seat_and_asks_the_next_seat() -> None:
    situation = three_seats(lambda b: b.with_hand("Grizzly Bears"))
    cast(situation, S1, "Grizzly Bears")

    passed(situation, S2)

    assert (asking(situation), passed_seats(situation)) == (S3, (S2,))


# @spec STACK-052, GAME-116
@pytest.mark.parametrize("tool", ["pass", "play", "effect"])
def test_a_seat_not_asked_may_not_pass_play_or_record_an_effect(tool: str) -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
    )

    assert refusal_kind(situation, S3, tool) == "not_your_call"


# @spec STACK-042, GAME-112, GAME-116
@NOT_BUILT
@pytest.mark.parametrize("tool", ["pass", "play", "effect"])
def test_the_seat_being_asked_is_the_seat_to_act_and_may_respond_or_pass(tool: str) -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
    )

    assert asked(situation)[:2] == ((S2,), "respond")
    assert accepted(situation, S2, tool)


# @spec STACK-042, GAME-117
@NOT_BUILT
@pytest.mark.parametrize("tool", ["play", "effect"])
def test_the_active_seat_may_not_play_while_another_seat_is_asked(tool: str) -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
    )

    assert refusal_kind(situation, S1, tool) == "not_your_call"


# @spec STACK-043, GAME-117
@NOT_BUILT
@pytest.mark.parametrize("tool", ["advance", "attack"])
def test_advance_and_attack_are_errors_while_the_stack_is_not_empty(tool: str) -> None:
    situation = two_seats(
        second=lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(1)).with_window(
            "stack", asking=1
        )
    )

    assert refusal_kind(situation, S1, tool) == "window_open"


# @spec STACK-043
@NOT_BUILT
@pytest.mark.parametrize("tool", ["advance", "attack"])
def test_advance_and_attack_are_errors_while_a_window_is_open_whichever_seat_calls(
    tool: str,
) -> None:
    situation = two_seats(second=lambda b: b.with_window("end", asking=2), step=Step.END)

    assert acting.may_call(situation.game, S1, tool) is not None
    assert acting.may_call(situation.game, S2, tool) is not None


# @spec STACK-053
@NOT_BUILT
def test_a_seat_owing_a_pending_choice_may_not_pass() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
    )
    a_pending_look(situation, S2)

    assert refusal_kind(situation, S2, "pass") == "answer_with_choose"


# @spec STACK-054, TURN-067
@NOT_BUILT
@pytest.mark.parametrize("reminded", [False, True], ids=["no reminder", "reminded"])
def test_the_active_seat_with_no_window_open_has_nothing_to_pass(reminded: bool) -> None:
    situation = two_seats(
        (lambda b: b.with_battlefield("Mystic Remora").with_reminder("Mystic Remora", Step.UPKEEP))
        if reminded
        else (lambda b: b),
        step=Step.UPKEEP,
    )

    assert asked(situation)[:2] == ((S1,), "turn")
    assert refusal_kind(situation, S1, "pass") == "nothing_to_pass"


# @spec STACK-057
@NOT_BUILT
def test_a_seat_asked_in_a_window_may_record_an_earlier_trigger() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_battlefield("Llanowar Elves").with_window("stack", asking=2),
    )

    recorded(situation, S2, "Llanowar Elves", {"draw": 1})

    assert stack_ids(situation) == ["s1", "s2"]


# @spec STACK-056
@NOT_BUILT
def test_combat_damage_opens_no_window_and_leaves_the_active_seat_to_act() -> None:
    situation = two_seats(lambda b: b.with_battlefield("Grizzly Bears"))
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    passed(situation, S2)

    advanced(situation, to="combat_damage")

    assert situation.game.step is Step.COMBAT_DAMAGE
    assert situation.game.window is None
    assert asked(situation)[:2] == ((S1,), "turn")


# ------------------------------------------------------------------ the seat to act


# @spec GAME-111
@NOT_BUILT
def test_a_seat_reminded_out_of_its_turn_acts_ahead_of_an_open_window() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
        lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.MAIN1),
    )

    assert asked(situation)[:2] == ((S3,), "trigger")


# @spec GAME-109
def test_a_pending_choice_comes_before_a_reminder_and_an_open_window() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
        lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.MAIN1),
    )
    a_pending_look(situation, S1)

    assert asked(situation) == ((S1,), "choice", "look")


# @spec TURN-044, CMBT-029
@NOT_BUILT
@pytest.mark.parametrize("tool", ["advance", "attack"])
def test_the_active_seat_may_not_move_on_while_another_seats_reminder_waits(tool: str) -> None:
    situation = two_seats(
        second=lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.MAIN1)
    )

    assert refusal_kind(situation, S1, tool) == "not_your_call"


# @spec GAME-148
@NOT_BUILT
@pytest.mark.parametrize("waiting", ["window", "reminder"])
def test_the_tested_seat_may_end_the_game_whatever_waits(waiting: str) -> None:
    situation = two_seats(
        (lambda b: b.with_spell_on_stack("Grizzly Bears")) if waiting == "window" else same,
        (lambda b: b.with_window("stack", asking=2))
        if waiting == "window"
        else (lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.MAIN1)),
    )
    assert asked(situation)[0] == (S2,)

    assert accepted(situation, S1, "end_game")


# @spec GAME-161
@NOT_BUILT
@pytest.mark.parametrize("waiting", ["window", "reminder"])
def test_a_seat_may_concede_while_the_game_waits_on_it(waiting: str) -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears") if waiting == "window" else b,
        (lambda b: b.with_window("stack", asking=2))
        if waiting == "window"
        else (lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.MAIN1)),
    )
    assert acting.seats_to_act(situation.game).seats == (S2,)  # type: ignore[union-attr]

    assert accepted(situation, S2, "end_game")


# ------------------------------------------------------------------ timing


# @spec PLAY-081
@NOT_BUILT
def test_a_land_played_by_a_seat_asked_out_of_its_turn_fails_the_timing_check() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_hand("Forest").with_window("stack", asking=2),
    )

    result = play(situation.game, situation.deck, S2, card="Forest")

    assert check_kinds(result) == ["land_timing"]


# @spec PLAY-081
@NOT_BUILT
def test_a_land_played_by_the_active_seat_with_the_stack_not_empty_fails_the_timing_check() -> None:
    situation = two_seats(
        lambda b: b.with_hand("Forest"),
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(1)).with_window(
            "stack", asking=1
        ),
    )

    result = play(situation.game, situation.deck, S1, card="Forest")

    assert check_kinds(result) == ["land_timing"]


# @spec PLAY-082
def test_a_land_is_played_at_once_entering_on_the_table_turn() -> None:
    situation = two_seats(lambda b: b.with_hand("Forest").with_library("Island"))
    forest = situation.game.hand_of(S1)[0]

    cast(situation, S1, "Forest", delta={"draw": 1})

    assert situation.game.instance(forest.id).entered_turn == 5
    assert situation.game.stack == []
    assert situation.names_in(Zone.HAND) == ["Island"]


# @spec PLAY-083
@NOT_BUILT
def test_a_sorcery_speed_spell_cast_out_of_the_casters_turn_fails_the_timing_check() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: (
            b.with_hand("Grizzly Bears", "Forest")
            .with_battlefield("Forest")
            .with_window("stack", asking=2)
        ),
    )

    result = play(situation.game, situation.deck, S2, card="Grizzly Bears")

    assert "spell_timing" in check_kinds(result)


# @spec PLAY-083
@NOT_BUILT
def test_a_sorcery_speed_spell_cast_in_the_casters_main_step_over_a_stack_fails_timing() -> None:
    situation = two_seats(
        lambda b: b.with_hand("Grizzly Bears"),
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(1)).with_window(
            "stack", asking=1
        ),
    )

    result = play(situation.game, situation.deck, S1, card="Grizzly Bears")

    assert check_kinds(result) == ["spell_timing"]


# @spec PLAY-083
@NOT_BUILT
def test_a_spell_with_flash_may_be_cast_out_of_the_casters_turn() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_hand("Brazen Flash").with_window("stack", asking=2),
    )

    cast(situation, S2, "Brazen Flash")

    assert stack_ids(situation) == ["s1", "s2"]


# @spec GAME-119
def test_a_pass_from_an_eliminated_seat_is_refused() -> None:
    situation = two_seats(second=lambda b: b.eliminated())

    assert refusal_kind(situation, S2, "pass") == "seat_eliminated"
