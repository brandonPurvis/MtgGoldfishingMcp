"""Coordinating the seats of a contested game: waiting for a seat's turn to act, the digest
each response begins with, resends against a seat's own change, and records naming seats."""

# @spec APP-076

import json
import threading
from collections import Counter
from typing import Any

from behave import given, then, when
from tests.support.responses import digest_lines

from mtg_goldfishing.adapters.mcp.tools import ToolResponse
from mtg_goldfishing.domain.game.seats import SeatNumber

SEAT = r"S{number:d}"


def _as_seat(context: Any, number: int, tool: str, **arguments: object) -> ToolResponse:
    seat_id = context.table_of_seats.seat_id(number)
    response: ToolResponse = context.agent.call(tool, game_id=seat_id, **arguments)
    return response


def _hand_of(context: Any, number: int) -> list[str]:
    game = context.agent.game()
    return [card.name for card in game.hand_of(SeatNumber(number))]


def _digest(context: Any) -> list[str]:
    """The digest lines the last response begins with."""
    return digest_lines(context.agent.text)


@given(f"seat {SEAT}'s hand is noted")
def step_impl(context: Any, number: int) -> None:
    context.noted_hand = Counter(_hand_of(context, number))


@when(f"seat {SEAT} waits")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "wait")


@when(f"seat {SEAT} waits with a timeout of {{seconds:d}} second")
def step_impl(context: Any, number: int, seconds: int) -> None:
    _as_seat(context, number, "wait", timeout=seconds)


@when(f"seat {SEAT} starts waiting")
def step_impl(context: Any, number: int) -> None:
    """The seat's agent calls wait on a thread of its own and is answered there."""
    seat_id = context.table_of_seats.seat_id(number)
    answers: list[ToolResponse] = []
    tools = context.agent.tools
    thread = threading.Thread(
        target=lambda: answers.append(tools.call("wait", {"game_id": seat_id, "timeout": 10})),
        daemon=True,
    )
    thread.start()
    context.waiting = (thread, answers)


@when(f"seat {SEAT} takes a mulligan after change {{after:d}}")
def step_impl(context: Any, number: int, after: int) -> None:
    _as_seat(context, number, "mulligan", keep=False, after=after)


@when(f"seat {SEAT} records an effect sent after change {{after:d}} with delta {{delta}}")
def step_impl(context: Any, number: int, after: int, delta: str) -> None:
    _as_seat(
        context, number, "effect", source="a test effect", delta=json.loads(delta), after=after
    )


@when(f"seat {SEAT} asks for the game's log with the call records")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "get_log", include_calls=True)


@then(f'seat {SEAT}\'s wait returns "{{line}}"')
def step_impl(context: Any, number: int, line: str) -> None:
    thread, answers = context.waiting
    thread.join(timeout=15)
    assert not thread.is_alive(), "the wait did not return"
    (answer,) = answers
    assert line in answer.text.splitlines(), answer.text


@then("the response begins with a digest line for change #{change:d} made by S{number:d}")
def step_impl(context: Any, change: int, number: int) -> None:
    digest = _digest(context)
    assert [line for line in digest if line.startswith(f"S{number} #{change}: ")], digest


@then('the digest says "{words}"')
def step_impl(context: Any, words: str) -> None:
    assert any(words in line for line in _digest(context)), context.agent.text


@then(f"the digest names no card of seat {SEAT}'s hand")
def step_impl(context: Any, number: int) -> None:
    digest = " ".join(_digest(context))
    named = [name for name in _hand_of(context, number) if name in digest]
    assert named == [], (named, digest)


@then(f"the digest names the card seat {SEAT} drew")
def step_impl(context: Any, number: int) -> None:
    drawn = list((Counter(_hand_of(context, number)) - context.noted_hand).elements())
    assert len(drawn) == 1, drawn
    lines = _digest(context)
    assert any(f"S{number} drew {drawn[0]}" in line for line in lines), context.agent.text


@then("the response has no digest lines")
def step_impl(context: Any) -> None:
    assert digest_lines(context.agent.text) == [], context.agent.text


@then("the game's change number is {change:d}")
def step_impl(context: Any, change: int) -> None:
    assert context.agent.game().change == change


@then("every log entry and call record names the seat that made it")
def step_impl(context: Any) -> None:
    log = json.loads(context.agent.text)
    entries = [(entry["tool"], entry["seat"]) for entry in log["entries"]]
    assert entries[0] == ("new_game", None), entries
    assert all(isinstance(seat, int) for _, seat in entries[1:]), entries
    calls = [(call["tool"], call.get("seat")) for call in log["calls"]]
    assert all(isinstance(seat, int) for tool, seat in calls if tool != "new_game"), calls


@then("the log's game lists {count:d} opposing seats on the Omnath deck")
def step_impl(context: Any, count: int) -> None:
    seats = json.loads(context.agent.text)["game"]["seats"]
    opposing = [seat for seat in seats if not seat["tested"]]
    assert [seat["deck_id"] for seat in opposing] == [context.opposing_deck_id] * count, seats
