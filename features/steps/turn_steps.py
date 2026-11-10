"""Advancing through the turn and declaring attacks."""

# @spec APP-025

from typing import Any

from behave import when


@when('I advance to "{step:Quoted}" discarding "{card:Quoted}"')
def step_impl(context: Any, step: str, card: str) -> None:
    context.agent.call("advance", to=step, discard=[card])


@when('I advance to "{step:Quoted}"')
def step_impl(context: Any, step: str) -> None:
    context.agent.call("advance", to=step)


@when('I attack with "{first:Quoted}" and "{second:Quoted}", both with haste')
def step_impl(context: Any, first: str, second: str) -> None:
    attackers = [first, second]
    context.agent.call("attack", attackers=attackers, haste=attackers)


@when('I attack with "{attacker:Quoted}" with haste, and it is blocked')
def step_impl(context: Any, attacker: str) -> None:
    context.agent.call("attack", attackers=[attacker], haste=[attacker], blocked=[attacker])
