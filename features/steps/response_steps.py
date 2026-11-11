"""What the agent reads: the status word, the summary and event lines, and the status line."""

# @spec APP-025

import json
from typing import Any

from behave import then, when
from tests.support.responses import headline


@then("the response is {status:w}")
def step_impl(context: Any, status: str) -> None:
    assert headline(context.agent.text).split(maxsplit=1)[0] == status, context.agent.text


@then('the response says "{words}"')
def step_impl(context: Any, words: str) -> None:
    assert words in context.agent.text, context.agent.text


@then("the response has no status line")
def step_impl(context: Any) -> None:
    assert " · #" not in context.agent.text, context.agent.text


@then('the status line reads "{line}"')
def step_impl(context: Any, line: str) -> None:
    assert context.agent.status_line == line, context.agent.status_line


@then('the status line begins "{start}"')
def step_impl(context: Any, start: str) -> None:
    assert context.agent.status_line.startswith(start), context.agent.status_line


@then('the status line shows "{part}"')
def step_impl(context: Any, part: str) -> None:
    assert part in context.agent.status_line, context.agent.status_line


@then('the status line ends with "{end}"')
def step_impl(context: Any, end: str) -> None:
    assert context.agent.status_line.endswith(end), context.agent.status_line


@then("the status line does not show a pending choice")
def step_impl(context: Any) -> None:
    assert "CHOICE pending" not in context.agent.status_line, context.agent.status_line


@then("the response carries the error flag")
def step_impl(context: Any) -> None:
    assert context.agent.last.is_error


@then("the response does not carry the error flag")
def step_impl(context: Any) -> None:
    assert not context.agent.last.is_error


@then("the game did not change")
def step_impl(context: Any) -> None:
    agent = context.agent
    assert agent.game().change == agent.change_before
    assert agent.change() == agent.change_before


@when("I ask for the game's log")
def step_impl(context: Any) -> None:
    context.agent.call("get_log")


@then("the response is JSON about the current game")
def step_impl(context: Any) -> None:
    agent = context.agent
    agent.log = json.loads(agent.text)
    assert agent.log["game"]["game_id"] == agent.game_id


@then('the log has an entry for "{tool}"')
def step_impl(context: Any, tool: str) -> None:
    assert any(entry["tool"] == tool for entry in context.agent.log["entries"])


@then('the log\'s game has the result "{result}"')
def step_impl(context: Any, result: str) -> None:
    assert context.agent.log["game"]["result"]["outcome"] == result
