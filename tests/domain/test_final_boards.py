"""Every seat's state at the end of a contested game: `final` in the outcome of the tested
seat's `end_game` entry."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from mtg_goldfishing.domain.events import EliminationCause
from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.elimination import eliminate
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.records.export import log_entry_to_data, snapshot_to_data
from mtg_goldfishing.domain.records.log import log_entry
from mtg_goldfishing.domain.records.snapshots import take_snapshot
from mtg_goldfishing.domain.steps import Step
from tests.support.acting import S1, S2, S3, acted
from tests.support.builders import Situation, a_game

ATRAXA = "Atraxa, Praetors' Voice"
THRASIOS = "Thrasios, Triton Hero"
TYMNA = "Tymna the Weaver"
VALKI = "Valki, God of Lies // Tibalt, Cosmic Impostor"
ENDING = {"result": "stalled", "notes": "even"}
NOT_YET = pytest.mark.xfail(strict=True, reason="M5: not implemented yet")


def a_table() -> Situation:
    """Seat 1's turn in table turn 5. Seat 1 plays Atraxa, seat 2 Thrasios and Tymna, seat 3
    no commander; each holds cards in its hand, battlefield and graveyard."""
    builder: Any = (
        a_game()
        .in_step(Step.MAIN1, turn=5)
        .in_turn_of(1)
        .with_commander(ATRAXA)
        .with_hand("Sol Ring", "Island")
        .with_battlefield("Forest", tapped=True, counters={"charge": 1})
        .with_battlefield("Llanowar Elves")
        .with_graveyard("Cultivate")
        .with_commander_damage(ATRAXA, 2, 4)
        .with_commander_damage(ATRAXA, 3, 2)
    )
    builder = (
        builder.and_an_opposing_seat()
        .with_commander(THRASIOS, TYMNA)
        .with_life(33)
        .with_hand("Lightning Bolt")
        .with_battlefield("Mountain")
        .with_graveyard("Ponder")
        .with_commander_damage(THRASIOS, 1, 6)
    )
    builder = builder.and_an_opposing_seat().with_hand("Counterspell").with_battlefield("Island")
    return builder.build()


def ended(situation: Situation, decks: Decks | None = None) -> dict[str, Any]:
    """The tested seat ends the game; its log entry as data."""
    before = situation.game
    result = end_game(before, situation.deck, S1, result="stalled", notes="even", decks=decks)
    applied = accept_change(acted(situation, result), S1, "end_game", ENDING)
    entry = log_entry(
        tool="end_game",
        arguments=ENDING,
        before=before,
        after=applied.game,
        summary=applied.summary,
        events=applied.events,
        seat=S1,
        final=applied.final,
    )
    return log_entry_to_data(entry)


def final_of(entry: dict[str, Any], seat: int) -> dict[str, Any]:
    (found,) = [each for each in entry["outcome"]["final"] if each["seat"] == seat]
    return dict(found)


def per_seat_decks(situation: Situation) -> Decks:
    """Each seat its own deck, with only that seat's commanders."""
    deck = situation.deck
    return Decks(
        {
            S1: replace(deck, commanders=(ATRAXA,)),
            S2: replace(deck, commanders=(THRASIOS, TYMNA)),
            S3: replace(deck, commanders=()),
        }
    )


# ------------------------------------------------------------------ one object per seat


# @spec REC-097
@NOT_YET
def test_the_tested_seat_s_end_game_records_every_seat_in_ascending_seat_number() -> None:
    entry = ended(a_table())
    assert [each["seat"] for each in entry["outcome"]["final"]] == [1, 2, 3]


# @spec REC-097
@NOT_YET
def test_final_sits_beside_the_result_and_notes() -> None:
    entry = ended(a_table())
    assert set(entry["outcome"]) == {"result", "notes", "final"}
    assert (entry["outcome"]["result"], entry["outcome"]["notes"]) == ("stalled", "even")


