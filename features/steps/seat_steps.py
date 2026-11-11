"""Contested games: starting one against opposing decks, and acting as each seat by its own
seat id, as the agent playing that seat would."""

# @spec APP-076

import json
import re
from collections import Counter
from typing import Any

from behave import given, then, when
from tests.support.decks import OMNATH, an_opposing_deck_list
from tests.support.responses import headline

from mtg_goldfishing.adapters.mcp.tools import ToolResponse
from mtg_goldfishing.domain.game.model import Game

STARTED = re.compile(r"^OK Started contested game (g\w+) with seed (\d+)\. Seats in turn order:$")
SEAT_LINE = re.compile(r"^S(\d+) (g\w+): deck (\w+), life (\d+)(, the tested seat)?\.$")
SEAT = r"S{number:d}"


class Table:
    """What the agent starting a contested game was told: the game id and each seat's line."""

    def __init__(self, response: ToolResponse) -> None:
        lines = response.text.splitlines()
        started = STARTED.match(lines[0])
        assert started, response.text
        self.game_id = started.group(1)
        self.seats: dict[int, dict[str, Any]] = {}
        for line in lines[1:]:
            found = SEAT_LINE.match(line)
            if found:
                number, seat_id, deck_id, life, tested = found.groups()
                self.seats[int(number)] = {
                    "seat_id": seat_id,
                    "deck_id": deck_id,
                    "life": int(life),
                    "tested": tested is not None,
                }

    def seat_id(self, number: int) -> str:
        return str(self.seats[number]["seat_id"])

    @property
    def tested(self) -> int:
        return next(number for number, seat in self.seats.items() if seat["tested"])


def _start(context: Any, opponents: list[str], seed: int, **arguments: object) -> ToolResponse:
    agent = context.agent
    response = agent.call(
        "new_game", deck_id=agent.deck_id, opponents=opponents, seed=seed, **arguments
    )
    if headline(response.text).startswith("OK"):
        table = Table(response)
        context.tables = [*getattr(context, "tables", []), table]
        context.table_of_seats = table
        agent.game_id = table.game_id
    return response


def _omnath(context: Any, count: int) -> list[str]:
    return [context.opposing_deck_id] * count


def _as_seat(context: Any, number: int, tool: str, **arguments: object) -> ToolResponse:
    seat_id = context.table_of_seats.seat_id(number)
    response: ToolResponse = context.agent.call(tool, game_id=seat_id, **arguments)
    return response


def _game(context: Any) -> Game:
    game: Game = context.agent.game()
    return game


def _hand_line(response: ToolResponse) -> str:
    """The hand line of a state listing."""
    return next(line for line in response.text.splitlines() if line.startswith("Hand ("))


def _hand_of(context: Any, number: int) -> list[str]:
    game = _game(context)
    seat = next(seat for seat in game.seats if seat.number.value == number)
    return [card.name for card in game.hand_of(seat.number)]


@given("the Omnath test deck is loaded")
def step_impl(context: Any) -> None:
    response = context.agent.call(
        "load_deck", cards=an_opposing_deck_list().text(), commander=OMNATH
    )
    assert headline(response.text).startswith("OK Loaded deck "), response.text
    context.opposing_deck_id = response.text.split()[3].rstrip(":")


@when("I start a contested game against {count:d} Omnath decks with seed {seed:d}")
@when("I start a contested game against {count:d} Omnath deck with seed {seed:d}")
@when("I start another contested game against {count:d} Omnath decks with seed {seed:d}")
def step_impl(context: Any, count: int, seed: int) -> None:
    _start(context, _omnath(context, count), seed)


@when(
    "I start a contested game against {count:d} Omnath decks with seed {seed:d}"
    " and the tested seat at position {position:d}"
)
@when(
    "I start a contested game against {count:d} Omnath deck with seed {seed:d}"
    " and the tested seat at position {position:d}"
)
def step_impl(context: Any, count: int, seed: int, position: int) -> None:
    _start(context, _omnath(context, count), seed, position=position)


