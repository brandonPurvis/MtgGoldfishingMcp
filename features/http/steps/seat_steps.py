"""Contested games over HTTP: starting a game, and acting and reading as each seat through its
own MCP client and seat id. Every fact a step checks was read in a response, as an agent
would read it."""

# @spec APP-077

import json
import threading
import time
from collections import Counter
from typing import Any

from behave import given, then, when
from features.http.players import (
    Table,
    choice_for,
    hand,
    status_line,
    zone_of,
)
from features.http.seat_agent import SeatAgent
from tests.e2e.seat_clients import Answer
from tests.support.decks import ATRAXA, OMNATH, a_deck_list, an_opposing_deck_list
from tests.support.responses import headline

SEAT = r"S{number:d}"
FULL_GAME_TIMEOUT = 300.0


def _table(context: Any) -> Table:
    table: Table = context.players
    return table


def _correct(context: Any, number: int, delta: dict[str, object]) -> None:
    """Arrange the scenario with an immediate effect of the seat, which must be accepted."""
    answer = _table(context).as_seat(
        number, "effect", source="arranging the scenario", delta=delta, immediate=True
    )
    assert headline(answer.text).startswith("OK"), answer.text


def _bring(context: Any, number: int, card: str, zone: str) -> None:
    """See that the seat has `card` in its hand or on its battlefield, moving it there from
    its hand or command zone, or else fetching it from its library."""
    state = _table(context).state_of(number)
    held = hand(state)
    if zone == "hand":
        if card in held:
            return
        sources = {"command": zone_of(state, number, "Command zone")}
    else:
        if card in zone_of(state, number, "Battlefield"):
            return
        sources = {"hand": held, "command": zone_of(state, number, "Command zone")}
    if any(card in names for names in sources.values()):
        _correct(context, number, {"move": {zone: [card]}})
    else:
        _correct(context, number, {"fetch": {zone: [card]}})


def _start_seated(context: Any, count: int, **arguments: object) -> None:
    table = _table(context)
    opposing = table.opposing_deck_id
    assert opposing is not None
    answer = table.start([opposing] * count, 42, position=1, **arguments)
    assert headline(answer.text).startswith("OK"), answer.text


# ------------------------------------------------------------------ decks and games


@given("the Atraxa test deck is loaded")
def step_impl(context: Any) -> None:
    _table(context).deck_id = _table(context).load(a_deck_list().text(), ATRAXA)


@given("the Omnath test deck is loaded")
def step_impl(context: Any) -> None:
    table = _table(context)
    table.opposing_deck_id = table.load(an_opposing_deck_list().text(), OMNATH)


@when("I start a contested game against {count:d} Omnath decks with seed {seed:d}")
@when("I start a contested game against {count:d} Omnath deck with seed {seed:d}")
def step_impl(context: Any, count: int, seed: int) -> None:
    table = _table(context)
    assert table.opposing_deck_id is not None
    table.start([table.opposing_deck_id] * count, seed)


@given(
    "a contested game against {count:d} Omnath deck with seed {seed:d}"
    " and the tested seat at position {position:d}"
)
@given(
    "a contested game against {count:d} Omnath decks with seed {seed:d}"
    " and the tested seat at position {position:d}"
)
def step_impl(context: Any, count: int, seed: int, position: int) -> None:
    table = _table(context)
    assert table.opposing_deck_id is not None
    answer = table.start([table.opposing_deck_id] * count, seed, position=position)
    assert headline(answer.text).startswith("OK"), answer.text


@given("a started contested game against {count:d} Omnath deck with the tested seat first")
@given("a started contested game against {count:d} Omnath decks with the tested seat first")
def step_impl(context: Any, count: int) -> None:
    _start_seated(context, count)
    table = _table(context)
    for number in sorted(table.seats):
        kept = table.as_seat(number, "mulligan", keep=True)
        assert headline(kept.text).startswith("OK"), kept.text


@given("a started contested game against the Atraxa deck with the tested seat first")
def step_impl(context: Any) -> None:
    table = _table(context)
    table.opposing_deck_id = table.deck_id
    context.execute_steps(
        "Given a started contested game against 1 Omnath deck with the tested seat first"
    )


# ------------------------------------------------------------------ arranging


@given(f'seat {SEAT} puts "{{card}}" onto the battlefield')
def step_impl(context: Any, number: int, card: str) -> None:
    _bring(context, number, card, "battlefield")


@given(f'seat {SEAT} holds "{{card}}"')
def step_impl(context: Any, number: int, card: str) -> None:
    _bring(context, number, card, "hand")


@given(f'seat {SEAT} has "{{mana}}" in its pool')
@when(f'seat {SEAT} adds "{{mana}}" to its pool')
def step_impl(context: Any, number: int, mana: str) -> None:
    _correct(context, number, {"mana": mana})


