"""What each event, error and rule check reads as in a response."""

from __future__ import annotations

from dataclasses import replace
from typing import get_args

import pytest

from mtg_goldfishing.adapters.mcp.refusal_lines import check_text, error_text
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer, event_lines
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    AlreadyApplied,
    AlreadySo,
    AlreadySoKind,
    AssumptionKind,
    AssumptionMade,
    AttackDeclared,
    AttackerDamage,
    CardMoved,
    CardPlayed,
    CardsDiscarded,
    CardsDrawn,
    CardsRevealed,
    CheckKind,
    ChecksOverridden,
    ChoiceResolved,
    CombatDamageDealt,
    CostPaid,
    CountersChanged,
    DamageAdded,
    DeckLoaded,
    DeckReport,
    EffectRecorded,
    EnteredStep,
    Error,
    ErrorKind,
    Event,
    ExpectationMismatched,
    FailedCheck,
    GameEnded,
    GameStarted,
    HandKept,
    InstanceChosen,
    LibraryShuffled,
    LifeChanged,
    LogExported,
    ManaAdded,
    MulliganTaken,
    NothingRevealed,
    NoticeKind,
    NoticeRaised,
    Placement,
    Refused,
    ReminderIssued,
    RevealedCard,
    SnapshotWritten,
    StateListed,
    StepsEntered,
    StopReason,
    Tapped,
    TokensCreated,
    Untapped,
)
from mtg_goldfishing.domain.game.calls import accept_change, follow_change
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.results import Applied, Resent
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.playing import play
from mtg_goldfishing.domain.reading.model import (
    EntersTappedReading,
    EntersTappedReport,
    KeywordReading,
    KeywordReport,
    ManaAbility,
    ReadAbility,
    UnreadAbility,
)
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import a_game
from tests.support.library import taps_for, taps_for_any
from tests.support.outcomes import ATRAXA, a_summary, outcome_of

RENDERER = TextRenderer()


def response(tool: str, outcome: Outcome) -> list[str]:
    return RENDERER.render(tool, outcome).response.splitlines()


def mana(text: str) -> ManaString:
    return ManaString.parse(text)


# ------------------------------------------------------------------ responses from play


# @spec TOOL-016, TOOL-026
def test_a_play_reports_the_card_cast_and_how_it_was_paid() -> None:
    situation = (
        a_game()
        .with_hand("Cultivate")
        .with_battlefield("Forest", "Forest", "Island", "Plains")
        .build()
    )
    result = play(situation.game, situation.deck, card="Cultivate")
    assert response("play", outcome_of(situation, result))[:2] == [
        "OK Cast Cultivate.",
        "Paid {2}{G}: tapped Forest, Forest, Island.",
    ]


# @spec TOOL-023
def test_a_refused_play_says_the_cost_is_not_payable_and_how_much_mana_there_is() -> None:
    situation = a_game().with_hand("Shivan Dragon").with_battlefield(*("Forest",) * 5).build()
    result = play(situation.game, situation.deck, card="Shivan Dragon")
    assert response("play", outcome_of(situation, result))[0] == (
        "REJECTED Cost {4}{R}{R} not payable: 5 mana available; not enough {R}."
        " Resubmit with override to cast anyway."
    )


# @spec TOOL-016, TOOL-026
def test_an_advance_that_stops_for_a_reminder_says_why_and_what_to_send_next() -> None:
    situation = (
        a_game()
        .in_step(Step.MAIN2, turn=6)
        .with_battlefield("Phyrexian Arena", "Forest")
        .with_hand("Cultivate")
        .with_library("Island")
        .build()
    )
    result = advance(situation.game, situation.deck, to="main1")
    assert response("advance", outcome_of(situation, result))[:3] == [
        "OK end → cleanup → T7 untap → upkeep",
        "Reminder (upkeep): Phyrexian Arena",
        'Stopped at upkeep for the reminder. Send advance(to="main1", after=0) again to continue.',
    ]


# @spec TOOL-026
def test_several_reminded_permanents_with_one_name_are_counted() -> None:
    event = ReminderIssued(Step.UPKEEP, (("Rhystic Study", 2), ("Phyrexian Arena", 1)))
    assert event_lines(event) == ["Reminder (upkeep): Rhystic Study ×2, Phyrexian Arena"]


# @spec TOOL-026
def test_an_advance_that_stops_before_cleanup_says_how_many_cards_to_discard() -> None:
    event = AdvanceStopped(StopReason.DISCARD, Step.END, Step.MAIN1, discard_count=2)
    assert event_lines(event, after=42) == [
        "Stopped at end: the hand is over seven cards, so 2 must be discarded in cleanup."
        ' Send advance(to="main1", discard=[2 cards from hand], after=42) to continue,'
        " or add override if the hand has no maximum size."
    ]


