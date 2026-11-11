"""The records of the stack: an entry naming the item its call stacked, the items a call
resolved, countered or removed, automatic passes, and a `pass` on a reminder."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from mtg_goldfishing.domain.game.calls import accept_change
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.records.export import log_entry_to_data
from mtg_goldfishing.domain.records.log import log_entry
from mtg_goldfishing.domain.records.reminders import judge_reminders
from mtg_goldfishing.domain.stack.passing import pass_
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, acted
from tests.support.builders import Situation
from tests.support.tables import a_table, bolt_at, three_seats, two_seats

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M4: not built")


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
    return log_entry(
        tool=tool,
        arguments=arguments,
        before=before,
        after=applied.game,
        summary=applied.summary,
        events=applied.events,
        seat=seat,
    )


def data(entry: Any) -> dict[str, Any]:
    return log_entry_to_data(entry)


def a_cast(situation: Situation, seat: SeatNumber, card: str, **arguments: Any) -> Any:
    result = play(situation.game, situation.deck, seat, card=card, **arguments)
    return logged(situation, seat, "play", {"card": card, **arguments}, result)


def a_pass(situation: Situation, seat: SeatNumber) -> Any:
    result = pass_(situation.game, situation.deck, seat)
    return logged(situation, seat, "pass", {}, result)


def an_effect(situation: Situation, seat: SeatNumber, delta: object, **arguments: Any) -> Any:
    result = effect(situation.game, situation.deck, seat, source="x", delta=delta, **arguments)
    return logged(situation, seat, "effect", {"source": "x", "delta": delta, **arguments}, result)


# @spec REC-032
@NOT_BUILT
def test_an_entry_names_the_item_its_call_put_on_the_stack() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))

    entry = data(a_cast(situation, S1, "Lightning Bolt", delta=bolt_at(2)))

    assert entry["stacked"] == "s1"
    assert (entry["card"], entry["delta"]["damage"]) == ("Lightning Bolt", {"2": 3})


# @spec REC-033
@NOT_BUILT
def test_a_stacking_entry_records_what_was_stated_and_paid_when_it_was_cast() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))

    entry = data(a_cast(situation, S1, "Lightning Bolt", delta=bolt_at(2)))

    assert entry["paid"]["cost"] == "{R}"
    assert entry["delta"]["added"] == {"shuffles": 0, "commander_redirected": [], "tokens_gone": []}
    assert entry["stacked"] == "s1"


# @spec REC-034
@NOT_BUILT
def test_the_entry_of_the_call_that_resolved_an_item_records_its_resolution() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    a_cast(situation, S1, "Lightning Bolt", delta=bolt_at(2))

    entry = data(a_pass(situation, S2))

    (resolved,) = entry["resolved"]
    assert (resolved["item"], resolved["controller"], resolved["source"]) == (
        "s1",
        1,
        "Lightning Bolt",
    )
    assert resolved["delta"]["damage"] == {"2": 3}
    assert resolved["to"] == "graveyard"


# @spec REC-034
@NOT_BUILT
def test_a_resolved_ability_records_no_destination() -> None:
    situation = two_seats()
    an_effect(situation, S1, {"life": 1})

    (resolved,) = data(a_pass(situation, S2))["resolved"]

    assert (resolved["item"], resolved["to"]) == ("s1", None)


# @spec REC-034, REC-074
@NOT_BUILT
def test_a_restated_resolution_records_the_restated_delta_and_the_choose_has_no_outcome() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Grizzly Bears", delta={"life": 1}, disturbed=True),
        lambda b: b.with_window("stack", asking=2),
    )
    a_pass(situation, S2)
    choice = situation.game.pending[0].choice_id
    restate = {"delta": {"life": 4}}

    result = choose(situation.game, situation.deck, S1, choice_id=choice, restate=restate)
    entry = data(logged(situation, S1, "choose", {"choice_id": choice, "restate": restate}, result))

    assert entry["outcome"] is None
    (resolved,) = entry["resolved"]
    assert resolved["delta"]["life"] == 4


# @spec REC-074
def test_a_choose_answering_an_ask_has_no_outcome() -> None:
    situation = two_seats(lambda b: b.with_hand("Grizzly Bears"), lands=False)
    an_effect(situation, S1, {"ask": [{"seats": [2], "text": "lose 1 life"}]}, immediate=True)
    choice = situation.game.pending[0].choice_id

    result = choose(situation.game, situation.deck, S2, choice_id=choice, delta={"life": -1})
    entry = data(logged(situation, S2, "choose", {"choice_id": choice}, result))

    assert entry["outcome"] is None


# @spec REC-035
@NOT_BUILT
def test_resolving_an_item_leaves_the_entry_that_stacked_it_as_it_was() -> None:
    situation = two_seats(lambda b: b.with_hand("Lightning Bolt"))
    cast = data(a_cast(situation, S1, "Lightning Bolt", delta=bolt_at(2)))
    before = dict(cast)

    a_pass(situation, S2)

    assert cast == before
    assert cast["resolved"] == []


# @spec REC-036
@NOT_BUILT
def test_the_entry_of_the_call_whose_delta_countered_an_item_records_it() -> None:
    situation = two_seats(
        lambda b: b.with_spell_on_stack("Lightning Bolt", delta=bolt_at(2)),
        lambda b: b.with_hand("Counterspell").with_window("stack", asking=2),
    )
    a_cast(situation, S2, "Counterspell", delta={"counter": ["s1"]})

    entry = data(a_pass(situation, S1))

    assert entry["countered"] == ["s1"]
    assert [resolved["item"] for resolved in entry["resolved"]] == ["s2"]


# @spec REC-066
@NOT_BUILT
def test_items_an_elimination_takes_off_the_stack_are_recorded_as_removed() -> None:
    situation = three_seats(
        second=lambda b: b.with_ability_on_stack(
            "a trick", delta={"life": 1}
        ).with_ability_on_stack("another", delta={"life": 1}),
        third=lambda b: b.with_window("stack", asking=3),
    )

    result = end_game(situation.game, situation.deck, S2, result="loss")
    entry = data(logged(situation, S2, "end_game", {"result": "loss"}, result))

    assert entry["removed"] == ["s1", "s2"]
    assert entry["countered"] == []


# @spec REC-066
@NOT_BUILT
def test_items_the_end_of_the_game_takes_off_the_stack_are_recorded_as_removed() -> None:
    situation = two_seats(
        second=lambda b: b.with_ability_on_stack("a trick", delta={"life": 1}).with_window(
            "stack", asking=1
        )
    )

    result = end_game(situation.game, situation.deck, S1, result="win")
    entry = data(logged(situation, S1, "end_game", {"result": "win"}, result))

    assert entry["removed"] == ["s1"]


# @spec REC-037
@NOT_BUILT
def test_automatic_passes_are_recorded_with_the_item_passed_on() -> None:
    situation = three_seats(
        lambda b: b.with_hand("Grizzly Bears"),
        lambda b: b,
        lambda b: b.with_battlefield("Island"),
        lands=False,
    )

    entry = data(a_cast(situation, S1, "Grizzly Bears", override="paid by the test"))

    assert entry["auto_passes"] == [{"seat": 2, "item": "s1"}]


# @spec REC-037
@NOT_BUILT
def test_an_automatic_pass_in_an_end_window_with_an_empty_stack_names_no_item() -> None:
    situation = two_seats(step=Step.MAIN2, lands=False)

    result = advance(situation.game, situation.deck, S1, to="cleanup")
    entry = data(logged(situation, S1, "advance", {"to": "cleanup"}, result))

    assert entry["auto_passes"] == [{"seat": 2, "item": None}]


# @spec REC-044
@NOT_BUILT
def test_a_pass_on_a_reminder_does_not_answer_it() -> None:
    situation = a_table(lambda b: b, lambda b: b.with_battlefield("Black Vise"), step=Step.UNTAP)
    entries = [logged(situation, S1, "advance", {}, advance(situation.game, situation.deck, S1))]

    entries.append(a_pass(situation, S2))

    (judged,) = judge_reminders(entries)
    assert judged.answered is False


# @spec REC-044
@NOT_BUILT
def test_an_effect_after_a_pass_on_a_reminder_still_answers_it() -> None:
    situation = a_table(lambda b: b, lambda b: b.with_battlefield("Black Vise"), step=Step.UNTAP)
    entries = [logged(situation, S1, "advance", {}, advance(situation.game, situation.deck, S1))]
    entries.append(a_pass(situation, S2))

    result = effect(
        situation.game, situation.deck, S2, source="Black Vise", delta={"life": 0}, immediate=True
    )
    entries.append(
        logged(situation, S2, "effect", {"source": "Black Vise", "immediate": True}, result)
    )

    (judged,) = judge_reminders(entries)
    assert judged.answered is True
