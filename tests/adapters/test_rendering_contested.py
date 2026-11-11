"""The text a seat of a contested game reads: its status line, its errors, its state listing,
the start of a contested game, and the turn passing between seats."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.listing_lines import state_lines
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer, status_line
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.deck.model import DeckCard, DeckEntry, LoadedDeck
from mtg_goldfishing.domain.events import Error, Refused
from mtg_goldfishing.domain.game import acting, creation
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.model import GameResult, GameStatus, Result, Zone
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import GameBuilder, Situation, a_game
from tests.support.library import LIBRARY

RENDERER = TextRenderer()
S1, S2, S3, S4 = SeatNumber(1), SeatNumber(2), SeatNumber(3), SeatNumber(4)
ATRAXA = "Atraxa, Praetors' Voice"
KENRITH = "Kenrith, the Returned King"
THRASIOS = "Thrasios, Triton Hero"
TYMNA = "Tymna the Weaver"


def line_of(situation: Situation, seat: SeatNumber) -> str:
    return status_line(summarize(situation.game, situation.deck, seat))


def line_asked_for(situation: Situation, seat: SeatNumber, seconds: int) -> str:
    """The status line of a summary holding how long the seats to act have been asked."""
    renew: Any = replace
    summary = summarize(situation.game, situation.deck, seat)
    assert summary.table is not None
    return status_line(renew(summary, table=renew(summary.table, time_asked=seconds)))


def response(tool: str, situation: Situation, seat: SeatNumber, result: Any) -> list[str]:
    """The response to `seat`'s call: its events as that seat may see them."""
    events = as_seen_by(result.events, seat)
    (summary,) = as_seen_by((result.summary,), seat)
    outcome = Outcome(Status.OK, summary, events, summarize(result.game, situation.deck, seat))
    return RENDERER.render(tool, outcome).response.splitlines()


def refused(situation: Situation, seat: SeatNumber, error: Error) -> list[str]:
    outcome = Outcome(
        Status.ERROR, Refused((error,), ()), (), summarize(situation.game, situation.deck, seat)
    )
    return RENDERER.render("advance", outcome).response.splitlines()


def two_seats(**options: Any) -> Any:
    """Seat 1's turn 2 (table turn 3, round 2) in main1, unless told otherwise."""
    builder: Any = (
        a_game()
        .in_step(options.get("step", Step.MAIN1), turn=3)
        .in_round(2)
        .in_turn_of(options.get("active", 1))
        .with_turns_taken(2)
        .with_commander(ATRAXA)
        .with_hand(*options.get("hand", ("Island",)))
        .with_battlefield("Forest")
        .with_library("Plains", "Plains")
    )
    return builder.and_an_opposing_seat().with_turns_taken(1).with_commander(KENRITH)


def four_seats() -> GameBuilder:
    builder: Any = a_game().with_commander(ATRAXA).with_library("Plains")
    builder = builder.and_an_opposing_seat().with_life(31).with_library("Swamp")
    builder = builder.and_an_opposing_seat().with_commander(KENRITH).with_library("Island")
    return builder.and_an_opposing_seat().eliminated().with_library("Forest")


# ------------------------------------------------------------------ the status line


# @spec TOOL-041
def test_the_status_line_of_a_started_contested_game_as_the_calling_seat_sees_it() -> None:
    situation = two_seats().with_life(35).build()
    assert line_of(situation, S1) == (
        "T2 main1 (S1) · You S1 · Hand 1 · Lands 1 (1 untapped) · Pool {} · Life 40"
        " · S2 35 · Cmdr 0 · Cmdr taken 0 · Tax 0 · Act you turn · #0"
    )


# @spec TOOL-041, TOOL-090
def test_the_status_line_of_a_seat_not_to_act_ends_act_with_the_time_asked() -> None:
    situation = two_seats(active=2).with_life(35).build()
    assert line_asked_for(situation, S1, 240) == (
        "T2 main1 (S2) · You S1 · Hand 1 · Lands 1 (1 untapped) · Pool {} · Life 40"
        " · S2 35 · Cmdr 0 · Cmdr taken 0 · Tax 0 · Act S2 turn (4 min) · #0"
    )