# @spec TOOL-026
def test_an_expectation_mismatch_is_a_warning() -> None:
    event = ExpectationMismatched("untapped_lands", "1", "2")
    assert event_lines(event) == ["Warning: untapped_lands is 1, expected 2"]


# @spec TOOL-026
def test_revealed_cards_are_listed_with_the_choice_id() -> None:
    event = CardsRevealed(
        "ch2", "look", (RevealedCard("c41", "Forest"), RevealedCard("c12", "Island"))
    )
    assert event_lines(event) == [
        "Choice ch2 (look) revealed: Forest (c41), Island (c12)."
        ' Say where they go with choose(choice_id="ch2").'
    ]


# @spec TOOL-026
def test_combat_damage_is_shown_per_attacker_with_the_new_totals() -> None:
    event = CombatDamageDealt(
        (AttackerDamage("Grizzly Bears", 2), AttackerDamage(ATRAXA, 4, commander_target=1)),
        28,
        ((ATRAXA, (0, 4, 0)),),
    )
    assert event_lines(event) == [
        "Grizzly Bears dealt 2 combat damage.",
        "Atraxa, Praetors' Voice dealt 4 combat damage to opponent 1.",
        "Damage dealt 28/120; commander damage Atraxa, Praetors' Voice 0/4/0.",
    ]


# @spec TOOL-026
def test_an_unannounced_x_is_stated_as_an_assumption() -> None:
    event = AssumptionMade(AssumptionKind.X_IS_ZERO, "Fireball")
    assert event_lines(event) == ["Assumed: X = 0 for Fireball."]


# @spec TOOL-024
def test_each_notice_has_its_own_wording() -> None:
    worded = {event_lines(NoticeRaised(kind))[0] for kind in NoticeKind}
    assert len(worded) == len(NoticeKind)


# ------------------------------------------------------------------------------- resends


# @spec TOOL-026
def test_a_resend_renders_the_original_events_and_says_it_was_already_applied() -> None:
    situation = (
        a_game().with_hand("Cultivate").with_battlefield("Forest", "Forest", "Forest").build()
    )
    arguments: dict[str, object] = {"card": "Cultivate"}
    applied = play(situation.game, situation.deck, card="Cultivate")
    assert isinstance(applied, Applied)
    accepted = accept_change(applied, "play", arguments)
    resent = follow_change(accepted.game, "play", {**arguments, "after": 0}, 0)
    assert isinstance(resent, Resent)
    assert response("play", outcome_of(situation, resent))[:3] == [
        "OK Cast Cultivate.",
        "Already applied as change #1; nothing was applied again.",
        "Paid {2}{G}: tapped Forest, Forest, Forest.",
    ]


# ----------------------------------------------------------------------------- get_state


# @spec TOOL-016, TOOL-025
def test_get_state_lists_the_zones_and_what_was_read_of_each_permanent() -> None:
    situation = (
        a_game()
        .with_commander(ATRAXA)
        .with_hand("Cultivate", "Island")
        .with_battlefield("Forest", tapped=True)
        .with_battlefield("Llanowar Elves", counters={"+1/+1": 2})
        .with_battlefield("Phyrexian Arena")
        .with_graveyard("Ponder")
        .with_library("Swamp")
        .build()
    )
    listing = list_state(situation.game, situation.deck)
    outcome = Outcome(Status.OK, StateListed("summary"), game=a_summary(), payload=listing)
    assert response("get_state", outcome)[:8] == [
        "OK State, summary detail.",
        "Hand (2): Cultivate, Island",
        "Battlefield (3):",
        "  c4 Forest: tapped; mana {T}: {G}",
        "  c5 Llanowar Elves: counters 2 +1/+1; mana {T}: {G}",
        "  c6 Phyrexian Arena: trigger in upkeep",
        "Graveyard (1): Ponder",
        "Command zone (1): Atraxa, Praetors' Voice",
    ]


# @spec TOOL-016
def test_get_state_in_full_adds_exile_library_size_commanders_and_payments() -> None:
    situation = (
        a_game()
        .with_commander(ATRAXA)
        .with_hand("Cultivate")
        .with_battlefield("Forest", "Forest", "Forest")
        .with_exile("Ponder")
        .with_library("Swamp", "Island")
        .build()
    )
    played = play(situation.game, situation.deck, card="Cultivate")
    assert isinstance(played, Applied)
    listing = list_state(played.game, situation.deck, "full")
    outcome = Outcome(Status.OK, StateListed("full"), game=a_summary(), payload=listing)
    assert response("get_state", outcome)[-5:-1] == [
        "Exile (1): Ponder",
        "Library: 2 cards",
        "Commander Atraxa, Praetors' Voice: cast 0 times, damage 0/0/0",
        "Payments this turn: {2}{G} (3 mana)",
    ]


