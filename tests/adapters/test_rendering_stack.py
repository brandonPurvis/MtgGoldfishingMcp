"""The text a seat reads about the stack and response windows: the status line's `Stack` and
`Act`, what a seat is asked, the order of event lines, digest lines of casts, passes and
resolutions, the state listing's stack and window, and the stops and attacks that wait."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.listing_lines import state_lines
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer, digest_line, status_line
from mtg_goldfishing.application.outcome import DigestElement, Outcome, Status
from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.events import Error, ErrorKind, Refused
from mtg_goldfishing.domain.game import acting
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.model import PendingChoice
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by, public_form
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.stack.passing import pass_
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted, cast
from tests.support.builders import Situation, a_game
from tests.support.tables import bolt_at, three_seats, two_seats

RENDERER = TextRenderer()


def line_of(situation: Situation, seat: SeatNumber) -> str:
    return status_line(summarize(situation.game, situation.deck, seat))


def response(tool: str, situation: Situation, seat: SeatNumber, result: Any) -> list[str]:
    """The response to `seat`'s call: its events as that seat may see them."""
    events = as_seen_by(result.events, seat)
    (summary,) = as_seen_by((result.summary,), seat)
    outcome = Outcome(Status.OK, summary, events, summarize(result.game, situation.deck, seat))
    return RENDERER.render(tool, outcome).response.splitlines()


def not_your_call(situation: Situation, seat: SeatNumber) -> str:
    asked = acting.seats_to_act(situation.game)
    error = Error(ErrorKind.NOT_YOUR_CALL, subject="pass", asked=asked)
    outcome = Outcome(
        Status.ERROR, Refused((error,), ()), (), summarize(situation.game, situation.deck, seat)
    )
    return RENDERER.render("pass", outcome).response.splitlines()[0]


def listing_of(situation: Situation, seat: SeatNumber) -> list[str]:
    listing: Any = list_state(situation.game, situation.deck, seat)
    return state_lines(listing)


def bears_asked_of_s2() -> Situation:
    return three_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears"),
        lambda b: b.with_window("stack", asking=2),
    )


# ------------------------------------------------------------------ the status line


# @spec TOOL-046
def test_the_status_line_shows_the_number_of_items_on_the_stack() -> None:
    situation = bears_asked_of_s2()

    assert " · Stack 1 · " in line_of(situation, S3)


# @spec TOOL-046
def test_the_status_line_shows_no_stack_while_the_stack_is_empty() -> None:
    assert " · Stack " not in line_of(two_seats(), S1)


# @spec TOOL-060, TOOL-047
def test_act_says_respond_for_the_seat_a_window_asks() -> None:
    situation = bears_asked_of_s2()

    assert line_of(situation, S2).endswith(f"Act you respond · #{situation.game.change}")
    assert " · Act S2 respond · " in line_of(situation, S3)


# @spec TOOL-060
def test_act_says_trigger_for_a_seat_reminded_out_of_its_turn() -> None:
    situation = two_seats(
        second=lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.UPKEEP),
        step=Step.UPKEEP,
    )

    assert " · Act S2 trigger · " in line_of(situation, S1)


# @spec TOOL-060
def test_act_names_the_kind_of_a_resolve_choice() -> None:
    situation = two_seats(lambda b: b.with_spell_on_stack("Grizzly Bears", disturbed=True))
    situation.game.pending.append(PendingChoice("x1", S1, "Grizzly Bears", "resolve", [], None))

    assert " · Act S1 resolve · " in line_of(situation, S2)


# @spec TOOL-060
def test_act_says_turn_for_the_active_seat_when_nothing_else_waits() -> None:
    assert " · Act you turn · " in line_of(two_seats(step=Step.END), S1)


# ------------------------------------------------------------------ what a seat is asked


# @spec TOOL-061, TOOL-040
def test_the_seat_asked_about_an_item_is_told_its_id_source_and_controller() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    result = cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))
    after = acting.seats_to_act(result.game)
    assert after is not None

    outcome = Outcome(
        Status.OK, result.summary, (), summarize(result.game, situation.deck, S2), seat=S2
    )
    lines = RENDERER.render("wait", outcome).response.splitlines()

    assert lines[1] == "You are asked to respond to s1: Lightning Bolt from S1."


# @spec TOOL-061
@pytest.mark.parametrize(
    ("kind", "words"),
    [("attack", "respond to the attack"), ("end", "respond in the end step")],
)
def test_a_window_with_no_item_asks_a_seat_to_respond_to_the_attack_or_in_the_end_step(
    kind: str, words: str
) -> None:
    situation = two_seats(second=lambda b: b.with_window(kind, asking=2), step=Step.END)

    assert not_your_call(situation, S1) == (
        f"ERROR Not your seat's call: S2 is asked to {words}."
        " Call wait to be told when it is yours."
    )


# @spec TOOL-061
def test_an_item_asked_about_is_named_by_its_id_in_an_error() -> None:
    assert "S2 is asked to respond to s1." in not_your_call(bears_asked_of_s2(), S3)