# @spec TOOL-042
def test_the_turn_shown_is_the_calling_seat_s_own_and_the_active_seat_is_named() -> None:
    situation = two_seats().build()
    assert line_of(situation, S2).startswith("T1 main1 (S1) · You S2 · ")


# @spec TOOL-043
def test_the_status_line_gives_the_calling_seat_s_number() -> None:
    assert " · You S3 · " in line_of(four_seats().build(), S3)


# @spec TOOL-044
def test_every_other_seat_s_life_is_shown_in_seat_order_with_out_for_an_eliminated_seat() -> None:
    assert " · Life 40 · S1 40 · S2 31 · S4 out · " in line_of(four_seats().build(), S3)


# @spec TOOL-045
def test_commander_damage_is_shown_to_each_other_seat_in_the_order_of_the_life_groups() -> None:
    builder: Any = (
        a_game()
        .with_commander(ATRAXA)
        .with_commander_damage(ATRAXA, 2, 7)
        .with_commander_damage(ATRAXA, 4, 14)
    )
    builder = builder.and_an_opposing_seat().and_an_opposing_seat().eliminated()
    line = line_of(builder.and_an_opposing_seat().build(), S1)
    assert " · S2 40 · S3 out · S4 40 · Cmdr 7/0/14 · " in line


# @spec TOOL-045, TOOL-058
def test_two_commanders_show_a_group_each_in_name_order_for_damage_and_tax() -> None:
    builder: Any = (
        a_game()
        .with_commander(TYMNA, THRASIOS)
        .with_commander_damage(TYMNA, 2, 5)
        .with_commander_damage(THRASIOS, 2, 3)
    )
    situation = builder.and_an_opposing_seat().build()
    thrasios = situation.named(THRASIOS)
    situation.game.seat(S1).commander_casts[thrasios.id] = 1
    assert " · Cmdr 3|5 · Cmdr taken 0 · Tax 2|0 · " in line_of(situation, S1)


# @spec TOOL-093
def test_commander_damage_taken_is_shown_from_each_other_seat_in_the_order_of_the_life_groups() -> (
    None
):
    builder: Any = a_game().with_commander(ATRAXA)
    builder = builder.and_an_opposing_seat().with_commander(KENRITH)
    builder = builder.with_commander_damage(KENRITH, 1, 3)
    builder = builder.and_an_opposing_seat().eliminated().with_commander(ATRAXA)
    builder = builder.with_commander_damage(ATRAXA, 1, 9)
    builder = builder.and_an_opposing_seat().with_commander(KENRITH)
    line = line_of(builder.build(), S1)
    assert " · S2 40 · S3 out · S4 40 · Cmdr 0/0/0 · Cmdr taken 3/9/0 · Tax 0 · " in line


# @spec TOOL-093
def test_a_seat_with_two_commanders_shows_a_group_of_two_in_its_commanders_name_order() -> None:
    builder: Any = a_game().with_commander(ATRAXA)
    builder = builder.and_an_opposing_seat().with_commander(KENRITH)
    builder = builder.with_commander_damage(KENRITH, 1, 3)
    builder = builder.and_an_opposing_seat().with_commander(TYMNA, THRASIOS)
    builder = builder.with_commander_damage(TYMNA, 1, 9).with_commander_damage(THRASIOS, 1, 12)
    assert " · Cmdr taken 3/12|9 · " in line_of(builder.build(), S1)


# @spec TOOL-093
def test_damage_taken_from_a_commander_counts_under_the_seat_whose_deck_it_is() -> None:
    builder: Any = a_game().with_commander(ATRAXA).with_commander_damage(ATRAXA, 2, 6)
    builder = builder.and_an_opposing_seat().with_commander(KENRITH)
    builder = builder.and_an_opposing_seat().with_commander(KENRITH, zone=Zone.BATTLEFIELD)
    builder = builder.controlled_by(KENRITH, 2).with_commander_damage(KENRITH, 1, 5)
    assert " · Cmdr taken 0/5 · " in line_of(builder.build(), S1)