@when(
    "I start a contested game against the Omnath deck and the Atraxa deck with seed {seed:d}"
    " and starting life {lives}"
)
def step_impl(context: Any, seed: int, lives: str) -> None:
    starting = [int(life) for life in lives.split(",")]
    opponents = [context.opposing_deck_id, context.agent.deck_id]
    _start(context, opponents, seed, starting_life=starting)


@when("I start a contested game against the Atraxa deck with seed {seed:d}")
def step_impl(context: Any, seed: int) -> None:
    _start(context, [context.agent.deck_id], seed)


@given(
    "a contested game against {count:d} Omnath deck with seed {seed:d}"
    " and the tested seat at position {position:d}"
)
def step_impl(context: Any, count: int, seed: int, position: int) -> None:
    response = _start(context, _omnath(context, count), seed, position=position)
    assert headline(response.text).startswith("OK"), response.text


@given("a started contested game against {count:d} Omnath deck with the tested seat first")
def step_impl(context: Any, count: int) -> None:
    response = _start(context, _omnath(context, count), 42, position=1)
    assert headline(response.text).startswith("OK"), response.text
    for number in sorted(context.table_of_seats.seats):
        kept = _as_seat(context, number, "mulligan", keep=True)
        assert headline(kept.text).startswith("OK"), kept.text


@given(
    "a started contested game against {count:d} Omnath deck with the tested seat first"
    " and a turn limit of {limit:d}"
)
def step_impl(context: Any, count: int, limit: int) -> None:
    response = _start(context, _omnath(context, count), 42, position=1, turn_limit=limit)
    assert headline(response.text).startswith("OK"), response.text
    for number in sorted(context.table_of_seats.seats):
        kept = _as_seat(context, number, "mulligan", keep=True)
        assert headline(kept.text).startswith("OK"), kept.text


@when(f"seat {SEAT} takes a mulligan")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "mulligan", keep=False)


@when(f"seat {SEAT} keeps its hand")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "mulligan", keep=True)


@when(f"seat {SEAT} advances")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "advance")


@when(f"seat {SEAT} ends its turn")
def step_impl(context: Any, number: int) -> None:
    """Advance to the next turn's first main step, discarding down to seven if need be."""
    hand = _hand_of(context, number)
    discard = hand[7:]
    arguments: dict[str, object] = {"to": "main1"}
    if discard:
        arguments["discard"] = discard
    _as_seat(context, number, "advance", **arguments)


@when(f"seat {SEAT} asks for the state")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "get_state")


@when(f"seat {SEAT} asks for the game's log")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "get_log")


@then("the response lists {count:d} seats in turn order")
def step_impl(context: Any, count: int) -> None:
    assert sorted(context.table_of_seats.seats) == list(range(1, count + 1)), context.agent.text


@then("each seat was given its own seat id")
def step_impl(context: Any) -> None:
    table = context.table_of_seats
    ids = [seat["seat_id"] for seat in table.seats.values()]
    assert len(set(ids)) == len(ids)
    assert table.seats[table.tested]["seat_id"] == table.game_id
    for number, seat in table.seats.items():
        game = _game(context)
        found = next(s for s in game.seats if s.seat_id.value == seat["seat_id"])
        assert found.number.value == number


@then("both contested games have the same turn order")
def step_impl(context: Any) -> None:
    first, second = context.tables[-2:]
    assert first.tested == second.tested
    assert [s["deck_id"] for s in first.seats.values()] == [
        s["deck_id"] for s in second.seats.values()
    ]


@then("every seat of both games was dealt the same opening hand")
def step_impl(context: Any) -> None:
    first, second = context.tables[-2:]
    for number in first.seats:
        hands = []
        for table in (first, second):
            response = context.agent.call("get_state", game_id=table.seat_id(number))
            hands.append(_hand_line(response))
        assert hands[0] == hands[1], hands
        assert hands[0].startswith("Hand (7): "), hands


