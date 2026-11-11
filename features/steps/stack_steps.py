"""The stack and response windows: casting onto the stack, passing, confirming or restating a
disturbed spell, and what the stack holds, each call made as one seat through its own seat id.

Arranging a seat's cards and mana uses `effect` with `immediate: true`, a correction applied
at once, so that arranging puts nothing on the stack.
"""

# @spec APP-076

import json
from collections import Counter
from typing import Any

from behave import given, then, when
from tests.support.decks import OMNATH, an_opposing_deck_list
from tests.support.responses import headline

from mtg_goldfishing.adapters.mcp.tools import ToolResponse
from mtg_goldfishing.domain.game.model import Game, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber

SEAT = r"S{number:d}"


def _game(context: Any) -> Game:
    game: Game = context.agent.game()
    return game


def _as_seat(context: Any, number: int, tool: str, **arguments: object) -> ToolResponse:
    seat_id = context.table_of_seats.seat_id(number)
    response: ToolResponse = context.agent.call(tool, game_id=seat_id, **arguments)
    return response


def _names_in(context: Any, number: int, zone: Zone) -> list[str]:
    return [card.name for card in _game(context).in_zone(zone, SeatNumber(number))]


def _correct(context: Any, number: int, delta: dict[str, object]) -> None:
    """Arrange the scenario with an immediate effect of the seat, which must be accepted."""
    response = _as_seat(
        context, number, "effect", source="arranging the scenario", delta=delta, immediate=True
    )
    assert headline(response.text).startswith("OK"), response.text


def _choice_id(context: Any) -> str:
    pending = _game(context).pending
    assert pending, context.agent.text
    return pending[0].choice_id


# ------------------------------------------------------------------ arranging


@given('the Omnath test deck is loaded with "{card}" defined as "{text}"')
def step_impl(context: Any, card: str, text: str) -> None:
    response = context.agent.call(
        "load_deck",
        cards=an_opposing_deck_list().text(),
        commander=OMNATH,
        definitions=[{"name": card, "oracle_text": text}],
    )
    assert headline(response.text).startswith("OK Loaded deck "), response.text
    context.opposing_deck_id = response.text.split()[3].rstrip(":")


@given("a started contested game against the Atraxa deck with the tested seat first")
def step_impl(context: Any) -> None:
    context.opposing_deck_id = context.agent.deck_id
    context.execute_steps(
        "Given a started contested game against 1 Omnath deck with the tested seat first"
    )


@given(f'seat {SEAT} holds "{{card}}"')
def step_impl(context: Any, number: int, card: str) -> None:
    if card in _names_in(context, number, Zone.HAND):
        return
    if card in _names_in(context, number, Zone.COMMAND):
        _correct(context, number, {"move": {"hand": [card]}})
    else:
        _correct(context, number, {"fetch": {"hand": [card]}})


@given(f'seat {SEAT} has "{{mana}}" in its pool')
@when(f'seat {SEAT} adds "{{mana}}" to its pool')
def step_impl(context: Any, number: int, mana: str) -> None:
    _correct(context, number, {"mana": mana})


@given(f"seat {SEAT} has tapped every permanent it controls")
def step_impl(context: Any, number: int) -> None:
    battlefield = _game(context).battlefield_of(SeatNumber(number))
    untapped = [card.id for card in battlefield if not card.tapped]
    if untapped:
        _correct(context, number, {"tap": untapped})


# ------------------------------------------------------------------ calls


@when(f'seat {SEAT} casts "{{card}}"')
def step_impl(context: Any, number: int, card: str) -> None:
    _as_seat(context, number, "play", card=card)


@when(f'seat {SEAT} casts "{{card}}" with delta {{delta}}')
def step_impl(context: Any, number: int, card: str, delta: str) -> None:
    _as_seat(context, number, "play", card=card, delta=json.loads(delta))


@when(f'seat {SEAT} casts "{{card}}" with cast triggers {{triggers}}')
def step_impl(context: Any, number: int, card: str, triggers: str) -> None:
    _as_seat(context, number, "play", card=card, cast_triggers=json.loads(triggers))


@when(f'seat {SEAT} records an effect from "{{source}}" with delta {{delta}}')
def step_impl(context: Any, number: int, source: str, delta: str) -> None:
    _as_seat(context, number, "effect", source=source, delta=json.loads(delta))


@when(f"seat {SEAT} passes")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "pass")


@when(f"seat {SEAT} confirms its resolve choice")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "choose", choice_id=_choice_id(context))


@when(f"seat {SEAT} restates its resolve choice with {{restate}}")
def step_impl(context: Any, number: int, restate: str) -> None:
    _as_seat(context, number, "choose", choice_id=_choice_id(context), restate=json.loads(restate))


# ------------------------------------------------------------------ outcomes


@then("the stack is empty")
def step_impl(context: Any) -> None:
    assert _game(context).stack == [], _game(context).stack


@then("the stack holds {count:d} items")
@then("the stack holds {count:d} item")
def step_impl(context: Any, count: int) -> None:
    assert len(_game(context).stack) == count, _game(context).stack


@then(f'"{{card}}" is on seat {SEAT}' + "'s battlefield")
def step_impl(context: Any, card: str, number: int) -> None:
    held = Counter(_names_in(context, number, Zone.BATTLEFIELD))
    assert held[card] >= 1, held