# @spec TOOL-047
def test_act_names_the_seat_to_act_as_you_or_by_seat_number_with_what_it_is_asked() -> None:
    situation = two_seats(active=2).build()
    assert line_of(situation, S1).endswith(" · Act S2 turn · #0")
    assert line_of(situation, S2).endswith(" · Act you turn · #0")


# @spec TOOL-090
def test_the_calling_seat_to_act_is_shown_no_time_asked() -> None:
    situation = two_seats(active=2).build()
    assert line_asked_for(situation, S2, 240).endswith(" · Act you turn · #0")


# @spec TOOL-090
def test_a_summary_holding_no_time_asked_shows_none_on_act() -> None:
    situation = two_seats(active=2).build()
    assert line_of(situation, S1).endswith(" · Act S2 turn · #0")


# @spec TOOL-091
@pytest.mark.parametrize(
    ("seconds", "shown"),
    [(0, "0 s"), (45, "45 s"), (59, "59 s"), (60, "1 min"), (299, "4 min"), (4500, "75 min")],
)
def test_a_time_asked_is_whole_seconds_under_a_minute_and_whole_minutes_after(
    seconds: int, shown: str
) -> None:
    situation = two_seats(active=2).build()
    assert line_asked_for(situation, S1, seconds).endswith(f" · Act S2 turn ({shown}) · #0")


# @spec TOOL-059
def test_a_pending_choice_is_shown_by_act_and_never_as_choice_pending() -> None:
    situation = two_seats(active=2).with_library("Swamp", "Swamp").build()
    looked: Any = effect(
        situation.game,
        situation.deck,
        S2,
        source="a look",
        delta={"look": {"n": 1, "rest": "library_bottom"}},
        immediate=True,
    )
    situation.game = looked.game
    assert line_of(situation, S2).endswith(" · Act you look · #0")
    assert line_of(situation, S1).endswith(" · Act S2 look · #0")


# @spec TOOL-048
def test_during_mulligans_the_line_names_every_seat_still_to_keep() -> None:
    builder: Any = a_game().in_mulligan().with_hand("Forest")
    builder = builder.and_an_opposing_seat().with_hand("Island").having_kept()
    situation = builder.and_an_opposing_seat().with_hand("Swamp", "Swamp").build()
    situation.game.seat(S1).mulligans = 1
    assert line_of(situation, S1) == "Mulligan 1 · Hand 1 · Act you S3 · #0"
    assert line_of(situation, S2) == "Mulligan 0 · Hand 1 · Act S1 S3 · #0"
    assert line_of(situation, S3) == "Mulligan 0 · Hand 2 · Act S1 you · #0"


# @spec TOOL-092
def test_during_mulligans_a_seat_that_has_kept_reads_how_long_the_others_have_been_asked() -> None:
    builder: Any = a_game().in_mulligan().with_hand("Forest")
    builder = builder.and_an_opposing_seat().with_hand("Island").having_kept()
    situation = builder.and_an_opposing_seat().with_hand("Swamp", "Swamp").build()
    assert line_asked_for(situation, S2, 120) == "Mulligan 0 · Hand 1 · Act S1 S3 (2 min) · #0"


# @spec TOOL-049
def test_an_eliminated_calling_seat_s_line_begins_with_out() -> None:
    builder: Any = a_game().with_library("Plains")
    situation = builder.and_an_opposing_seat().eliminated().build()
    assert line_of(situation, S2).startswith("Out · T0 main1 (S1) · You S2 · ")


# @spec TOOL-049, TOOL-062
def test_an_ended_game_s_line_puts_ended_before_out() -> None:
    builder: Any = a_game().with_library("Plains")
    situation = builder.and_an_opposing_seat().eliminated().build()
    situation.game.status = GameStatus.ENDED
    situation.game.result = Result(GameResult.WIN, "")
    assert line_of(situation, S2).startswith("Ended (win) · Out · T0 main1 (S1) · You S2 · ")