@given(f"seat {SEAT} has ended its turn")
def step_impl(context: Any, number: int) -> None:
    """Discard down to seven, then advance until the turn passes; a seat asked in a window or
    reminded on the way passes, each through its own client."""
    table = _table(context)
    held = hand(table.state_of(number))
    if len(held) > 7:
        _correct(context, number, {"discard": held[7:]})
    line = status_line(table.state_of(number))
    for _ in range(8):
        act = line.act
        assert act is not None, line.text
        who, asked = act
        if who != "you" and asked in ("respond", "trigger"):
            answer = table.as_seat(int(who.removeprefix("S")), "pass")
        else:
            answer = table.as_seat(number, "advance", to="main1")
        assert headline(answer.text).startswith("OK"), answer.text
        line = status_line(table.state_of(number))
        if line.active != number:
            return
    raise AssertionError(table.last.text)


# ------------------------------------------------------------------ calls


@when(f"seat {SEAT} records an effect with delta {{delta}}")
def step_impl(context: Any, number: int, delta: str) -> None:
    _table(context).as_seat(number, "effect", source="a test effect", delta=json.loads(delta))


@when(f'seat {SEAT} casts "{{card}}"')
def step_impl(context: Any, number: int, card: str) -> None:
    _table(context).as_seat(number, "play", card=card)


@when(f'seat {SEAT} casts "{{card}}" with delta {{delta}}')
def step_impl(context: Any, number: int, card: str, delta: str) -> None:
    _table(context).as_seat(number, "play", card=card, delta=json.loads(delta))


@when(f"seat {SEAT} passes")
def step_impl(context: Any, number: int) -> None:
    _table(context).as_seat(number, "pass")


@when(f"seat {SEAT} asks for the state")
def step_impl(context: Any, number: int) -> None:
    _table(context).as_seat(number, "get_state")


@when(f"seat {SEAT} waits")
def step_impl(context: Any, number: int) -> None:
    _table(context).as_seat(number, "wait")


@when(f"seat {SEAT} attacks with targets {{targets}}")
def step_impl(context: Any, number: int, targets: str) -> None:
    by_attacker = json.loads(targets)
    _table(context).as_seat(number, "attack", attackers=list(by_attacker), targets=by_attacker)


@when(f'seat {SEAT} advances to "{{step}}"')
def step_impl(context: Any, number: int, step: str) -> None:
    _table(context).as_seat(number, "advance", to=step)


@when(f"seat {SEAT} answers its blocks choice with blocks {{blocks}}")
def step_impl(context: Any, number: int, blocks: str) -> None:
    """The choice id is the one the seat was shown, in the answer to its latest call."""
    table = _table(context)
    choice = choice_for(table.last, number)
    table.as_seat(number, "choose", choice_id=choice, blocks=json.loads(blocks))


@when(f"seat {SEAT} ends its turn")
def step_impl(context: Any, number: int) -> None:
    """Advance to the next turn's first main step, discarding down to seven if need be."""
    table = _table(context)
    held = hand(table.state_of(number))
    arguments: dict[str, object] = {"to": "main1"}
    if len(held) > 7:
        arguments["discard"] = held[7:]
    table.as_seat(number, "advance", **arguments)


@when(f"seat {SEAT} takes a mulligan")
def step_impl(context: Any, number: int) -> None:
    _table(context).as_seat(number, "mulligan", keep=False)


@when(f"seat {SEAT} takes a mulligan after change {{after:d}}")
def step_impl(context: Any, number: int, after: int) -> None:
    _table(context).as_seat(number, "mulligan", keep=False, after=after)


# ------------------------------------------------------------------ waiting at once


@when(f"seat {SEAT} starts waiting with a timeout of {{seconds:d}} seconds")
def step_impl(context: Any, number: int, seconds: int) -> None:
    """The seat's agent sends wait through its own client; the answer comes later."""
    table = _table(context)
    context.waiting = (
        time.monotonic(),
        seconds,
        table.clients.send(
            f"S{number}", "wait", {"game_id": table.seat_id(number), "timeout": seconds}
        ),
    )


@then(f"seat {SEAT}'s wait is still open after {{seconds:d}} second")
def step_impl(context: Any, number: int, seconds: int) -> None:
    _, _, answer = context.waiting
    time.sleep(seconds)
    assert not answer.done(), answer.result().text


@then(f'seat {SEAT}\'s wait returns "{{line}}" well before its timeout')
def step_impl(context: Any, number: int, line: str) -> None:
    sent, seconds, pending = context.waiting
    answer: Answer = pending.result(timeout=seconds + 10)
    waited = time.monotonic() - sent
    assert line in answer.text.splitlines(), answer.text
    assert waited < seconds / 2, f"the wait took {waited:.1f}s of its {seconds}s"


# ------------------------------------------------------------------ a full game