# @spec TOOL-016
def test_get_state_never_shows_the_library_contents() -> None:
    situation = a_game().with_hand("Cultivate").with_library("Swamp", "Mountain").build()
    listing = list_state(situation.game, situation.deck, "full")
    outcome = Outcome(Status.OK, StateListed("full"), game=a_summary(), payload=listing)
    text = RENDERER.render("get_state", outcome).response
    assert ("Swamp" in text, "Mountain" in text) == (False, False)


# ----------------------------------------------------------------------------- load_deck


# @spec TOOL-026
def test_load_deck_lists_each_part_of_the_deck_report_that_is_not_empty() -> None:
    report = DeckReport(
        definitions_applied=("Custom Card",),
        read_with_assumptions=(
            ReadAbility(
                "Nimbus Maze",
                ManaAbility(
                    taps_for("{W}").produces, assumptions=("ignores activation condition",)
                ),
            ),
        ),
        unread=(UnreadAbility("Mana Flare", "Whenever a player taps a land for mana..."),),
        not_used_on_their_own=(ReadAbility("Lotus Petal", taps_for_any(sacrifices=True)),),
        granting_haste_or_vigilance=(
            KeywordReport("Concordant Crossroads", "haste", KeywordReading()),
        ),
        enters_tapped=(EntersTappedReport("Temple of Plenty", EntersTappedReading(tapped=True)),),
        assumed_untapped=(
            EntersTappedReport(
                "Glacial Fortress",
                EntersTappedReading(
                    assumptions=(
                        "assumes it enters untapped: unless you control a Plains or an Island",
                    )
                ),
            ),
        ),
        keywords_with_assumptions=(
            KeywordReport(
                "Odric", "vigilance", KeywordReading(assumptions=("assumes its condition is met",))
            ),
        ),
    )
    outcome = Outcome(Status.OK, DeckLoaded("d3f9a01c2e", 100, (ATRAXA,), report=report))
    assert response("load_deck", outcome) == [
        "OK Loaded deck d3f9a01c2e: 100 cards, commander Atraxa, Praetors' Voice.",
        "Definitions applied: Custom Card",
        "Mana read with assumptions: Nimbus Maze (ignores activation condition)",
        "Mana not read: Mana Flare",
        "Not used by the auto payment system on its own (name them in pay):"
        " Lotus Petal (sacrificed)",
        "Grants haste or vigilance: Concordant Crossroads (haste)",
        "Enters tapped: Temple of Plenty",
        "Assumed to enter untapped: Glacial Fortress (unless you control a Plains or an Island)",
        "Keywords read with assumptions: Odric (vigilance: assumes its condition is met)",
    ]


# @spec DECK-038
def test_load_deck_names_the_cards_a_refresh_kept_on_their_cached_data() -> None:
    report = DeckReport(not_refreshed=("Sol Ring", "Ponder"))
    outcome = Outcome(Status.OK, DeckLoaded("d3f9a01c2e", 100, (ATRAXA,), report=report))
    assert response("load_deck", outcome) == [
        "OK Loaded deck d3f9a01c2e: 100 cards, commander Atraxa, Praetors' Voice.",
        "Not refreshed (cached data kept): Sol Ring, Ponder",
    ]


# @spec TOOL-026
def test_load_deck_names_both_commanders_and_any_overridden_checks() -> None:
    overridden = ChecksOverridden(
        (FailedCheck(CheckKind.DECK_SIZE, number=99, expected=100),), "testing a 99"
    )
    outcome = Outcome(
        Status.OK,
        DeckLoaded("dabc", 99, ("Kraum, Ludevic's Opus", "Tymna the Weaver")),
        (overridden,),
    )
    assert response("load_deck", outcome) == [
        "OK Loaded deck dabc: 99 cards, commanders Kraum, Ludevic's Opus and Tymna the Weaver.",
        "Overridden (testing a 99): The deck has 99 cards, not 100.",
    ]


# ------------------------------------------------------------- one rendering for each kind