@then("the tested seat of the contested game holds the goldfish game's opening hand")
def step_impl(context: Any) -> None:
    started = next(r.text for r in context.agent.responses if r.text.startswith("OK Started game"))
    goldfish = started.split("Hand: ", 1)[1].splitlines()[0].rstrip(".")
    table = context.table_of_seats
    response = context.agent.call("get_state", game_id=table.seat_id(table.tested))
    assert _hand_line(response) == f"Hand (7): {goldfish}", (goldfish, response.text)


@then("the response lists the tested seat as S{number:d}")
def step_impl(context: Any, number: int) -> None:
    assert context.table_of_seats.tested == number, context.agent.text


@then("the response lists life {life:d} for the {which} seat on the {deck} deck")
def step_impl(context: Any, life: int, which: str, deck: str) -> None:
    deck_id = context.opposing_deck_id if deck == "Omnath" else context.agent.deck_id
    tested = which == "tested"
    seats = [
        seat
        for seat in context.table_of_seats.seats.values()
        if seat["deck_id"] == deck_id and seat["tested"] is tested
    ]
    assert [seat["life"] for seat in seats] == [life], context.agent.text


@then("every seat starts with life {life:d}")
def step_impl(context: Any, life: int) -> None:
    lives = {seat["life"] for seat in context.table_of_seats.seats.values()}
    assert lives == {life}, context.agent.text


@then("every seat plays the Atraxa deck")
def step_impl(context: Any) -> None:
    decks = {seat["deck_id"] for seat in context.table_of_seats.seats.values()}
    assert decks == {context.agent.deck_id}, context.agent.text


@then(f"the response shows seat {SEAT}'s hand")
def step_impl(context: Any, number: int) -> None:
    hand = ", ".join(_hand_of(context, number))
    assert f"Hand: {hand}." in context.agent.text, (hand, context.agent.text)


@then(f"the state lists seat {SEAT}'s hand and no other")
def step_impl(context: Any, number: int) -> None:
    hand = _hand_of(context, number)
    lines = [line for line in context.agent.text.splitlines() if line.startswith("Hand (")]
    assert lines == [f"Hand ({len(hand)}): {', '.join(hand)}"], context.agent.text


@then('the response lists "{line}"')
def step_impl(context: Any, line: str) -> None:
    assert line in context.agent.text.splitlines(), context.agent.text


@then(f"seat {SEAT} holds {{count:d}} cards")
def step_impl(context: Any, number: int, count: int) -> None:
    assert len(_hand_of(context, number)) == count


@then(f'seat {SEAT}\'s status line begins "{{start}}"')
def step_impl(context: Any, number: int, start: str) -> None:
    line = _as_seat(context, number, "get_state").text.splitlines()[-1]
    assert line.startswith(start), line


@then("the game is in round {round_number:d}")
def step_impl(context: Any, round_number: int) -> None:
    assert _game(context).round == round_number


@then('the response does not say "{words}"')
def step_impl(context: Any, words: str) -> None:
    assert words not in context.agent.text, context.agent.text


@then(f"the log holds seat {SEAT}'s opening hand")
def step_impl(context: Any, number: int) -> None:
    """A kept hand in the log holds the seat's cards: those still in its hand."""
    log = json.loads(context.agent.text)
    held = Counter(_hand_of(context, number))
    kept = [
        Counter(entry["outcome"]["hand"])
        for entry in log["entries"]
        if entry["tool"] == "mulligan" and entry["outcome"] and "bottomed" in entry["outcome"]
    ]
    assert any(len(list(hand.elements())) == 7 and hand <= held for hand in kept), kept


@then("the status line has no seat, Act or Stack field")
def step_impl(context: Any) -> None:
    line = context.agent.status_line
    assert " · You S" not in line
    assert " · Act " not in line
    assert " · Stack " not in line
    assert not line.startswith("Out")
