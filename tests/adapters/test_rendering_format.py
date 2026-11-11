"""The shape of every text response: status and summary, event lines, status line."""

from __future__ import annotations

import json

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    AlreadyApplied,
    AssumptionKind,
    AssumptionMade,
    AttackerDamage,
    CardMoved,
    CardsDrawn,
    CardsRevealed,
    CastTriggerApplied,
    CheckKind,
    ChecksOverridden,
    CombatDamageDealt,
    CostPaid,
    DeckLoaded,
    EffectRecorded,
    EnteredStep,
    Error,
    ErrorKind,
    ExpectationMismatched,
    FailedCheck,
    LogExported,
    NoticeKind,
    NoticeRaised,
    Refused,
    ReminderIssued,
    RevealedCard,
    StateListed,
    StepsEntered,
    StopReason,
    TokensCreated,
)
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.model import GameStatus
from mtg_goldfishing.domain.game.summary import CommanderStatus
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import TESTED, a_game
from tests.support.outcomes import ATRAXA, a_summary, outcome_of

RENDERER = TextRenderer()


def lines(tool: str, outcome: Outcome) -> list[str]:
    return RENDERER.render(tool, outcome).response.splitlines()


def a_refusal(*checks: FailedCheck, errors: tuple[Error, ...] = ()) -> Outcome:
    status = Status.ERROR if errors else Status.REJECTED
    return Outcome(status, Refused(errors, checks), game=a_summary())


COST_CHECK = FailedCheck(
    CheckKind.COST_NOT_PAYABLE, "Shivan Dragon", cost=ManaString.parse("{6}{R}"), number=5
)


# ------------------------------------------------------------------------------ the shape


# @spec TOOL-014
def test_a_response_is_a_summary_line_then_event_lines_then_the_status_line() -> None:
    situation = a_game().with_commander(ATRAXA).with_hand("Forest").with_library("Island").build()
    result = effect(situation.game, situation.deck, TESTED, source="Brainstorm", delta={"draw": 1})
    assert lines("effect", outcome_of(situation, result)) == [
        "OK Effect from Brainstorm recorded.",
        "Drew Island.",
        "T3 main1 · Hand 2 · Lands 0 (0 untapped) · Pool {} · Life 40 · Dmg 0/120"
        " · Cmdr 0/0/0 · Tax 0 · #0",
    ]


# @spec TOOL-015
@pytest.mark.parametrize("status", list(Status))
def test_the_first_word_of_a_response_is_its_status(status: Status) -> None:
    outcome = Outcome(status, EffectRecorded("Sol Ring"), game=a_summary())
    assert lines("effect", outcome)[0].split(" ")[0] == status.value


# ------------------------------------------------------------------------ the status line


# @spec TOOL-017
def test_the_status_line_shows_turn_step_hand_lands_pool_life_damage_commander_tax_and_change() -> (
    None
):
    outcome = Outcome(Status.OK, EffectRecorded("Sol Ring"), game=a_summary(pool="{G}{G}*"))
    assert lines("effect", outcome)[-1] == (
        "T6 main1 · Hand 4 · Lands 6 (5 untapped) · Pool {G}{G}* · Life 40 · Dmg 22/120"
        " · Cmdr 7/0/0 · Tax 2 · #41"
    )


# @spec TOOL-017
def test_the_status_line_shows_damage_to_each_opponent_and_an_empty_pool_as_braces() -> None:
    commanders = (CommanderStatus(ATRAXA, (3, 0, 5), 0),)
    outcome = Outcome(Status.OK, EffectRecorded("x"), game=a_summary(commanders=commanders))
    assert " · Pool {} · " in lines("effect", outcome)[-1]
    assert " · Cmdr 3/0/5 · " in lines("effect", outcome)[-1]