# @spec TOOL-062
def test_an_ended_contested_game_s_line_has_no_act() -> None:
    situation = two_seats().build()
    situation.game.status = GameStatus.ENDED
    situation.game.result = Result(GameResult.WIN, "")
    assert line_of(situation, S1) == (
        "Ended (win) · T2 main1 (S1) · You S1 · Hand 1 · Lands 1 (1 untapped) · Pool {}"
        " · Life 40 · S2 40 · Cmdr 0 · Cmdr taken 0 · Tax 0 · #0"
    )


# @spec TOOL-062
def test_a_contested_game_ended_during_mulligans_shows_the_mulligan_line_without_act() -> None:
    builder: Any = a_game().in_mulligan().with_hand("Forest")
    situation = builder.and_an_opposing_seat().with_hand("Island").build()
    situation.game.status = GameStatus.ENDED
    situation.game.result = Result(GameResult.STALLED, "")
    assert line_of(situation, S2) == "Ended (stalled) · Mulligan 0 · Hand 1 · #0"


# ------------------------------------------------------------------ calls out of turn


# @spec TOOL-050
def test_a_call_from_a_seat_not_to_act_names_the_seat_to_act_and_suggests_wait() -> None:
    situation = two_seats().build()
    error: Any = acting.may_call(situation.game, S2, "advance")
    assert refused(situation, S2, error)[0] == (
        "ERROR Not your seat's call: S1 is asked to take its turn."
        " Call wait to be told when it is yours."
    )


# @spec TOOL-050
def test_during_mulligans_the_error_names_every_seat_still_to_keep() -> None:
    builder: Any = a_game().in_mulligan().with_hand("Forest").having_kept()
    builder = builder.and_an_opposing_seat().with_hand("Island")
    situation = builder.and_an_opposing_seat().with_hand("Swamp").build()
    error: Any = acting.may_call(situation.game, S1, "mulligan")
    assert refused(situation, S1, error)[0] == (
        "ERROR Not your seat's call: S2 and S3 are asked to keep or mulligan."
        " Call wait to be told when it is yours."
    )


# @spec TOOL-050
def test_a_pending_choice_is_named_by_its_kind_in_the_error() -> None:
    situation = two_seats().build()
    looked: Any = effect(
        situation.game,
        situation.deck,
        S1,
        source="a look",
        delta={"look": {"n": 1, "rest": "library_bottom"}},
    )
    situation.game = looked.game
    error: Any = acting.may_call(situation.game, S2, "choose")
    assert refused(situation, S2, error)[0].startswith(
        "ERROR Not your seat's call: S1 is asked to answer the look choice."
    )


# @spec TOOL-040
def test_the_first_event_line_says_what_the_calling_seat_is_now_asked_to_do() -> None:
    situation = two_seats(hand=("Island", "Forest")).build()
    result: Any = play(situation.game, situation.deck, S1, card="Forest")
    lines = response("play", situation, S1, result)
    assert lines[1] == "You are asked to take your turn."


# @spec TOOL-040
def test_a_seat_that_is_not_to_act_is_told_nothing_it_is_asked() -> None:
    situation = two_seats(active=2).build()
    outcome = Outcome(Status.OK, Refused((), ()), (), summarize(situation.game, situation.deck, S1))
    lines = RENDERER.render("get_state", outcome).response.splitlines()
    assert not any(line.startswith("You are asked") for line in lines)
    assert " · Act S2 turn · " in lines[-1]


# ------------------------------------------------------------------ the state listing


def a_table_of_two() -> Situation:
    builder: Any = (
        a_game()
        .with_commander(ATRAXA)
        .with_hand("Counterspell", "Ancestral Vision")
        .with_battlefield("Island")
        .with_graveyard("Ponder")
        .with_library("Plains", "Plains", "Plains")
    )
    return (
        builder.and_an_opposing_seat()
        .with_commander(KENRITH)
        .with_hand("Shivan Dragon")
        .with_battlefield("Mountain", "Llanowar Elves")
        .controlled_by("Llanowar Elves", 1)
        .with_library("Swamp")
        .with_life(31)
        .build()
    )