# @spec TOOL-061
def test_a_reminded_seat_is_asked_to_record_or_pass_its_trigger() -> None:
    situation = two_seats(
        second=lambda b: b.with_battlefield("Black Vise").with_reminder("Black Vise", Step.UPKEEP),
        step=Step.UPKEEP,
    )

    assert "S2 is asked to record or pass the upkeep trigger of Black Vise." in not_your_call(
        situation, S1
    )


# ------------------------------------------------------------------ event lines


# @spec TOOL-040, STACK-047
def test_stack_lines_follow_the_other_event_lines_in_their_order() -> None:
    situation = two_seats(
        lambda b: b.with_hand("Lightning Bolt"),
        lambda b: b.with_life(3),
        lands=False,
    )
    result = cast(situation, S1, "Lightning Bolt", delta=bolt_at(2), override="paid by the test")

    lines = response("play", situation, S1, result)

    def at(words: str) -> int:
        return next(i for i, line in enumerate(lines) if words in line)

    assert at("Put s1 on the stack: Lightning Bolt from S1.") < at(
        "S2 passed automatically on s1: no untapped permanents."
    )
    assert at("passed automatically") < at("s1 resolved: Lightning Bolt from S1.")
    assert at("s1 resolved") < at("S2 is eliminated")
    assert at("S2 is eliminated") < at("Notice:")


# @spec TOOL-040
def test_a_countered_item_is_said_to_be_countered() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_hand("Counterspell").with_window("stack", asking=2),
    )
    cast(situation, S2, "Counterspell", delta={"counter": ["s1"]})

    result = acted(situation, pass_(situation.game, situation.deck, S1))

    assert "s1 was countered: Lightning Bolt from S1." in response("pass", situation, S1, result)


# ------------------------------------------------------------------ digest lines


# @spec TOOL-036, TOOL-037
def test_a_digest_line_tells_of_a_pass_and_the_resolution_it_caused() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))
    result = acted(situation, pass_(situation.game, situation.deck, S2))

    line = digest_line(DigestElement(S2, 2, public_form((result.summary, *result.events))))

    assert line.startswith("S2 #2: S2 passed on s1; s1 resolved: Lightning Bolt from S1")


# @spec TOOL-036
def test_a_digest_line_tells_of_a_cast_put_on_the_stack() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    result = cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))

    line = digest_line(DigestElement(S1, 1, public_form((result.summary, *result.events))))

    assert "Put s1 on the stack: Lightning Bolt from S1" in line


# ------------------------------------------------------------------ the state listing


# @spec GAME-122
def test_the_state_lists_the_stack_top_first_and_the_window_with_the_seat_asked() -> None:
    situation = three_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_spell_on_stack("Counterspell", delta={"counter": ["s1"]}),
        lambda b: b.with_window("stack", asking=3),
    )

    lines = listing_of(situation, S1)

    assert "Stack (2): s2 Counterspell from S2; s1 Lightning Bolt from S1" in lines
    assert "Response window (stack): asking S3" in lines


# @spec GAME-122
def test_the_state_lists_each_seats_life_hand_library_and_whether_it_is_out() -> None:
    situation = two_seats(second=lambda b: b.eliminated(), lands=False)

    lines = listing_of(situation, S1)

    assert "S2 · Life 40 · Hand 0 · Library 0 · Out" in lines


# @spec GAME-123
def test_a_contested_listing_marks_a_trigger_on_opponents_turns_only() -> None:
    situation = two_seats(second=lambda b: b.with_battlefield("Black Vise", "Sulfuric Vortex"))

    lines = listing_of(situation, S1)

    assert any(line.endswith("Black Vise: trigger in upkeep (opp)") for line in lines)
    assert any(line.endswith("Sulfuric Vortex: trigger in upkeep") for line in lines)


# @spec GAME-030
def test_a_goldfish_listing_leaves_out_a_trigger_on_opponents_turns_only() -> None:
    situation = a_game().with_battlefield("Black Vise", "Mystic Remora").build()

    lines = listing_of(situation, S1)

    assert any(line.endswith(" Black Vise") for line in lines)
    assert any(line.endswith("Mystic Remora: trigger in upkeep") for line in lines)


# ------------------------------------------------------------------ stops


# @spec TURN-057
def test_an_advance_stopped_for_the_end_window_says_who_is_asked() -> None:
    situation = two_seats(step=Step.MAIN2)
    result = acted(situation, advance(situation.game, situation.deck, S1, to="cleanup"))

    lines = response("advance", situation, S1, result)

    assert any(
        line.startswith("Stopped at end: the other seats are being asked whether they respond;")
        and "S2 is asked now" in line
        for line in lines
    )


# @spec CMBT-078
def test_an_attack_stopped_for_another_seats_reminder_says_it_was_not_declared() -> None:
    situation = two_seats(
        lambda b: b.with_battlefield("Grizzly Bears"),
        lambda b: b.with_battlefield("Banner of Each Combat"),
    )
    result = acted(
        situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"])
    )

    lines = response("attack", situation, S1, result)

    assert lines[0].startswith("OK Attack not declared: stopped at begin_combat")
    assert "Send attack again" in lines[0]
    assert "after" in lines[0]