# @spec TOOL-018
def test_two_commanders_show_one_damage_and_tax_group_each_in_name_order() -> None:
    commanders = (
        CommanderStatus("Tymna the Weaver", (0, 3, 0), 0),
        CommanderStatus("Kraum, Ludevic's Opus", (4, 0, 0), 2),
    )
    outcome = Outcome(Status.OK, EffectRecorded("Sol Ring"), game=a_summary(commanders=commanders))
    assert " · Cmdr 4/0/0|0/3/0 · Tax 2|0 · " in lines("effect", outcome)[-1]


# @spec TOOL-019
def test_during_mulligans_the_status_line_shows_the_mulligan_count_hand_and_change() -> None:
    summary = a_summary(
        status=GameStatus.MULLIGAN, turn=0, step=None, hand=7, mulligans=2, change=3
    )
    outcome = Outcome(Status.OK, EffectRecorded("x"), game=summary)
    assert lines("mulligan", outcome)[-1] == "Mulligan 2 · Hand 7 · #3"


# @spec TOOL-020
def test_while_a_choice_is_pending_the_status_line_ends_with_choice_pending() -> None:
    outcome = Outcome(
        Status.CHOICE, EffectRecorded("Ponder"), game=a_summary(status=GameStatus.PENDING_CHOICE)
    )
    assert lines("effect", outcome)[-1].endswith(" · #41 · CHOICE pending")


# @spec TOOL-021
def test_for_an_ended_game_the_status_line_begins_with_the_result() -> None:
    summary = a_summary(status=GameStatus.ENDED, result="win")
    outcome = Outcome(Status.OK, StateListed("summary"), game=summary, payload=None)
    assert lines("end_game", outcome)[-1].startswith("Ended (win) · T6 main1 · Hand 4 · ")


# @spec TOOL-019, TOOL-021
def test_a_game_ended_during_mulligans_shows_the_mulligan_status_line() -> None:
    summary = a_summary(
        status=GameStatus.ENDED, result="loss", turn=0, step=None, hand=7, mulligans=0, change=2
    )
    outcome = Outcome(Status.OK, StateListed("summary"), game=summary, payload=None)
    assert lines("end_game", outcome)[-1] == "Ended (loss) · Mulligan 0 · Hand 7 · #2"


# @spec TOOL-022
def test_a_response_about_no_existing_game_has_no_status_line() -> None:
    outcome = Outcome(Status.ERROR, Refused((Error(ErrorKind.UNKNOWN_GAME, "gnope"),), ()))
    assert lines("play", outcome) == [
        "ERROR No game with id gnope. Check the game id, or start a game with new_game."
    ]


# @spec TOOL-022
def test_a_load_deck_response_has_no_status_line() -> None:
    outcome = Outcome(Status.OK, DeckLoaded("d3f9a01c2e", 100, (ATRAXA,)))
    assert lines("load_deck", outcome) == [
        "OK Loaded deck d3f9a01c2e: 100 cards, commander Atraxa, Praetors' Voice."
    ]


# --------------------------------------------------------------------------- event order


# @spec TOOL-016
def test_event_lines_appear_in_the_fixed_order_whatever_order_they_happened_in() -> None:
    events = (
        NoticeRaised(NoticeKind.DAMAGE),
        ExpectationMismatched("untapped_lands", "1", "2"),
        AdvanceStopped(StopReason.REMINDER, Step.UPKEEP, Step.MAIN1),
        ReminderIssued(Step.UPKEEP, (("Phyrexian Arena", 1),)),
        AssumptionMade(AssumptionKind.X_IS_ZERO, "Fireball"),
        CombatDamageDealt((AttackerDamage("Grizzly Bears", 2),), 24, ()),
        CardsRevealed("ch1", "look", (RevealedCard("c9", "Island"),)),
        CardsDrawn(("Island",)),
        TokensCreated("Treasure", 1),
        CardMoved("Forest", "graveyard", "hand"),
        CastTriggerApplied("Thousand-Year Storm", {"draw": 1}),
        CostPaid(ManaString.parse("{G}"), tapped=("Forest",)),
        StepsEntered((EnteredStep(7, Step.UNTAP),)),
    )
    outcome = Outcome(Status.OK, EffectRecorded("x"), events, game=a_summary())
    assert [line.split(" ")[0] for line in lines("effect", outcome)[1:-1]] == [
        "T7",  # steps entered
        "Paid",  # payment
        "Cast",  # cast triggers applied
        "Drew",  # moves, tokens and draws keep the order they happened in
        "Created",
        "Moved",
        "Choice",  # cards revealed
        "Grizzly",  # combat damage per attacker, then the totals
        "Damage",
        "Assumed:",
        "Reminder",
        "Stopped",
        "Warning:",
        "Notice:",
    ]


