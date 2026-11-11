"""The records of a contested game: what each log entry says about the seats, its public and
private events, seat ids kept out of every record, and reminders judged per seat."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.game import creation
from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.mulligan import mulligan
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.records.export import (
    call_record_to_data,
    game_to_data,
    log_entry_to_data,
    snapshot_to_data,
)
from mtg_goldfishing.domain.records.log import log_entry
from mtg_goldfishing.domain.records.reminders import judge_reminders
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted
from tests.support.builders import Situation, a_game
from tests.support.library import LIBRARY
from tests.support.stored import (
    a_call,
    a_contested_log_entry,
    a_contested_reminder,
    a_log_entry,
    a_snapshot,
)

ATRAXA = "Atraxa, Praetors' Voice"
CONTESTED_ONLY = (
    "seat",
    "active",
    "table_turn",
    "round",
    "stacked",
    "resolved",
    "countered",
    "removed",
    "auto_passes",
    "no_blocks",
    "eliminated",
    "public",
    "private",
    "lives",
    "seats",
)


def a_table(seats: int = 3, *, active: int = 1, step: Step = Step.MAIN1) -> Situation:
    """Seat `active`'s turn 2 of its own (table turn 5, round 2); every seat holds an Island,
    has a Forest on its battlefield and Forests in its library."""
    builder: Any = a_game().in_step(step, turn=5).in_round(2).in_turn_of(active).with_turns_taken(2)
    for number in range(1, seats + 1):
        if number > 1:
            builder = builder.and_an_opposing_seat().with_turns_taken(2 if number < active else 1)
        builder = builder.with_hand("Island").with_battlefield("Forest")
        builder = builder.with_library("Forest", "Forest")
    return builder.build()


def logged(
    situation: Situation,
    seat: SeatNumber,
    tool: str,
    arguments: Mapping[str, object],
    result: object,
) -> Any:
    """The log entry of a seat's applied call, counted as the game's next change."""
    before = situation.game
    applied = accept_change(acted(situation, result), seat, tool, arguments)
    build: Any = log_entry
    return build(
        tool=tool,
        arguments=arguments,
        before=before,
        after=applied.game,
        summary=applied.summary,
        events=applied.events,
        seat=seat,
    )


def an_effect(situation: Situation, seat: SeatNumber, delta: object, **more: object) -> Any:
    arguments = {"game_id": situation.game.seat(seat).seat_id.value, "source": "x", **more}
    result = effect(situation.game, situation.deck, seat, source="x", delta=delta)
    return logged(situation, seat, "effect", {**arguments, "delta": delta}, result)


def data(entry: Any) -> dict[str, Any]:
    return log_entry_to_data(entry)


def kinds(events: Any) -> list[str]:
    return [type(event).__name__ for event in events]


# ------------------------------------------------------------------ the seats of an entry


# @spec REC-028
def test_an_entry_records_the_seat_whose_call_it_records() -> None:
    situation = a_table(active=2)
    assert data(an_effect(situation, S2, {"life": 1}))["seat"] == 2


# @spec REC-029
def test_an_entry_records_the_active_seat_when_the_call_was_made() -> None:
    situation = a_table(active=2)
    assert data(an_effect(situation, S2, {"life": 1}))["active"] == 2


# @spec REC-030
def test_an_entry_s_turn_is_the_active_seat_s_own_turn_number() -> None:
    situation = a_table(active=2)
    entry = an_effect(situation, S2, {"life": 1})
    assert data(entry)["turn"] == situation.game.seat(S2).turns == 1


# @spec REC-031
def test_an_entry_records_the_table_turn_and_round_before_the_call() -> None:
    situation = a_table(step=Step.CLEANUP)
    entry = logged(situation, S1, "advance", {}, advance(situation.game, situation.deck, S1))
    assert (data(entry)["table_turn"], data(entry)["round"]) == (5, 2)
    assert situation.game.turn == 6


# @spec REC-029, REC-030, REC-031
def test_a_mulligan_entry_has_no_active_seat_and_turn_table_turn_and_round_0() -> None:
    builder: Any = a_game().in_mulligan().with_hand(*["Island"] * 7)
    builder = builder.with_library(*["Forest"] * 7).and_an_opposing_seat()
    situation = builder.with_hand(*["Island"] * 7).with_library(*["Forest"] * 7).build()
    result = mulligan(situation.game, situation.deck, S2, keep=False)
    recorded = data(logged(situation, S2, "mulligan", {"keep": False}, result))
    assert (recorded["active"], recorded["turn"], recorded["table_turn"], recorded["round"]) == (
        None,
        0,
        0,
        0,
    )


# @spec REC-039
def test_an_entry_records_each_seat_its_call_eliminated_and_why() -> None:
    situation = a_table()
    entry = an_effect(situation, S1, {"damage": {"2": 40, "3": 40}})
    assert data(entry)["eliminated"] == [
        {"seat": 2, "cause": "life"},
        {"seat": 3, "cause": "life"},
    ]


# @spec REC-077
def test_a_seat_at_0_life_and_21_commander_damage_is_recorded_as_eliminated_for_life() -> None:
    builder: Any = a_game().with_commander(ATRAXA).with_commander_damage(ATRAXA, 2, 21)
    situation = builder.and_an_opposing_seat().with_hand("Island").build()
    entry = an_effect(situation, S1, {"damage": {"2": 40}})
    assert data(entry)["eliminated"] == [{"seat": 2, "cause": "life"}]


# @spec REC-039, REC-080
def test_a_concession_records_a_null_result_the_notes_and_the_seat_as_conceding() -> None:
    situation = a_table()
    arguments = {"result": "loss", "notes": "beaten"}
    result = end_game(situation.game, situation.deck, S2, result="loss", notes="beaten")
    recorded = data(logged(situation, S2, "end_game", arguments, result))
    assert recorded["outcome"] == {"result": None, "notes": "beaten"}
    assert recorded["eliminated"] == [{"seat": 2, "cause": "concede"}]
    assert recorded["arguments"]["result"] == "loss"


# @spec REC-038
def test_an_attacked_seat_declared_no_blocks_for_is_recorded_in_no_blocks() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    situation = builder.build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    result = advance(situation.game, situation.deck, S1, to="declare_blockers")
    entry = logged(situation, S1, "advance", {"to": "declare_blockers"}, result)
    assert data(entry)["no_blocks"] == [2]


# @spec REC-041
def test_a_reminder_recorded_on_an_entry_names_the_seat_it_was_issued_to() -> None:
    builder: Any = a_game().in_step(Step.UNTAP, turn=5).in_turn_of(2).and_an_opposing_seat()
    situation = builder.with_battlefield("Phyrexian Arena").with_library("Forest").build()
    result = advance(situation.game, situation.deck, S2, to="main1")
    (reminder,) = data(logged(situation, S2, "advance", {"to": "main1"}, result))["reminders"]
    assert (reminder["card"], reminder["seat"]) == ("Phyrexian Arena", 2)


# ------------------------------------------------------------------ public and private events


# @spec REC-040, REC-068
def test_an_entry_stores_the_public_form_of_its_summary_and_events() -> None:
    situation = a_table()
    entry = an_effect(situation, S1, {"draw": 1})
    public = entry.contested.public
    assert kinds(public)[0] == "EffectRecorded"
    assert "HiddenCardsDrawn" in kinds(public)
    assert "CardsDrawn" not in kinds(public)


# @spec REC-067, REC-078
def test_an_entry_stores_for_the_seat_whose_turn_it_began_what_that_seat_drew() -> None:
    situation = a_table(step=Step.CLEANUP)
    entry = logged(situation, S1, "advance", {}, advance(situation.game, situation.deck, S1))
    (private,) = entry.contested.private
    assert private.seat == S2
    assert len(private.events) == len(entry.contested.public)
    (drawn,) = [event for event in private.events if type(event).__name__ == "CardsDrawn"]
    assert drawn.cards == ("Forest",)


# @spec REC-078
def test_an_entry_has_no_private_events_for_the_seat_that_made_the_call() -> None:
    situation = a_table()
    entry = an_effect(situation, S1, {"draw": 1})
    assert entry.contested.private == ()


# @spec REC-040
def test_the_exported_public_events_are_json_ready_data() -> None:
    situation = a_table()
    exported = data(an_effect(situation, S1, {"draw": 1}))
    assert exported["public"][0]["type"] == "EffectRecorded"
    assert exported["private"] == {}


# ------------------------------------------------------------------ outcomes


def a_contested_game() -> Any:
    deck: Any = a_game().with_commander(ATRAXA).with_library(*["Forest"] * 10).build().deck
    opposing: Any = creation.OpposingDeck
    return creation.new_game(
        deck,
        deck_id=deck.deck_id,
        game_id="gabcdefghij",
        seed=3,
        turn_limit=None,
        draw_first_turn=None,
        opposing=[opposing(deck.deck_id, deck, "gseatnumber2")],
        starting_life=None,
        position=1,
    )


# @spec REC-060, REC-061, REC-062
def test_the_new_game_entry_names_no_seat_and_holds_every_seat_s_hand_and_no_events() -> None:
    created = a_contested_game()
    game = created.game
    applied = accept_change(created, game.tested.number, "new_game", {})
    build: Any = log_entry
    entry = build(
        tool="new_game",
        arguments={},
        before=None,
        after=applied.game,
        summary=applied.summary,
        events=applied.events,
        seat=None,
    )
    recorded = data(entry)
    hands = {
        str(seat.number.value): [card.name for card in game.hand_of(seat.number)]
        for seat in game.seats
    }
    assert recorded["seat"] is None
    assert recorded["outcome"] == {"hand": hands}
    assert (recorded["public"], recorded["private"]) == ([], {})


def blocked_by(situation: Situation, blocks: object) -> Any:
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    acted(situation, advance(situation.game, situation.deck, S1, to="declare_blockers"))
    choice = situation.game.pending[0].choice_id
    arguments = {"choice_id": choice, "blocks": blocks}
    result = choose(situation.game, situation.deck, S2, choice_id=choice, blocks=blocks)
    return logged(situation, S2, "choose", arguments, result)


def a_duel_with_a_blocker() -> Situation:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    return builder.with_battlefield("Llanowar Elves").build()


# @spec REC-073
def test_a_blocks_answer_records_each_blocker_by_name_and_id_and_the_attacker_it_blocks() -> None:
    situation = a_duel_with_a_blocker()
    elves = next(c for c in situation.game.cards if c.name == "Llanowar Elves")
    bears = next(c for c in situation.game.cards if c.name == "Grizzly Bears")
    entry = blocked_by(situation, {"Llanowar Elves": "Grizzly Bears"})
    assert data(entry)["outcome"] == {
        "blocks": {
            elves.id: {
                "blocker": "Llanowar Elves",
                "attacker": "Grizzly Bears",
                "attacker_id": bears.id,
            }
        }
    }


# @spec REC-073
def test_a_blocks_answer_with_no_blocks_records_an_empty_map() -> None:
    situation = a_duel_with_a_blocker()
    assert data(blocked_by(situation, {}))["outcome"] == {"blocks": {}}


# @spec REC-074
def test_an_ask_answer_records_no_outcome() -> None:
    situation = a_table()
    an_effect(situation, S1, {"ask": [{"seats": [2], "text": "discard a card"}]})
    choice = situation.game.pending[0].choice_id
    delta = {"discard": ["Island"]}
    result = choose(situation.game, situation.deck, S2, choice_id=choice, delta=delta)
    entry = logged(situation, S2, "choose", {"choice_id": choice, "delta": delta}, result)
    assert data(entry)["outcome"] is None
    assert data(entry)["seat"] == 2


# @spec REC-072
def test_a_hand_answer_records_where_each_revealed_card_went() -> None:
    situation = a_table()
    recorded_look = effect(
        situation.game, situation.deck, S1, source="x", delta={"look_at_hand": 2}
    )
    acted(situation, recorded_look)
    choice = situation.game.pending[0].choice_id
    selections = {"graveyard": ["Island"]}
    result = choose(situation.game, situation.deck, S1, choice_id=choice, selections=selections)
    entry = logged(situation, S1, "choose", {"choice_id": choice, "selections": selections}, result)
    assert data(entry)["outcome"] == {"placements": [{"card": "Island", "to": "graveyard"}]}


# @spec REC-075
def test_an_attack_records_the_attackers_and_the_seat_each_attacks_and_no_blocked_list() -> None:
    situation = a_duel_with_a_blocker()
    arguments = {"attackers": ["Grizzly Bears"], "targets": 2}
    result = attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"], targets=2)
    entry = logged(situation, S1, "attack", arguments, result)
    assert data(entry)["outcome"] == {
        "attackers": ["Grizzly Bears"],
        "targets": [{"attacker": "Grizzly Bears", "seat": 2}],
    }


# @spec REC-076
def test_entering_combat_damage_records_each_attacker_s_damage_and_the_seat_dealt_it() -> None:
    builder: Any = a_game().with_battlefield("Grizzly Bears").and_an_opposing_seat()
    situation = builder.build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"]))
    result = advance(situation.game, situation.deck, S1, to="combat_damage")
    entry = logged(situation, S1, "advance", {"to": "combat_damage"}, result)
    assert data(entry)["outcome"] == {
        "damage": [{"attacker": "Grizzly Bears", "damage": 2, "seat": 2}]
    }


# ------------------------------------------------------------------ seat ids in records


def an_opposing_call(situation: Situation, reason: str) -> Any:
    seat_id = situation.game.seat(S2).seat_id.value
    delta = {"ask": [{"seats": [3], "text": f"{situation.game.seat(S3).seat_id.value} discards"}]}
    arguments = {"game_id": seat_id, "source": "x", "delta": delta, "reason": reason}
    result = effect(situation.game, situation.deck, S2, source="x", delta=delta)
    return logged(situation, S2, "effect", arguments, result)


# @spec REC-058
def test_an_opposing_seat_s_entry_stores_the_game_id_as_its_game_id_argument() -> None:
    situation = a_table(active=2)
    entry = an_opposing_call(situation, "as planned")
    assert data(entry)["arguments"]["game_id"] == situation.game.game_id


# @spec REC-057, REC-065
def test_an_opposing_seat_id_written_anywhere_in_an_entry_is_redacted() -> None:
    situation = a_table(active=2)
    third = situation.game.seat(S3).seat_id.value
    entry = an_opposing_call(situation, f"told by {third} to")
    recorded = data(entry)
    assert recorded["reason"] == "told by [redacted] to"
    assert recorded["arguments"]["delta"]["ask"][0]["text"] == "[redacted] discards"
    assert third not in repr(entry)
    assert situation.game.seat(S2).seat_id.value not in repr(entry)


# ------------------------------------------------------------------ reminders


# @spec REC-043
def test_a_reminder_is_answered_by_an_effect_of_the_reminded_seat_in_the_same_table_turn() -> None:
    issued = a_contested_log_entry(5, seat=1, table_turn=3, reminders=(a_contested_reminder(1, 3),))
    answer = a_contested_log_entry(6, seat=1, table_turn=3, source="Phyrexian Arena")
    (judged,) = judge_reminders([issued, answer])
    assert judged.answered


# @spec REC-043
def test_an_effect_of_another_seat_does_not_answer_a_seat_s_reminder() -> None:
    issued = a_contested_log_entry(5, seat=1, table_turn=3, reminders=(a_contested_reminder(1, 3),))
    other = a_contested_log_entry(6, seat=2, table_turn=3, source="Phyrexian Arena")
    (judged,) = judge_reminders([issued, other])
    assert not judged.answered


# @spec REC-043
def test_an_effect_in_a_later_table_turn_does_not_answer_a_reminder() -> None:
    issued = a_contested_log_entry(5, seat=1, table_turn=3, reminders=(a_contested_reminder(1, 3),))
    late = a_contested_log_entry(9, seat=1, table_turn=5, source="Phyrexian Arena")
    (judged,) = judge_reminders([issued, late])
    assert not judged.answered


# ------------------------------------------------------------------ goldfish records


# @spec REC-042
def test_a_goldfish_entry_has_none_of_the_fields_only_a_contested_game_has() -> None:
    assert set(log_entry_to_data(a_log_entry(1))) & set(CONTESTED_ONLY) == set()


# @spec REC-042
def test_a_goldfish_snapshot_has_none_of_the_fields_only_a_contested_game_has() -> None:
    exported = snapshot_to_data(a_snapshot(1, written_by=2))
    assert set(exported) & set(CONTESTED_ONLY) == set()


# @spec REC-042
def test_a_goldfish_call_record_stores_no_seat_number() -> None:
    assert "seat" not in call_record_to_data(a_call("gtest000001", 1))


# @spec REC-042
def test_the_get_log_header_of_a_goldfish_game_has_none_of_the_contested_fields() -> None:
    game = a_game().build().game
    assert set(game_to_data(game)) & {"table_turn", "round", "seats"} == set()


# A card used in these tests that the library must know.
assert "Phyrexian Arena" in LIBRARY
