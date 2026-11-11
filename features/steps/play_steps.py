"""Playing cards, recording effects, and finishing a look with `choose`."""

# @spec APP-025

import re
from typing import Any

from behave import given, then, when
from tests.support.responses import headline

from mtg_goldfishing.domain.game.model import Zone

REVEALED = re.compile(r"Choice (?P<choice>\S+) \(look\) revealed: (?P<first>[^(]+) \(")


@when('I play "{card:Quoted}" with override "{reason:Quoted}"')
def step_impl(context: Any, card: str, reason: str) -> None:
    context.agent.call("play", card=card, override=reason)


@when('I play "{card:Quoted}" after the change number I last saw')
def step_impl(context: Any, card: str) -> None:
    agent = context.agent
    agent.change_at_start = agent.change()
    agent.call("play", card=card, after=agent.change_at_start)


@given('I have played "{card:Quoted}"')
def step_impl(context: Any, card: str) -> None:
    response = context.agent.call("play", card=card)
    assert headline(response.text).startswith("OK"), response.text


@when('I play "{card:Quoted}"')
def step_impl(context: Any, card: str) -> None:
    context.agent.call("play", card=card)


@when("I send the same call again")
def step_impl(context: Any) -> None:
    tool, arguments = context.agent.calls[-1]
    context.agent.call(tool, **arguments)


@then("the game's change number went up by one in all")
def step_impl(context: Any) -> None:
    agent = context.agent
    assert agent.game().change == agent.change_at_start + 1


@when("I call play without naming a card")
def step_impl(context: Any) -> None:
    context.agent.call("play")


@then("the call is kept as a call record")
def step_impl(context: Any) -> None:
    record = context.agent.harness.last_call()
    assert (record.tool, record.game_id) == ("play", context.agent.game_id), record
    assert record.response == context.agent.text


@when(
    'I record an effect from "{source:Quoted}" that draws {draw:d} card'
    " and changes my life by {life:d}"
)
def step_impl(context: Any, source: str, draw: int, life: int) -> None:
    context.agent.call("effect", source=source, delta={"draw": draw, "life": life})


@when(
    'I record an effect from "{source:Quoted}" that looks at the top {count:d} cards,'
    ' the rest going to "{rest:Quoted}"'
)
def step_impl(context: Any, source: str, count: int, rest: str) -> None:
    agent = context.agent
    agent.hand_before_look = len(agent.names_in(Zone.HAND))
    look = {"look": {"n": count, "from": "top", "rest": rest}}
    agent.call("effect", source=source, delta=look)
    agent.look = agent.text


@when(
    'I record an effect from "{source:Quoted}" that looks at the top {count:d} cards,'
    ' the rest going to "{rest:Quoted}", after the change number I last saw'
)
def step_impl(context: Any, source: str, count: int, rest: str) -> None:
    agent = context.agent
    agent.change_at_start = agent.change()
    look = {"look": {"n": count, "from": "top", "rest": rest}}
    agent.call("effect", source=source, delta=look, after=agent.change_at_start)


@when("I choose the first revealed card for my hand")
def step_impl(context: Any) -> None:
    agent = context.agent
    revealed = REVEALED.search(agent.look)
    assert revealed, agent.look
    selections = {"hand": [revealed.group("first").strip()]}
    agent.call("choose", choice_id=revealed.group("choice"), selections=selections)


@then("my hand holds one card more than before the look")
def step_impl(context: Any) -> None:
    agent = context.agent
    assert len(agent.names_in(Zone.HAND)) == agent.hand_before_look + 1