# @spec REC-097, REC-100
@NOT_YET
def test_an_eliminated_seat_is_listed_in_final() -> None:
    situation = a_table()
    eliminate(situation.game, S3, EliminationCause.CONCEDE)
    entry = ended(situation, per_seat_decks(situation))
    assert [each["seat"] for each in entry["outcome"]["final"]] == [1, 2, 3]


# ------------------------------------------------------------------ what each object holds


# @spec REC-098
@NOT_YET
def test_a_seat_s_final_object_holds_exactly_its_state_fields() -> None:
    assert set(final_of(ended(a_table()), 2)) == {
        "seat",
        "life",
        "eliminated",
        "hand",
        "battlefield",
        "graveyard",
        "commander_damage_taken",
    }


# @spec REC-098
@NOT_YET
def test_final_records_each_seat_s_life_and_whether_it_is_eliminated() -> None:
    seat = final_of(ended(a_table()), 2)
    assert (seat["life"], seat["eliminated"]) == (33, False)


# @spec REC-098
@NOT_YET
def test_final_records_a_seat_s_hand_and_graveyard_by_card_name() -> None:
    seat = final_of(ended(a_table()), 1)
    assert (seat["hand"], seat["graveyard"]) == (["Sol Ring", "Island"], ["Cultivate"])


# @spec REC-098
@NOT_YET
def test_final_records_each_permanent_with_its_tapped_state_and_counters() -> None:
    seat = final_of(ended(a_table()), 1)
    assert seat["battlefield"] == [
        {"name": "Forest", "tapped": True, "counters": {"charge": 1}},
        {"name": "Llanowar Elves", "tapped": False, "counters": {}},
    ]


# @spec REC-098
@NOT_YET
def test_a_permanent_is_recorded_under_the_seat_that_controls_it() -> None:
    builder: Any = a_table_builder_with_a_stolen_elf()
    entry = ended(builder.build())
    names = {seat: [p["name"] for p in final_of(entry, seat)["battlefield"]] for seat in (1, 2)}
    assert names == {1: ["Forest", "Llanowar Elves", "Grizzly Bears"], 2: ["Mountain"]}


def a_table_builder_with_a_stolen_elf() -> Any:
    """Seat 1's Forest and Elves; seat 2's Mountain, and its Grizzly Bears that seat 1
    controls."""
    return (
        a_game()
        .in_turn_of(1)
        .with_battlefield("Forest", "Llanowar Elves")
        .and_an_opposing_seat()
        .with_battlefield("Mountain", "Grizzly Bears")
        .controlled_by("Grizzly Bears", 1)
    )


# @spec REC-098
@NOT_YET
def test_final_names_and_lists_a_seat_s_cards_as_a_snapshot_of_that_seat_does() -> None:
    builder: Any = (
        a_game()
        .in_turn_of(1)
        .with_hand("Lightning Bolt", "Forest")
        .with_battlefield(VALKI, "Island")
        .with_graveyard("Ponder", "Cultivate")
        .and_an_opposing_seat()
        .with_battlefield("Mountain")
    )
    situation = builder.build()
    snapshot = take_snapshot(situation.game.copy(), situation.deck)
    assert snapshot is not None
    described = snapshot_to_data(snapshot)
    seat = final_of(ended(situation), 1)
    assert (seat["hand"], seat["battlefield"], seat["graveyard"]) == (
        [card["name"] for card in described["hand"]],  # type: ignore[attr-defined]
        described["battlefield"],
        described["graveyard"],
    )


# ------------------------------------------------------------------ commander damage taken


# @spec REC-099
@NOT_YET
def test_commander_damage_taken_maps_every_other_seat_to_each_of_its_commanders() -> None:
    seat = final_of(ended(a_table()), 1)
    assert seat["commander_damage_taken"] == {"2": {THRASIOS: 6, TYMNA: 0}, "3": {}}


