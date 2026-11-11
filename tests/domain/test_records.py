"""The records domain: building log entries, judging reminders and the get_log export."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.events import (
    AssumptionKind,
    AssumptionMade,
    CardMoved,
    CardPlayed,
    CardsDiscarded,
    CheckKind,
    ChecksOverridden,
    ChoiceResolved,
    CostPaid,
    EffectRecorded,
    Event,
    ExpectationMismatched,
    FailedCheck,
    GameStarted,
    LibraryShuffled,
    MulliganTaken,
    NoticeKind,
    NoticeRaised,
    Placement,
)
from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import Game, Zone
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.results import Applied, Result
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.reading.model import CardReading, FaceReading, StepTrigger
from mtg_goldfishing.domain.records.export import export, log_entry_to_data
from mtg_goldfishing.domain.records.log import log_entry
from mtg_goldfishing.domain.records.model import (
    CallRecord,
    LogEntry,
    Payment,
    ReminderRecord,
    TurnSnapshot,
)
from mtg_goldfishing.domain.records.reminders import JudgedReminder, judge_reminders
from mtg_goldfishing.domain.records.snapshots import take_snapshot
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import TESTED, Situation, a_game
from tests.support.library import LIBRARY

# ---------------------------------------------------------------------------------------
# Arranging calls
# ---------------------------------------------------------------------------------------


def applied(result: Result) -> Applied:
    assert isinstance(result, Applied), result
    return result


def logged(tool: str, arguments: Mapping[str, object], before: Game, result: Result) -> LogEntry:
    """The log entry for an operation's applied result, counted as the game's next change."""
    change = accept_change(applied(result), TESTED, tool, arguments)
    return log_entry(
        tool=tool,
        arguments=arguments,
        before=before,
        after=change.game,
        summary=change.summary,
        events=change.events,
    )


def reported(
    before: Game, tool: str, arguments: Mapping[str, object], *events: Event
) -> tuple[LogEntry, Game]:
    """The entry for a call reported by the events given, the first being its summary.

    Stands in for `play`, `effect` and `choose`, whose operations live in another segment.
    """
    after = before.copy()
    after.change += 1
    entry = log_entry(
        tool=tool,
        arguments=arguments,
        before=before,
        after=after,
        summary=events[0],
        events=events[1:],
    )
    return entry, after


def cast_with_triggers(
    situation: Situation, triggers: list[dict[str, object]], **more: object
) -> LogEntry:
    """The entry of a goldfish `play` of Lightning Bolt stating these cast triggers."""
    operate: Any = play
    arguments = {"card": "Lightning Bolt", "cast_triggers": triggers, **more}
    result = operate(situation.game, situation.deck, TESTED, **arguments)
    return logged("play", arguments, situation.game, result)


def effect_from(before: Game, source: str) -> tuple[LogEntry, Game]:
    return reported(before, "effect", {"source": source, "delta": {}}, EffectRecorded(source))


def entered_upkeep(situation: Situation) -> tuple[LogEntry, Game]:
    result = applied(advance(situation.game, situation.deck, TESTED))
    entry = logged("advance", {}, situation.game, result)
    return entry, result.game


def judged(entries: Sequence[LogEntry]) -> list[bool]:
    return [j.answered for j in judge_reminders(entries)]


VALKI = LIBRARY["Valki, God of Lies // Tibalt, Cosmic Impostor"][0]


def with_upkeep_trigger(card: Card) -> CardReading:
    return CardReading((FaceReading(step_triggers=(StepTrigger(Step.UPKEEP),)), FaceReading()))


# ---------------------------------------------------------------------------------------
# Log entries
# ---------------------------------------------------------------------------------------


# @spec REC-001
def test_a_log_entry_is_numbered_with_the_change_number_after_the_call() -> None:
    situation = a_game().in_step(Step.MAIN1).build()
    situation.game.change = 4
    entry = logged("advance", {}, situation.game, advance(situation.game, situation.deck, TESTED))
    assert entry.seq == 5


# @spec REC-001
def test_the_new_game_entry_is_the_first_change() -> None:
    game = Game(game_id="g1", seed=3, seats=[], change=1)
    entry = log_entry(
        tool="new_game",
        arguments={"deck_id": "d1"},
        before=None,
        after=game,
        summary=GameStarted("g1", 3, ("Forest",)),
        events=(),
    )
    assert (entry.seq, entry.turn, entry.step) == (1, 0, None)


# @spec REC-003
def test_a_log_entry_records_the_turn_and_step_the_call_was_made_in() -> None:
    situation = a_game().in_step(Step.CLEANUP, turn=3).with_library("Forest").build()
    result = advance(situation.game, situation.deck, TESTED, to="upkeep")
    entry = logged("advance", {"to": "upkeep"}, situation.game, result)
    assert (entry.turn, entry.step) == (3, Step.CLEANUP)


# @spec REC-003
def test_a_log_entry_during_mulligans_has_turn_zero_and_no_step() -> None:
    situation = a_game().in_mulligan().with_hand("Forest").with_library(*("Island",) * 8).build()
    result = mulligan(situation.game, situation.deck, TESTED, keep=False)
    entry = logged("mulligan", {"keep": False}, situation.game, result)
    assert (entry.turn, entry.step) == (0, None)


# @spec REC-003
def test_a_log_entry_records_the_tool_and_the_arguments_as_received() -> None:
    situation = a_game().in_step(Step.MAIN1).build()
    arguments: dict[str, object] = {"to": "MAIN2", "after": 0}
    result = advance(situation.game, situation.deck, TESTED, to="MAIN2")
    entry = logged("advance", arguments, situation.game, result)
    assert (entry.tool, entry.arguments) == ("advance", {"to": "MAIN2", "after": 0})


# @spec REC-004
def test_a_play_entry_records_the_card_and_the_zone_it_came_from() -> None:
    situation = a_game().with_hand("Grizzly Bears").build()
    entry, _ = reported(
        situation.game,
        "play",
        {"card": "grizzly bears"},
        CardPlayed("Grizzly Bears", "Grizzly Bears", "hand", "battlefield", is_land=False),
    )
    assert (entry.card, entry.from_zone) == ("Grizzly Bears", "hand")


# @spec REC-004
def test_an_effect_entry_records_its_source_as_the_card() -> None:
    situation = a_game().build()
    entry, _ = effect_from(situation.game, "Treasure")
    assert (entry.card, entry.from_zone) == ("Treasure", None)


# @spec REC-004
def test_a_play_entry_records_the_delta_with_what_the_service_added() -> None:
    situation = a_game().with_hand("Cultivate").build()
    delta: dict[str, object] = {"fetch": {"battlefield_tapped": ["Forest"], "hand": ["Island"]}}
    after = situation.game.copy()
    after.change += 1
    after.tested.shuffles += 1
    entry = log_entry(
        tool="play",
        arguments={"card": "Cultivate", "delta": delta},
        before=situation.game,
        after=after,
        summary=CardPlayed("Cultivate", "Cultivate", "hand", "graveyard", is_land=False),
        events=(
            CardMoved("Atraxa, Praetors' Voice", "battlefield", "command", True),
            CardMoved("Treasure", "battlefield", "graveyard", token_gone=True),
            LibraryShuffled(),
        ),
    )
    assert entry.delta == {
        "fetch": {"battlefield_tapped": ["Forest"], "hand": ["Island"]},
        "added": {
            "shuffles": 1,
            "commander_redirected": ["Atraxa, Praetors' Voice"],
            "tokens_gone": ["Treasure"],
        },
    }


# @spec REC-004
def test_a_call_without_a_delta_or_bookkeeping_records_no_delta() -> None:
    situation = a_game().build()
    entry = logged("advance", {}, situation.game, advance(situation.game, situation.deck, TESTED))
    assert entry.delta is None


# @spec REC-004
def test_a_play_entry_records_the_choices_as_received() -> None:
    situation = a_game().with_hand("Fireball").build()
    choices: dict[str, object] = {"x": 3, "targets": ["opponent 1"]}
    entry, _ = reported(
        situation.game,
        "play",
        {"card": "Fireball", "choices": choices},
        CardPlayed("Fireball", "Fireball", "hand", "graveyard", is_land=False),
    )
    assert entry.choices == {"x": 3, "targets": ["opponent 1"]}


# @spec REC-004
def test_a_play_entry_records_the_payment_made() -> None:
    situation = a_game().with_hand("Fireball").build()
    entry, _ = reported(
        situation.game,
        "play",
        {"card": "Fireball"},
        CardPlayed("Fireball", "Fireball", "hand", "graveyard", is_land=False),
        CostPaid(
            ManaString.parse("{3}{R}"),
            tapped=("Mountain", "Sol Ring"),
            sacrificed=("Treasure",),
            from_pool="{R}",
            surplus="{C}",
        ),
    )
    assert entry.paid == Payment(
        cost="{3}{R}",
        sources=("Mountain", "Sol Ring", "Treasure"),
        life=0,
        from_pool="{R}",
        surplus="{C}",
    )


# @spec REC-004
def test_a_card_played_unpaid_under_an_override_records_no_payment() -> None:
    situation = a_game().with_hand("Shivan Dragon").build()
    entry, _ = reported(
        situation.game,
        "play",
        {"card": "Shivan Dragon", "override": "cost reduced by Goreclaw"},
        CardPlayed("Shivan Dragon", "Shivan Dragon", "hand", "battlefield", is_land=False),
        CostPaid(ManaString.parse("{4}{R}{R}"), unpaid=True),
    )
    assert entry.paid is None


# @spec REC-005
def test_a_log_entry_records_the_reason_verbatim() -> None:
    situation = a_game().build()
    reason = "  Holding up mana for Counterspell;  no threats yet.  "
    result = advance(situation.game, situation.deck, TESTED)
    entry = logged("advance", {"reason": reason}, situation.game, result)
    assert entry.reason == reason


# @spec REC-006
def test_a_log_entry_records_the_override_and_the_checks_it_overrode() -> None:
    situation = a_game().with_hand("Forest").build()
    checks = (
        FailedCheck(CheckKind.LAND_DROP_USED),
        FailedCheck(CheckKind.LAND_TIMING, step=Step.UPKEEP),
    )
    entry, _ = reported(
        situation.game,
        "play",
        {"card": "Forest", "override": "Azusa lets me play another land"},
        CardPlayed("Forest", "Forest", "hand", "battlefield", is_land=True),
        ChecksOverridden(checks, "Azusa lets me play another land"),
    )
    assert (entry.override, entry.overridden_checks) == (
        "Azusa lets me play another land",
        ("land_drop_used", "land_timing"),
    )


# @spec REC-006
def test_a_log_entry_records_expect_mismatches() -> None:
    situation = a_game().build()
    entry, _ = reported(
        situation.game,
        "effect",
        {"source": "Bolas's Citadel", "delta": {"life": -2}, "expect": {"life": 40}},
        EffectRecorded("Bolas's Citadel"),
        ExpectationMismatched("life", "38", "40"),
    )
    assert entry.expect_mismatches == ("life: 38, expected 40",)


# @spec REC-006
def test_a_log_entry_records_the_assumptions_the_service_made() -> None:
    situation = a_game().with_hand("Fireball", "Glacial Fortress").build()
    entry, _ = reported(
        situation.game,
        "play",
        {"card": "Fireball"},
        CardPlayed("Fireball", "Fireball", "hand", "graveyard", is_land=False),
        AssumptionMade(AssumptionKind.X_IS_ZERO, "Fireball"),
        AssumptionMade(AssumptionKind.READING, "Glacial Fortress", "assumes it enters untapped"),
    )
    assert entry.assumptions == (
        "x_is_zero: Fireball",
        "reading: Glacial Fortress: assumes it enters untapped",
    )


# @spec REC-006
def test_a_log_entry_records_the_cards_drawn() -> None:
    situation = a_game().in_step(Step.UPKEEP).with_library("Island", "Forest").build()
    entry = logged("advance", {}, situation.game, advance(situation.game, situation.deck, TESTED))
    assert entry.drawn == ("Island",)


# @spec REC-006, REC-008
def test_a_log_entry_records_the_steps_entered_from_the_summary_event() -> None:
    situation = a_game().in_step(Step.MAIN2, turn=3).with_library("Forest").build()
    result = advance(situation.game, situation.deck, TESTED, to="upkeep")
    entry = logged("advance", {"to": "upkeep"}, situation.game, result)
    assert entry.steps == (Step.END, Step.CLEANUP, Step.UNTAP, Step.UPKEEP)


# @spec REC-006, REC-008
def test_a_log_entry_records_steps_entered_reported_among_the_events() -> None:
    situation = a_game().in_mulligan().with_hand("Forest").with_library("Island").build()
    result = mulligan(situation.game, situation.deck, TESTED, keep=True)
    entry = logged("mulligan", {"keep": True}, situation.game, result)
    assert entry.steps == (Step.UNTAP, Step.UPKEEP, Step.DRAW, Step.MAIN1)


# @spec REC-006
def test_a_log_entry_records_the_reminders_issued_with_who_they_were_for() -> None:
    situation = a_game().in_step(Step.UNTAP, turn=3).with_battlefield("Phyrexian Arena").build()
    entry, _ = entered_upkeep(situation)
    arena = situation.named("Phyrexian Arena")
    assert entry.reminders == (
        ReminderRecord("Phyrexian Arena", Step.UPKEEP, arena.id, "Phyrexian Arena", 3),
    )


# @spec REC-006
def test_a_reminder_issued_in_a_new_turn_is_recorded_for_that_turn() -> None:
    situation = (
        a_game()
        .in_step(Step.CLEANUP, turn=3)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest")
        .build()
    )
    result = advance(situation.game, situation.deck, TESTED, to="upkeep")
    entry = logged("advance", {"to": "upkeep"}, situation.game, result)
    assert [r.turn for r in entry.reminders] == [4]


# @spec REC-006
def test_a_log_entry_records_the_notices_first_raised() -> None:
    situation = a_game().build()
    entry, _ = reported(
        situation.game,
        "effect",
        {"source": "Exsanguinate", "delta": {"damage": 120}},
        EffectRecorded("Exsanguinate"),
        NoticeRaised(NoticeKind.DAMAGE),
    )
    assert entry.notices == ("damage",)


# @spec REC-007
def test_the_new_game_entry_outcome_is_the_opening_hand() -> None:
    game = Game(game_id="g1", seed=3, seats=[], change=1)
    entry = log_entry(
        tool="new_game",
        arguments={"deck_id": "d1"},
        before=None,
        after=game,
        summary=GameStarted("g1", 3, ("Forest", "Sol Ring")),
        events=(),
    )
    assert entry.outcome == {"hand": ["Forest", "Sol Ring"]}


# @spec REC-007
def test_a_mulligan_entry_outcome_is_the_new_hand() -> None:
    situation = a_game().in_mulligan().with_hand("Forest").build()
    entry, _ = reported(
        situation.game, "mulligan", {"keep": False}, MulliganTaken(1, ("Island", "Swamp"))
    )
    assert entry.outcome == {"hand": ["Island", "Swamp"]}


# @spec REC-007
def test_a_kept_hand_entry_outcome_is_the_hand_and_the_cards_bottomed() -> None:
    situation = (
        a_game().in_mulligan().with_hand("Forest", "Ponder").with_library("Island", "Swamp").build()
    )
    situation.game.tested.mulligans = 2
    result = mulligan(situation.game, situation.deck, TESTED, keep=True, bottom=["Ponder"])
    entry = logged("mulligan", {"keep": True, "bottom": ["Ponder"]}, situation.game, result)
    assert entry.outcome == {"hand": ["Forest"], "bottomed": ["Ponder"]}


# @spec REC-007
def test_a_choose_entry_outcome_is_where_each_revealed_card_went() -> None:
    situation = a_game().build()
    entry, _ = reported(
        situation.game,
        "choose",
        {"choice_id": "x1", "selections": {"hand": ["Island"]}},
        ChoiceResolved((Placement("Island", "hand"), Placement("Swamp", "library_bottom"))),
    )
    assert entry.outcome == {
        "placements": [
            {"card": "Island", "to": "hand"},
            {"card": "Swamp", "to": "library_bottom"},
        ]
    }


# @spec REC-007
def test_an_attack_entry_outcome_is_the_attackers_blocked_and_targets() -> None:
    situation = (
        a_game()
        .in_step(Step.MAIN1)
        .with_commander("Atraxa, Praetors' Voice", zone=Zone.BATTLEFIELD)
        .with_battlefield("Grizzly Bears")
        .build()
    )
    arguments: dict[str, object] = {
        "attackers": ["Atraxa, Praetors' Voice", "Grizzly Bears"],
        "blocked": ["Grizzly Bears"],
        "commander_target": 2,
    }
    result = attack(situation.game, situation.deck, TESTED, **arguments)  # type: ignore[arg-type]
    entry = logged("attack", arguments, situation.game, result)
    assert entry.outcome == {
        "attackers": ["Atraxa, Praetors' Voice", "Grizzly Bears"],
        "blocked": ["Grizzly Bears"],
        "targets": {"Atraxa, Praetors' Voice": 2},
    }


# @spec REC-007
def test_the_entry_that_enters_combat_damage_records_damage_per_attacker() -> None:
    situation = a_game().in_step(Step.MAIN1).with_battlefield("Grizzly Bears").build()
    declared = applied(
        attack(situation.game, situation.deck, TESTED, attackers=["Grizzly Bears"], damage=None)
    )
    result = advance(declared.game, situation.deck, TESTED, to="combat_damage")
    entry = logged("advance", {"to": "combat_damage"}, declared.game, result)
    assert entry.outcome == {
        "damage": [{"attacker": "Grizzly Bears", "damage": 2, "commander_target": None}]
    }


# @spec REC-007
def test_an_advance_entry_outcome_is_the_cards_discarded() -> None:
    situation = a_game().in_step(Step.END).with_hand(*("Ponder",) * 8).build()
    result = advance(situation.game, situation.deck, TESTED, discard=["Ponder"])
    entry = logged("advance", {"discard": ["Ponder"]}, situation.game, result)
    assert entry.outcome == {"discarded": ["Ponder"]}


# @spec REC-007
def test_a_discard_by_effect_is_not_an_outcome() -> None:
    situation = a_game().with_hand("Ponder").build()
    entry, _ = reported(
        situation.game,
        "effect",
        {"source": "Faithless Looting", "delta": {"discard": ["Ponder"]}},
        EffectRecorded("Faithless Looting"),
        CardsDiscarded(("Ponder",)),
    )
    assert entry.outcome is None


# @spec REC-007
def test_the_end_game_entry_outcome_is_the_result_and_notes() -> None:
    situation = a_game().build()
    result = end_game(situation.game, situation.deck, TESTED, result="win", notes="combo on turn 6")
    entry = logged("end_game", {"result": "win"}, situation.game, result)
    assert entry.outcome == {"result": "win", "notes": "combo on turn 6"}


# @spec REC-008
def test_a_log_entry_holds_only_json_compatible_data() -> None:
    situation = (
        a_game()
        .in_step(Step.MAIN2, turn=3)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest", "Island")
        .build()
    )
    result = advance(situation.game, situation.deck, TESTED, to="upkeep")
    entry = logged("advance", {"to": "upkeep", "reason": "go"}, situation.game, result)
    data = log_entry_to_data(entry)
    assert json.loads(json.dumps(data)) == data


# @spec REC-083
def test_a_goldfish_play_records_each_cast_trigger_s_delta_as_applied_in_the_order_listed() -> None:
    situation = (
        a_game()
        .with_hand("Lightning Bolt")
        .with_battlefield("Mountain")
        .with_library("Forest")
        .build()
    )
    triggers = [
        {"source": "Thousand-Year Storm", "delta": {"fetch": {"hand": ["Forest"]}}},
        {"source": "Young Pyromancer", "delta": {"draw": 0}, "choices": {"notes": "n"}},
    ]
    entry = cast_with_triggers(situation, triggers)
    no_bookkeeping = {"shuffles": 0, "commander_redirected": [], "tokens_gone": []}
    assert log_entry_to_data(entry)["cast_triggers"] == [
        {
            "source": "Thousand-Year Storm",
            "delta": {
                "fetch": {"hand": ["Forest"]},
                "added": {"shuffles": 1, "commander_redirected": [], "tokens_gone": []},
            },
            "choices": None,
        },
        {
            "source": "Young Pyromancer",
            "delta": {"draw": 0, "added": no_bookkeeping},
            "choices": {"notes": "n"},
        },
    ]


# @spec REC-083, REC-004
def test_a_goldfish_spell_s_delta_holds_none_of_its_cast_triggers_bookkeeping() -> None:
    situation = (
        a_game()
        .with_hand("Lightning Bolt")
        .with_battlefield("Mountain")
        .with_library("Forest")
        .build()
    )
    triggers = [{"source": "Thousand-Year Storm", "delta": {"fetch": {"hand": ["Forest"]}}}]
    entry = cast_with_triggers(situation, triggers, delta={"damage": 3})
    assert entry.delta == {
        "damage": 3,
        "added": {"shuffles": 0, "commander_redirected": [], "tokens_gone": []},
    }


# @spec REC-085
def test_a_goldfish_entry_whose_call_stated_no_cast_triggers_records_an_empty_list() -> None:
    situation = a_game().build()
    entry = logged("advance", {}, situation.game, advance(situation.game, situation.deck, TESTED))
    assert log_entry_to_data(entry)["cast_triggers"] == []


# ---------------------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------------------


# @spec REC-009
def test_a_reminder_is_answered_by_a_later_effect_from_the_permanent_in_the_same_turn() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Phyrexian Arena").build()
    reminding, game = entered_upkeep(situation)
    answering, _ = effect_from(game, "Phyrexian Arena")
    assert judged([reminding, answering]) == [True]


# @spec REC-009
def test_a_reminder_without_an_answering_effect_is_unanswered() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Phyrexian Arena").build()
    reminding, game = entered_upkeep(situation)
    other, _ = effect_from(game, "Sol Ring")
    assert judged([reminding, other]) == [False]


# @spec REC-009
def test_a_reminder_is_not_answered_by_an_effect_in_a_later_turn() -> None:
    situation = (
        a_game()
        .in_step(Step.UNTAP, turn=3)
        .with_battlefield("Phyrexian Arena")
        .with_library("Forest")
        .build()
    )
    reminding, game = entered_upkeep(situation)
    result = applied(advance(game, situation.deck, TESTED, to="upkeep"))
    next_turn = logged("advance", {"to": "upkeep"}, game, result)
    answering, _ = effect_from(result.game, "Phyrexian Arena")
    assert judged([reminding, next_turn, answering]) == [False, True]


# @spec REC-009
def test_a_reminder_is_not_answered_by_an_earlier_effect() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Phyrexian Arena").build()
    early, game = effect_from(situation.game, "Phyrexian Arena")
    situation.game = game
    reminding, _ = entered_upkeep(situation)
    assert judged([early, reminding]) == [False]


# @spec REC-009
def test_a_reminder_is_answered_only_by_an_effect_call() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Phyrexian Arena").build()
    reminding, game = entered_upkeep(situation)
    played, _ = reported(
        game,
        "play",
        {"card": "Phyrexian Arena", "from": "graveyard"},
        CardPlayed("Phyrexian Arena", "Phyrexian Arena", "graveyard", "battlefield", False),
    )
    assert judged([reminding, played]) == [False]


# @spec REC-009
def test_one_effect_answers_the_reminders_of_every_permanent_it_names() -> None:
    situation = (
        a_game().in_step(Step.UNTAP).with_battlefield("Rhystic Study", "Rhystic Study").build()
    )
    reminding, game = entered_upkeep(situation)
    answering, _ = effect_from(game, "rhystic study")
    assert judged([reminding, answering]) == [True, True]


# @spec REC-009
def test_judging_reports_each_reminder_with_the_entry_that_issued_it() -> None:
    situation = a_game().in_step(Step.UNTAP, turn=2).with_battlefield("Phyrexian Arena").build()
    situation.game.change = 6
    reminding, _ = entered_upkeep(situation)
    assert judge_reminders([reminding]) == [
        JudgedReminder(seq=7, reminder=reminding.reminders[0], answered=False)
    ]


# @spec REC-010
def test_an_instance_id_answers_only_that_permanents_reminder() -> None:
    situation = (
        a_game().in_step(Step.UNTAP).with_battlefield("Rhystic Study", "Rhystic Study").build()
    )
    reminding, game = entered_upkeep(situation)
    second = reminding.reminders[1].instance_id
    answering, _ = effect_from(game, second.upper())
    assert judged([reminding, answering]) == [False, True]


# @spec REC-010
def test_a_reminder_is_answered_by_the_card_name_ignoring_case() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Phyrexian Arena").build()
    reminding, game = entered_upkeep(situation)
    answering, _ = effect_from(game, "PHYREXIAN arena")
    assert judged([reminding, answering]) == [True]


# @spec REC-010
def test_a_reminder_is_answered_by_the_name_of_the_face_in_play() -> None:
    situation = (
        a_game()
        .in_step(Step.UNTAP)
        .with_card(VALKI, with_upkeep_trigger(VALKI))
        .with_battlefield(VALKI.name)
        .build()
    )
    reminding, game = entered_upkeep(situation)
    answering, _ = effect_from(game, "valki, god of lies")
    assert judged([reminding, answering]) == [True]


TIBALT = "Tibalt, Cosmic Impostor"


# @spec REC-009, REC-010
@pytest.mark.parametrize(
    ("source", "answered"),
    [(VALKI.name, True), (TIBALT.upper(), True), ("Valki, God of Lies", False)],
    ids=["card name", "face in play", "face not in play"],
)
def test_the_game_and_the_log_agree_on_answering_a_reminder_issued_on_a_back_face(
    source: str, answered: bool
) -> None:
    back_face_trigger = CardReading(
        (FaceReading(), FaceReading(step_triggers=(StepTrigger(Step.UPKEEP),)))
    )
    situation = (
        a_game()
        .in_step(Step.UNTAP)
        .with_card(VALKI, back_face_trigger)
        .with_battlefield(VALKI.name)
        .build()
    )
    situation.named(VALKI.name).face = 1
    reminding, game = entered_upkeep(situation)
    arguments = {"source": source, "delta": {}}
    result = applied(effect(game, situation.deck, TESTED, source=source, delta={}))
    answering = logged("effect", arguments, game, result)
    snapshot = take_snapshot(result.game, situation.deck)
    assert snapshot is not None
    unanswered = () if answered else (ReminderRecord(TIBALT, Step.UPKEEP),)
    assert (judged([reminding, answering]), snapshot.unanswered_reminders) == (
        [answered],
        unanswered,
    )


# @spec REC-010
def test_a_reminder_is_answered_by_the_full_card_name_of_a_double_faced_card() -> None:
    situation = (
        a_game()
        .in_step(Step.UNTAP)
        .with_card(VALKI, with_upkeep_trigger(VALKI))
        .with_battlefield(VALKI.name)
        .build()
    )
    reminding, game = entered_upkeep(situation)
    answering, _ = effect_from(game, VALKI.name)
    assert judged([reminding, answering]) == [True]


# ---------------------------------------------------------------------------------------
# get_log
# ---------------------------------------------------------------------------------------


def a_snapshot(turn: int, written_by: int) -> TurnSnapshot:
    return TurnSnapshot(
        turn=turn,
        hand=(),
        battlefield=(),
        graveyard=(),
        lands=0,
        mana_available=0,
        mana_spent=0,
        land_drop_made=False,
        life=40,
        damage_dealt=0,
        commander_damage=(),
        unanswered_reminders=(),
        written_by=written_by,
    )


def a_call(change: int | None, tool: str = "advance") -> CallRecord:
    return CallRecord(
        time=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        game_id="gtest000001",
        tool=tool,
        arguments={},
        status="OK",
        response="OK",
        is_override=False,
        change=change,
        id=change or 0,
    )


def a_played_game() -> tuple[Game, list[LogEntry], list[TurnSnapshot]]:
    """Three advances from main2 of turn 3: end, cleanup (writing a snapshot), untap."""
    situation = a_game().in_step(Step.MAIN2, turn=3).build()
    game = situation.game
    entries: list[LogEntry] = []
    snapshots: list[TurnSnapshot] = []
    for _ in range(3):
        result = applied(advance(game, situation.deck, TESTED))
        entries.append(logged("advance", {}, game, result))
        snapshots.extend(result.snapshots)
        game = result.game
    return game, entries, snapshots


# @spec REC-019
def test_the_export_describes_the_game() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [], since=None)
    assert document["game"] == {
        "game_id": "gtest000001",
        "deck_id": "dtest",
        "seed": 7,
        "turn_limit": None,
        "draw_first_turn": True,
        "status": "active",
        "turn": 4,
        "change": 3,
        "result": None,
    }


# @spec REC-019
def test_the_export_gives_the_result_of_an_ended_game() -> None:
    situation = a_game().build()
    ended = applied(
        end_game(situation.game, situation.deck, TESTED, result="stalled", notes="no gas")
    )
    document = export(ended.game, [], [], [], since=None)
    game = document["game"]
    assert isinstance(game, dict)
    assert game["result"] == {"outcome": "stalled", "notes": "no gas"}


# @spec REC-019
def test_the_export_holds_the_log_entries_in_order() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [], since=None)
    assert document["entries"] == [log_entry_to_data(entry) for entry in entries]


# @spec REC-019
def test_the_export_is_json() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [a_call(1)], since=None, include_calls=True)
    assert json.loads(json.dumps(document)) == document


# @spec REC-019, REC-009
def test_an_exported_entry_says_whether_each_reminder_was_answered() -> None:
    situation = a_game().in_step(Step.UNTAP).with_battlefield("Phyrexian Arena").build()
    reminding, game = entered_upkeep(situation)
    answering, game = effect_from(game, "Phyrexian Arena")
    document = export(game, [reminding, answering], [], [], since=None)
    exported = document["entries"]
    assert isinstance(exported, list)
    assert exported[0]["reminders"] == [
        {
            "card": "Phyrexian Arena",
            "step": "upkeep",
            "instance_id": situation.named("Phyrexian Arena").id,
            "answered": True,
        }
    ]


# @spec REC-020
def test_the_export_includes_snapshots_by_default() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [], since=None)
    assert [s["turn"] for s in document["snapshots"]] == [3]  # type: ignore[attr-defined]


# @spec REC-020
def test_the_export_leaves_out_snapshots_when_asked() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [], since=None, include_snapshots=False)
    assert "snapshots" not in document


# @spec REC-021
def test_the_export_leaves_out_call_records_by_default() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [a_call(1)], since=None)
    assert "calls" not in document


# @spec REC-021
def test_the_export_includes_call_records_when_asked() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [a_call(1)], since=None, include_calls=True)
    assert document["calls"] == [
        {
            "id": 1,
            "time": "2026-11-09T12:00:00+00:00",
            "game_id": "gtest000001",
            "tool": "advance",
            "arguments": {},
            "status": "OK",
            "response": "OK",
            "is_override": False,
            "change": 1,
        }
    ]


# @spec REC-022
def test_since_keeps_only_later_log_entries() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [], since=1)
    assert [e["seq"] for e in document["entries"]] == [2, 3]  # type: ignore[attr-defined]


# @spec REC-022
def test_since_keeps_only_call_records_with_a_later_change_number() -> None:
    game, entries, snapshots = a_played_game()
    calls = [a_call(None, "get_log"), a_call(1), a_call(2), a_call(3)]
    document = export(game, entries, snapshots, calls, since=2, include_calls=True)
    assert [c["change"] for c in document["calls"]] == [3]  # type: ignore[attr-defined]


# @spec REC-022
def test_since_keeps_only_snapshots_written_by_later_entries() -> None:
    game, entries, _ = a_played_game()
    snapshots = [a_snapshot(2, written_by=1), a_snapshot(3, written_by=2)]
    document = export(game, entries, snapshots, [], since=1)
    assert [s["turn"] for s in document["snapshots"]] == [3]  # type: ignore[attr-defined]


# @spec REC-025
def test_the_export_holds_the_records_and_no_figures_computed_from_them() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [a_call(1)], since=None, include_calls=True)
    assert set(document) == {"game", "entries", "snapshots", "calls"}


# @spec REC-025
def test_an_exported_snapshot_holds_only_the_snapshot_fields() -> None:
    game, entries, snapshots = a_played_game()
    document = export(game, entries, snapshots, [], since=None)
    exported = document["snapshots"]
    assert isinstance(exported, list)
    assert set(exported[0]) == {
        "turn",
        "hand",
        "battlefield",
        "graveyard",
        "lands",
        "mana_available",
        "mana_spent",
        "land_drop_made",
        "life",
        "damage_dealt",
        "commander_damage",
        "unanswered_reminders",
    }