# @spec TOOL-016
def test_already_applied_and_overridden_checks_come_before_the_steps_entered() -> None:
    events = (
        StepsEntered((EnteredStep(7, Step.UNTAP),)),
        ChecksOverridden((COST_CHECK,), "Cost reducer in play"),
        AlreadyApplied(41),
    )
    outcome = Outcome(Status.OK, EffectRecorded("x"), events, game=a_summary())
    assert [line.split(" ")[0] for line in lines("effect", outcome)[1:-1]] == [
        "Already",
        "Overridden",
        "T7",
    ]


# ------------------------------------------------------------------------------ refusals


# @spec TOOL-023
def test_a_rejected_summary_says_what_failed_and_that_override_applies_it_anyway() -> None:
    assert lines("play", a_refusal(COST_CHECK))[0] == (
        "REJECTED Cost {6}{R} not payable: 5 mana available. Resubmit with override to cast anyway."
    )


# @spec TOOL-023
def test_a_rejection_for_several_checks_lists_every_check() -> None:
    land_drop = FailedCheck(CheckKind.LAND_DROP_USED, "Forest", number=1)
    timing = FailedCheck(CheckKind.LAND_TIMING, "Forest", step=Step.UPKEEP)
    assert lines("play", a_refusal(land_drop, timing))[:3] == [
        "REJECTED 2 rule checks failed. Resubmit with override to play anyway;"
        " one override covers them all.",
        "Rule check: The land drop for this turn is already used.",
        "Rule check: Lands are played in a main step; the game is in upkeep.",
    ]


def test_an_error_for_several_problems_lists_each_error_and_check() -> None:
    errors = (
        Error(ErrorKind.SOURCE_TAPPED, "Sol Ring"),
        Error(ErrorKind.SOURCE_MANA_UNKNOWN, "Grizzly Bears"),
    )
    sick = FailedCheck(CheckKind.SUMMONING_SICK_SOURCE, "Llanowar Elves")
    assert lines("play", a_refusal(sick, errors=errors))[:4] == [
        "ERROR Nothing was applied: 2 errors and 1 failed rule check."
        " Fix the errors; the rule check would also need override.",
        "Error: Sol Ring is already tapped and cannot pay.",
        "Error: Grizzly Bears has no mana reading; state its mana in pay.with"
        ' as {"source": "Grizzly Bears", "mana": "{G}"}.',
        "Rule check: Llanowar Elves is summoning-sick, so it cannot tap for mana.",
    ]


# ------------------------------------------------------------------------------- notices


# @spec TOOL-024
@pytest.mark.parametrize(
    ("tool", "outcome"),
    [
        ("effect", Outcome(Status.OK, EffectRecorded("x"))),
        ("play", a_refusal(COST_CHECK)),
        ("play", a_refusal(errors=(Error(ErrorKind.CARD_NOT_IN_ZONE, "Forest", zone="hand"),))),
        ("effect", Outcome(Status.CHOICE, EffectRecorded("x"))),
        ("get_state", Outcome(Status.OK, StateListed("summary"))),
    ],
)
def test_current_notices_appear_on_every_response_about_the_game(
    tool: str, outcome: Outcome
) -> None:
    game = a_summary(notices=(NoticeKind.DAMAGE, NoticeKind.TURN_LIMIT))
    situation = a_game().build()
    listing = list_state(situation.game, situation.deck, TESTED)
    shown = Outcome(outcome.status, outcome.summary, outcome.events, game, payload=listing)
    assert lines(tool, shown)[-3:-1] == [
        "Notice: 120 damage reached",
        "Notice: turn limit reached",
    ]