def listing_lines(situation: Situation, seat: SeatNumber, detail: str = "summary") -> list[str]:
    listing: Any = list_state(situation.game, situation.deck, seat, detail)
    return state_lines(listing)


# @spec TOOL-051, GAME-121
def test_the_listing_gives_the_calling_seat_s_hand_then_each_seat_in_turn_order() -> None:
    lines = listing_lines(a_table_of_two(), S2)
    assert lines[0] == "Hand (1): Shivan Dragon"
    assert lines.index("S1 · Life 40 · Hand 2 · Library 3") < lines.index(
        "S2 (you) · Life 31 · Hand 1 · Library 1"
    )


# @spec TOOL-051
def test_the_listing_shows_no_card_of_another_seat_s_hand_and_none_of_any_library() -> None:
    text = "\n".join(listing_lines(a_table_of_two(), S2))
    assert "Counterspell" not in text
    assert "Ancestral Vision" not in text
    assert "Plains" not in text
    assert "Swamp" not in text


# @spec TOOL-066
def test_a_permanent_its_controller_does_not_own_is_marked_with_its_owner() -> None:
    lines = listing_lines(a_table_of_two(), S1)
    first = lines.index("S1 (you) · Life 40 · Hand 2 · Library 3")
    second = lines.index("S2 · Life 31 · Hand 1 · Library 1")
    on_first = lines[first:second]
    elves = next(line for line in on_first if "Llanowar Elves" in line)
    island = next(line for line in on_first if "Island" in line)
    assert elves.startswith("  c12 Llanowar Elves (owner S2)")
    assert "(owner" not in island


# ------------------------------------------------------------------ starting a contested game


def a_deck(deck_id: str, commander: str) -> LoadedDeck:
    return LoadedDeck(
        deck_id=deck_id,
        commanders=(commander,),
        entries=(DeckEntry("Forest", 30),),
        cards=(DeckCard(*LIBRARY["Forest"]), DeckCard(*LIBRARY[commander])),
    )


# @spec GAME-074, GAME-075, GAME-079
def test_a_new_contested_game_lists_its_seats_in_turn_order_and_shows_no_hand() -> None:
    tested, other = a_deck("dtested", ATRAXA), a_deck("dother", KENRITH)
    result: Any = creation.new_game(
        tested,
        deck_id="dtested",
        game_id="gabcdefghij",
        seed=3,
        opposing=[creation.OpposingDeck("dother", other, "gopposing01")],
        position=2,
        starting_life=[40, 30],
    )
    assert isinstance(result, Applied), result
    outcome = Outcome(Status.OK, result.summary, result.events, summarize(result.game, tested, S2))
    assert RENDERER.render("new_game", outcome).response.splitlines() == [
        "OK Started contested game gabcdefghij with seed 3. Seats in turn order:",
        "S1 gopposing01: deck dother, life 30.",
        "S2 gabcdefghij: deck dtested, life 40, the tested seat.",
        "Each seat passes its own seat id as game_id.",
        "Mulligan 0 · Hand 7 · Act S1 you · #0",
    ]


# ------------------------------------------------------------------ the turn passing


# @spec TURN-042
def test_the_turn_passing_is_shown_with_the_new_seat_and_its_turn_and_its_draw_counted() -> None:
    builder: Any = a_game().in_step(Step.CLEANUP, turn=3).in_round(2).with_turns_taken(2)
    situation = builder.and_an_opposing_seat().with_turns_taken(1).with_library("Swamp").build()
    result: Any = advance(situation.game, situation.deck, S1)
    lines = response("advance", situation, S1, result)
    assert lines[0] == "OK S2 T2 untap → upkeep → draw → main1"
    assert "S2 drew a card." in lines
    assert not any("Swamp" in line for line in lines)
