"""Turn snapshots: what a turn ended with."""

from __future__ import annotations

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.results import Applied
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.playing import play
from mtg_goldfishing.domain.reading.model import CardReading, FaceReading
from mtg_goldfishing.domain.records.model import HandCard, PermanentRecord, ReminderRecord
from mtg_goldfishing.domain.records.snapshots import take_snapshot
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.builders import Situation, a_game


def snapshot_at_cleanup(situation: Situation):  # type: ignore[no-untyped-def]
    result = advance(situation.game, situation.deck, to="cleanup")
    assert isinstance(result, Applied), result
    (snapshot,) = result.snapshots
    return snapshot


# @spec REC-011
def test_entering_cleanup_writes_a_snapshot_of_the_turn() -> None:
    situation = (
        a_game()
        .in_step(Step.MAIN2, turn=5)
        .with_commander("Atraxa, Praetors' Voice")
        .with_battlefield("Forest", tapped=True)
        .with_battlefield("Grizzly Bears", counters={"+1/+1": 1})
        .with_hand("Cultivate")
        .with_graveyard("Ponder")
        .with_land_drops_used(1)
        .with_life(33)
        .build()
    )
    situation.game.damage_dealt = 14
    snapshot = snapshot_at_cleanup(situation)
    assert snapshot.turn == 5
    assert snapshot.hand == (HandCard("Cultivate", payable=False),)
    assert snapshot.battlefield == (
        PermanentRecord("Forest", True),
        PermanentRecord("Grizzly Bears", False, (("+1/+1", 1),)),
    )
    assert snapshot.graveyard == ("Ponder",)
    assert (snapshot.lands, snapshot.land_drop_made) == (1, True)
    assert (snapshot.life, snapshot.damage_dealt) == (33, 14)
    assert snapshot.commander_damage == (("Atraxa, Praetors' Voice", (0, 0, 0)),)


# @spec REC-011
def test_a_snapshot_lists_reminders_that_went_unanswered() -> None:
    situation = a_game().in_step(Step.UNTAP, turn=5).with_battlefield("Phyrexian Arena").build()
    moved = advance(situation.game, situation.deck, to="upkeep")
    assert isinstance(moved, Applied)
    situation.game = moved.game
    snapshot = snapshot_at_cleanup(situation)
    assert [(r.card, r.step) for r in snapshot.unanswered_reminders] == [
        ("Phyrexian Arena", Step.UPKEEP)
    ]
    assert isinstance(snapshot.unanswered_reminders[0], ReminderRecord)


# @spec REC-012
def test_ending_a_game_mid_turn_writes_that_turn_a_snapshot() -> None:
    situation = a_game().in_step(Step.MAIN1, turn=4).build()
    result = end_game(situation.game, situation.deck, result="win", notes="")
    assert isinstance(result, Applied)
    assert [s.turn for s in result.snapshots] == [4]


# @spec REC-013
def test_a_turn_has_at_most_one_snapshot() -> None:
    situation = a_game().in_step(Step.MAIN2, turn=4).build()
    snapshot_at_cleanup(situation)
    situation.game.snapshot_turns.append(4)
    assert take_snapshot(situation.game, situation.deck) is None
    result = end_game(situation.game, situation.deck, result="win", notes="")
    assert isinstance(result, Applied)
    assert result.snapshots == ()


# @spec REC-014
def test_a_card_left_in_hand_is_payable_when_all_usable_sources_untapped_could_cast_it() -> None:
    situation = (
        a_game()
        .in_step(Step.MAIN2)
        .with_battlefield("Forest", "Forest", "Forest", tapped=True)
        .with_battlefield("Lotus Petal")
        .with_hand("Cultivate", "Shivan Dragon", "Island")
        .build()
    )
    snapshot = snapshot_at_cleanup(situation)
    assert snapshot.hand == (
        HandCard("Cultivate", payable=True),
        HandCard("Shivan Dragon", payable=False),
        HandCard("Island", payable=True),
    )


# @spec REC-015
def test_mana_available_is_counted_on_entering_the_first_main_step() -> None:
    situation = (
        a_game()
        .in_step(Step.DRAW, turn=4)
        .with_battlefield("Forest", "Sol Ring")
        .with_battlefield("Lotus Petal")
        .build()
    )
    result = advance(situation.game, situation.deck)
    assert isinstance(result, Applied)
    assert result.game.turn_stats.mana_available == 3


# @spec REC-016
def test_mana_spent_counts_mana_symbols_paid_but_not_life() -> None:
    situation = (
        a_game()
        .in_step(Step.MAIN1)
        .with_battlefield("Swamp", "Forest", "Forest")
        .with_hand("Dismember", "Grizzly Bears")
        .build()
    )
    for card in ("Dismember", "Grizzly Bears"):
        result = play(situation.game, situation.deck, card=card)
        assert isinstance(result, Applied), result
        situation.game = result.game
    snapshot = snapshot_at_cleanup(situation)
    assert snapshot.mana_spent == 3


# @spec REC-015
def test_mana_available_ignores_tapped_state_and_summoning_sickness() -> None:
    situation = (
        a_game()
        .in_step(Step.DRAW, turn=4)
        .with_battlefield("Forest", tapped=True)
        .with_battlefield("Llanowar Elves", entered_turn=4)
        .build()
    )
    result = advance(situation.game, situation.deck)
    assert isinstance(result, Applied)
    assert result.game.turn_stats.mana_available == 2


# @spec REC-016
def test_mana_spent_counts_a_generic_symbol_as_its_number() -> None:
    big = Card("Big Beast", (Face("Big Beast", ManaString.parse("{4}{G}"), "Creature — Beast"),))
    situation = (
        a_game()
        .in_step(Step.MAIN1)
        .with_card(big, CardReading((FaceReading(),)))
        .with_battlefield(*("Forest",) * 5)
        .with_hand("Big Beast")
        .build()
    )
    result = play(situation.game, situation.deck, card="Big Beast")
    assert isinstance(result, Applied), result
    situation.game = result.game
    assert snapshot_at_cleanup(situation).mana_spent == 5


# @spec REC-014
def test_payable_pays_phyrexian_symbols_with_mana_not_life() -> None:
    situation = (
        a_game().in_step(Step.MAIN2).with_battlefield("Forest").with_hand("Dismember").build()
    )
    snapshot = snapshot_at_cleanup(situation)
    assert snapshot.hand == (HandCard("Dismember", payable=False),)