# @spec TOOL-024
def test_a_notice_raised_by_the_call_is_shown_once() -> None:
    outcome = Outcome(
        Status.OK,
        EffectRecorded("Fireball"),
        (NoticeRaised(NoticeKind.DAMAGE),),
        game=a_summary(notices=(NoticeKind.DAMAGE,)),
    )
    assert lines("effect", outcome).count("Notice: 120 damage reached") == 1


# ---------------------------------------------------------------------- routine responses


# @spec TOOL-025
def test_a_play_response_does_not_list_the_hand_or_the_battlefield() -> None:
    situation = (
        a_game().with_hand("Forest", "Cultivate", "Counterspell").with_battlefield("Island").build()
    )
    result = play(situation.game, situation.deck, TESTED, card="Forest")
    response = RENDERER.render("play", outcome_of(situation, result)).response
    assert ("Cultivate" not in response, "Island" not in response) == (True, True)


# @spec TOOL-025
def test_an_advance_response_does_not_list_the_hand_or_the_battlefield() -> None:
    situation = (
        a_game()
        .in_step(Step.CLEANUP, turn=3)
        .with_hand("Cultivate")
        .with_battlefield("Sol Ring")
        .with_library("Forest")
        .build()
    )
    result = advance(situation.game, situation.deck, TESTED, to="main1")
    response = RENDERER.render("advance", outcome_of(situation, result)).response
    assert ("Cultivate" not in response, "Sol Ring" not in response) == (True, True)


# ------------------------------------------------------------------------- what is kept


def test_the_call_record_keeps_the_response_for_every_tool_but_a_successful_get_log() -> None:
    rendered = RENDERER.render("effect", Outcome(Status.OK, EffectRecorded("x"), game=a_summary()))
    assert rendered.record == rendered.response


EXPORT: dict[str, object] = {
    "game": {"game_id": "gtest000001"},
    "entries": [{"seq": 1}, {"seq": 2}],
    "snapshots": [{"turn": 1}],
}


# @spec REC-018
def test_a_successful_get_log_responds_with_the_export_as_json() -> None:
    outcome = Outcome(Status.OK, LogExported(2, 1, 0), game=a_summary(), payload=EXPORT)
    assert json.loads(RENDERER.render("get_log", outcome).response) == EXPORT


# @spec REC-018
def test_a_successful_get_log_keeps_a_one_line_size_note_in_its_call_record() -> None:
    outcome = Outcome(Status.OK, LogExported(2, 1, 0), game=a_summary(), payload=EXPORT)
    size = len(json.dumps(EXPORT))
    assert RENDERER.render("get_log", outcome).record == (
        f"get_log export: {size} characters, 2 entries, 1 snapshots, 0 calls"
    )


# @spec REC-024
def test_a_get_log_error_responds_in_the_text_format() -> None:
    outcome = Outcome(Status.ERROR, Refused((Error(ErrorKind.UNKNOWN_GAME, "gnope"),), ()))
    assert RENDERER.render("get_log", outcome).response.startswith("ERROR No game with id gnope.")


# @spec REC-024
def test_a_get_log_error_keeps_its_response_in_the_call_record() -> None:
    outcome = Outcome(Status.ERROR, Refused((Error(ErrorKind.UNKNOWN_GAME, "gnope"),), ()))
    rendered = RENDERER.render("get_log", outcome)
    assert rendered.record == rendered.response
