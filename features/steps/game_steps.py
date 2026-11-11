"""Loading a deck, starting games, mulligans, and arranging what is where."""

# @spec APP-025

from typing import Any

from behave import given, then, when
from tests.support.decks import ATRAXA, a_deck_list

from mtg_goldfishing.domain.game.model import Zone

SEED = 42


@given("the Atraxa test deck is loaded")
def step_impl(context: Any) -> None:
    agent = context.agent
    response = agent.call("load_deck", cards=a_deck_list().text(), commander=ATRAXA)
    assert response.text.startswith("OK Loaded deck "), response.text
    agent.deck_id = response.text.split()[3].rstrip(":")


@given("a game in the first main step of turn 1")
def step_impl(context: Any) -> None:
    context.execute_steps("Given the Atraxa test deck is loaded")
    context.agent.start_game(SEED)
    response = context.agent.call("mulligan", keep=True)
    assert response.text.splitlines()[-1].startswith("T1 main1"), response.text


@given("I have started a game with seed {seed:d}")
@when("I start a game with seed {seed:d}")
@when("I start another game with seed {seed:d}")
def step_impl(context: Any, seed: int) -> None:
    context.agent.start_game(seed)


@then("both games were dealt the same opening hand")
def step_impl(context: Any) -> None:
    starts = [r.text for r in context.agent.responses if r.text.startswith("OK Started game")]
    hands = [text.split("Hand: ", 1)[1].splitlines()[0] for text in starts]
    assert len(hands) == 2, starts
    assert hands[0] == hands[1], hands


@when("I take a mulligan")
def step_impl(context: Any) -> None:
    context.agent.call("mulligan", keep=False)


@when("I keep the hand")
def step_impl(context: Any) -> None:
    context.agent.call("mulligan", keep=True)


@given('"{first:Quoted}" and "{second:Quoted}" are in my hand')
def step_impl(context: Any, first: str, second: str) -> None:
    context.agent.arrange([first, second], Zone.HAND)


@given('"{card:Quoted}" is in my hand')
def step_impl(context: Any, card: str) -> None:
    context.agent.arrange([card], Zone.HAND)


@given('"{card:Quoted}" is on the battlefield')
@given('my commander "{card:Quoted}" is on the battlefield')
def step_impl(context: Any, card: str) -> None:
    context.agent.arrange([card], Zone.BATTLEFIELD)


@given("I hold {count:d} cards")
def step_impl(context: Any, count: int) -> None:
    agent = context.agent
    missing = count - len(agent.names_in(Zone.HAND))
    agent.arrange([*agent.names_in(Zone.HAND), *["Forest"] * max(missing, 0)], Zone.HAND)
    agent.discard_down_to(count)
    assert len(agent.names_in(Zone.HAND)) == count


@given("I have discarded down to seven cards")
def step_impl(context: Any) -> None:
    context.agent.discard_down_to(7)


@then('"{card:Quoted}" is on the battlefield')
def step_impl(context: Any, card: str) -> None:
    assert card in context.agent.names_in(Zone.BATTLEFIELD)


@then('"{card:Quoted}" is in my graveyard')
def step_impl(context: Any, card: str) -> None:
    assert card in context.agent.names_in(Zone.GRAVEYARD)


@when('I end the game as a "{result:Quoted}" with the verdict "{notes:Quoted}"')
def step_impl(context: Any, result: str, notes: str) -> None:
    context.agent.call("end_game", result=result, notes=notes, after=context.agent.change())


@when('I ask for the rules text of "{card:Quoted}"')
def step_impl(context: Any, card: str) -> None:
    context.agent.call("get_state", card=card)