# @spec REC-099
@NOT_YET
def test_commander_damage_taken_includes_commanders_that_dealt_no_damage() -> None:
    seat = final_of(ended(a_table()), 3)
    assert seat["commander_damage_taken"] == {"1": {ATRAXA: 2}, "2": {THRASIOS: 0, TYMNA: 0}}


# @spec REC-099
@NOT_YET
def test_commander_damage_taken_includes_an_eliminated_seat_s_commanders() -> None:
    situation = a_table()
    eliminate(situation.game, S2, EliminationCause.CONCEDE)
    seat = final_of(ended(situation, per_seat_decks(situation)), 1)
    assert seat["commander_damage_taken"] == {"2": {THRASIOS: 6, TYMNA: 0}, "3": {}}


# ------------------------------------------------------------------ an eliminated seat


# @spec REC-100
@NOT_YET
def test_an_eliminated_seat_s_final_object_holds_empty_zones_and_the_life_it_left_at() -> None:
    situation = a_table()
    acted(
        situation,
        effect(
            situation.game,
            situation.deck,
            S1,
            source="Fireball",
            delta={"damage": {"3": 45}},
            immediate=True,
        ),
    )
    seat = final_of(ended(situation, per_seat_decks(situation)), 3)
    assert seat == {
        "seat": 3,
        "life": -5,
        "eliminated": True,
        "hand": [],
        "battlefield": [],
        "graveyard": [],
        "commander_damage_taken": {"1": {ATRAXA: 2}, "2": {THRASIOS: 0, TYMNA: 0}},
    }


# ------------------------------------------------------------------ where final is not


# @spec REC-101
def test_a_goldfish_game_s_end_game_entry_holds_no_final() -> None:
    situation = a_game().build()
    before = situation.game
    result = end_game(before, situation.deck, S1, result="win", notes="fast")
    applied = accept_change(acted(situation, result), S1, "end_game", {"result": "win"})
    entry = log_entry(
        tool="end_game",
        arguments={"result": "win"},
        before=before,
        after=applied.game,
        summary=applied.summary,
        events=applied.events,
        final=applied.final,
    )
    assert log_entry_to_data(entry)["outcome"] == {"result": "win", "notes": "fast"}


# @spec REC-101
def test_a_concession_s_entry_holds_no_final() -> None:
    situation = a_table()
    before = situation.game
    result = end_game(before, situation.deck, S2, result="loss", notes="beaten")
    applied = accept_change(acted(situation, result), S2, "end_game", {"result": "loss"})
    entry = log_entry(
        tool="end_game",
        arguments={"result": "loss"},
        before=before,
        after=applied.game,
        summary=applied.summary,
        events=applied.events,
        seat=S2,
        final=applied.final,
    )
    assert "final" not in log_entry_to_data(entry)["outcome"]


# @spec REC-102
@NOT_YET
def test_final_is_held_in_the_outcome_and_in_no_public_or_private_event() -> None:
    entry = ended(a_table())
    events = json.dumps({"public": entry["public"], "private": entry["private"]})
    assert "final" in entry["outcome"]
    assert '"final"' not in events


# ------------------------------------------------------------------ the stack at the end


# @spec REC-103
@NOT_YET
def test_a_spell_left_on_the_stack_is_in_no_zone_of_final_and_its_item_is_removed() -> None:
    builder: Any = (
        a_game()
        .in_turn_of(1)
        .with_hand("Island")
        .with_battlefield("Mountain")
        .and_an_opposing_seat()
        .with_battlefield("Island")
        .with_spell_on_stack("Lightning Bolt")
    )
    situation = builder.build()
    (item,) = situation.game.stack
    entry = ended(situation)
    zones = [
        card if isinstance(card, str) else card["name"]
        for seat in entry["outcome"]["final"]
        for zone in ("hand", "battlefield", "graveyard")
        for card in seat[zone]
    ]
    assert "Lightning Bolt" not in zones
    assert entry["removed"] == [item.id]