def sample_of_every_event() -> list[Event]:
    revealed = (RevealedCard("c9", "Island"),)
    return [
        StepsEntered((EnteredStep(7, Step.UNTAP), EnteredStep(7, Step.UPKEEP))),
        DeckLoaded("dabc", 100, (ATRAXA,)),
        GameStarted("gabc", 42, ("Forest", "Island")),
        MulliganTaken(1, ("Forest",)),
        HandKept(("Island",), ("Forest",)),
        CardPlayed("Forest", "Forest", "hand", "battlefield", is_land=True),
        EffectRecorded("Sol Ring"),
        CostPaid(mana("{1}"), tapped=("Sol Ring",)),
        CardMoved("Forest", "graveyard", "hand"),
        TokensCreated("Treasure", 2),
        CardsDrawn(("Island",)),
        CardsDiscarded(("Island",)),
        Tapped(("Forest",)),
        Untapped(("Forest",)),
        ManaAdded("{G}"),
        CountersChanged("Llanowar Elves", "+1/+1", 1, 1),
        LifeChanged(-2, 38),
        DamageAdded(6, 28),
        LibraryShuffled(),
        AlreadySo("Forest", AlreadySoKind.ALREADY_TAPPED),
        InstanceChosen("Forest", "c4"),
        CardsRevealed("ch1", "look", revealed),
        NothingRevealed("search"),
        ChoiceResolved((Placement("Island", "hand"),)),
        AttackDeclared(("Grizzly Bears",), (), (), ("Grizzly Bears",)),
        CombatDamageDealt((AttackerDamage("Grizzly Bears", 2),), 2, ()),
        AssumptionMade(AssumptionKind.SNOW_AS_GENERIC),
        ReminderIssued(Step.UPKEEP, (("Phyrexian Arena", 1),)),
        AdvanceStopped(StopReason.REMINDER, Step.UPKEEP, Step.MAIN1),
        ExpectationMismatched("life", "38", "40"),
        NoticeRaised(NoticeKind.LIFE),
        ChecksOverridden((FailedCheck(CheckKind.LAND_DROP_USED, "Forest", number=1),), "fetch"),
        GameEnded("win", "fast"),
        AlreadyApplied(4),
        SnapshotWritten(3),
        StateListed("summary"),
        LogExported(1, 0, 0),
        Refused((Error(ErrorKind.UNKNOWN_GAME, "gabc"),), ()),
    ]


# @spec TOOL-026
def test_the_samples_cover_every_event_type() -> None:
    assert {type(event) for event in sample_of_every_event()} == set(get_args(Event))


# @spec TOOL-026
@pytest.mark.parametrize("event", sample_of_every_event(), ids=lambda e: type(e).__name__)
def test_every_event_type_has_a_rendering(event: Event) -> None:
    rendered = event_lines(event)
    assert len([line for line in rendered if line.strip()]) == len(rendered) > 0


ERROR_FACTS = Error(
    ErrorKind.UNKNOWN_GAME,
    subject="Forest",
    zone="hand",
    found_in="graveyard",
    names=("a", "b"),
    number=3,
    expected=2,
)
CHECK_FACTS = FailedCheck(
    CheckKind.COST_NOT_PAYABLE,
    subject="Forest",
    names=("G",),
    cost=mana("{2}{G}"),
    number=3,
    expected=2,
    step=Step.UPKEEP,
)


# @spec TOOL-026
def test_every_kind_of_error_has_its_own_wording() -> None:
    worded = {error_text(replace(ERROR_FACTS, kind=kind)) for kind in ErrorKind}
    assert len(worded) == len(ErrorKind)


# @spec TOOL-026
def test_every_kind_of_rule_check_has_its_own_wording() -> None:
    worded = {check_text(replace(CHECK_FACTS, kind=kind)) for kind in CheckKind}
    assert len(worded) == len(CheckKind)


# @spec TOOL-026
def test_a_card_missing_from_a_zone_says_where_it_is_instead() -> None:
    error = Error(
        ErrorKind.CARD_NOT_IN_ZONE, "Forest", zone="hand or command", found_in="graveyard"
    )
    assert error_text(error) == "No Forest in hand or command; it is in the graveyard."


# @spec TOOL-026
def test_a_stale_change_number_says_where_the_game_is_now() -> None:
    error = Error(ErrorKind.STALE_CHANGE, number=42)
    assert error_text(error) == (
        "The game is now at change #42, so your picture of it is stale."
        " Check the latest status line or call get_state, then send the call with after=42."
    )


# @spec APP-020
def test_an_internal_failure_says_it_was_inside_the_service_and_not_caused_by_the_call() -> None:
    text = error_text(Error(ErrorKind.INTERNAL_FAILURE))
    assert ("inside the service" in text, "not caused by the call" in text) == (True, True)