@when(
    "every seat plays through its own client at once, S{concedes:d} conceding in round"
    " {concede_round:d} and the tested seat ending the game in round {end_round:d}"
)
def step_impl(context: Any, concedes: int, concede_round: int, end_round: int) -> None:
    """Each seat's agent runs on a thread of its own, with its own client, from mulligans to
    the end of the game. With the tested seat first in turn order, a seat's own turn number
    is the round."""
    table = _table(context)
    assert table.tested == 1, table.seats
    agents = [
        SeatAgent(
            table.clients,
            number,
            table.seat_id(number),
            concede_on_turn=concede_round if number == concedes else None,
            end_on_turn=end_round if number == table.tested else None,
        )
        for number in sorted(table.seats)
    ]
    problems: dict[int, BaseException] = {}

    def run(agent: SeatAgent) -> None:
        try:
            agent.play()
        except BaseException as problem:  # reported by the step that checks the agents
            problems[agent.number] = problem

    threads = [threading.Thread(target=run, args=(agent,), daemon=True) for agent in agents]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + FULL_GAME_TIMEOUT
    for thread in threads:
        thread.join(timeout=max(deadline - time.monotonic(), 0))
    context.agents = agents
    context.agent_problems = problems
    context.agents_running = [t.name for t in threads if t.is_alive()]


@then("every seat's agent stopped without a problem")
def step_impl(context: Any) -> None:
    assert context.agents_running == [], "agents still playing"
    assert context.agent_problems == {}, context.agent_problems
    stopped = {agent.number: agent.stopped for agent in context.agents}
    assert all(stopped.values()), stopped
    refused = [error for agent in context.agents for error in agent.unexpected_errors]
    assert refused == [], refused


@then(f"seat {SEAT} is told the game has ended")
def step_impl(context: Any, number: int) -> None:
    agent = next(agent for agent in context.agents if agent.number == number)
    assert agent.last is not None
    assert agent.stopped == "ended", agent.last.text
    assert headline(agent.last.text) == "OK The game has ended.", agent.last.text


@then(f"the log read by seat {SEAT} holds every change of the game in change-number order")
def step_impl(context: Any, number: int) -> None:
    log = _table(context).log(number, include_calls=True)
    context.log = log
    changes = [entry["seq"] for entry in log["entries"]]
    assert log["game"]["status"] == "ended", log["game"]
    assert changes == list(range(1, log["game"]["change"] + 1)), changes


@then("the log holds changes made by every seat")
def step_impl(context: Any) -> None:
    made = Counter(entry["seat"] for entry in context.log["entries"])
    assert set(made) - {None} == set(_table(context).seats), made


@then("the log's call records name every seat")
def step_impl(context: Any) -> None:
    calls = Counter(call.get("seat") for call in context.log["calls"])
    assert set(_table(context).seats) <= set(calls), calls


# ------------------------------------------------------------------ what a seat reads


@then("the response is {status}")
def step_impl(context: Any, status: str) -> None:
    assert headline(_table(context).last.text).startswith(status), _table(context).last.text


@then('the response says "{words}"')
def step_impl(context: Any, words: str) -> None:
    assert words in _table(context).last.text, _table(context).last.text


@then('the status line shows "{words}"')
def step_impl(context: Any, words: str) -> None:
    assert words in _table(context).status_line.text, _table(context).status_line.text


@then("the status line has no Stack field")
def step_impl(context: Any) -> None:
    assert " · Stack " not in _table(context).status_line.text, _table(context).status_line.text


@then("the response lists {count:d} seats in turn order")
def step_impl(context: Any, count: int) -> None:
    table = _table(context)
    assert sorted(table.seats) == list(range(1, count + 1)), table.last.text


@then("each seat was given its own seat id")
def step_impl(context: Any) -> None:
    table = _table(context)
    ids = [seat.seat_id for seat in table.seats.values()]
    assert len(set(ids)) == len(ids), ids
    assert table.seat_id(table.tested) == table.game_id


@then("each seat's client is answered as that seat")
def step_impl(context: Any) -> None:
    """During mulligans every seat is still to keep: each reads itself as `you` among them."""
    table = _table(context)
    for number in sorted(table.seats):
        line = status_line(table.state_of(number))
        expected = ["you" if n == number else f"S{n}" for n in sorted(table.seats)]
        assert line.to_keep == expected, (number, line.text)


@then("the response begins with a digest line for change #{change:d} made by S{number:d}")
def step_impl(context: Any, change: int, number: int) -> None:
    digest = _table(context).digest
    assert [line for line in digest if line.startswith(f"S{number} #{change}: ")], digest


@then('the digest says "{words}"')
def step_impl(context: Any, words: str) -> None:
    assert any(words in line for line in _table(context).digest), _table(context).last.text


@then(f"the digest names no card of seat {SEAT}'s hand")
def step_impl(context: Any, number: int) -> None:
    table = _table(context)
    digest = " ".join(table.digest)
    named = [name for name in hand(table.state_of(number)) if name in digest]
    assert named == [], (named, digest)


@then(f'"{{card}}" is in seat {SEAT}\'s graveyard')
def step_impl(context: Any, card: str, number: int) -> None:
    graveyard = zone_of(_table(context).state_of(number), number, "Graveyard")
    assert card in graveyard, graveyard


@then(f"seat {SEAT}'s life is {{life:d}}")
def step_impl(context: Any, number: int, life: int) -> None:
    line = status_line(_table(context).state_of(number))
    assert line.field("Life") == str(life), line.text


@then("the game's change number is {change:d}")
def step_impl(context: Any, change: int) -> None:
    table = _table(context)
    line = status_line(table.state_of(table.tested))
    assert line.change == change, line.text
