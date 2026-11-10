"""Seats of a contested game reaching one another: effects on other seats' cards and life,
choices addressed to a seat, combat against seats, conceding and elimination.

Every call is made as one seat, through its own seat id, as the agent playing that seat would.
"""

# @spec APP-076

import json
from collections import Counter
from typing import Any

from behave import given, then, when

from mtg_goldfishing.adapters.mcp.tools import ToolResponse
from mtg_goldfishing.domain.game.model import CardInstance, Game, Zone
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


def _cards_named(context: Any, name: str) -> list[CardInstance]:
    return [card for card in _game(context).cards if card.name == name]


def _the_card(context: Any, name: str) -> CardInstance:
    (card,) = _cards_named(context, name)
    return card


def _arrange(context: Any, number: int, names: list[str], zone: Zone) -> None:
    """See that the seat holds these cards in `zone` (its hand or battlefield), bringing the
    missing ones there with one `effect` call of that seat: moved from its hand or command
    zone, or fetched from its library."""
    move: list[str] = []
    fetch: list[str] = []
    for name, wanted in Counter(names).items():
        missing = wanted - _names_in(context, number, zone).count(name)
        sources = [Zone.COMMAND] if zone is Zone.HAND else [Zone.HAND, Zone.COMMAND]
        for source in sources:
            taken = min(missing, _names_in(context, number, source).count(name))
            move.extend([name] * taken)
            missing -= taken
        fetch.extend([name] * max(missing, 0))
    delta: dict[str, object] = {}
    if move:
        delta["move"] = {zone.value: move}
    if fetch:
        delta["fetch"] = {zone.value: fetch}
    if delta:
        response = _as_seat(context, number, "effect", source="arranging the scenario", delta=delta)
        assert response.text.startswith("OK"), response.text


def _choice_id(context: Any) -> str:
    """The choice the game waits on, as the seat it is addressed to was told of it."""
    pending = _game(context).pending
    assert pending, context.agent.text
    return pending[0].choice_id


# ------------------------------------------------------------------ arranging


@given("a started contested game against {count:d} Omnath decks with the tested seat first")
def step_impl(context: Any, count: int) -> None:
    context.execute_steps(
        f"Given a started contested game against {count} Omnath deck with the tested seat first"
    )


@given(f'seat {SEAT} puts "{{card}}" onto the battlefield')
def step_impl(context: Any, number: int, card: str) -> None:
    _arrange(context, number, [card], Zone.BATTLEFIELD)


@given(f"seat {SEAT} has ended its turn")
def step_impl(context: Any, number: int) -> None:
    """Discard down to seven, then advance until the turn passes, past any reminder."""
    hand = _names_in(context, number, Zone.HAND)
    if len(hand) > 7:
        delta = {"discard": hand[7:]}
        response = _as_seat(context, number, "effect", source="arranging the scenario", delta=delta)
        assert response.text.startswith("OK"), response.text
    for _ in range(4):
        response = _as_seat(context, number, "advance", to="main1")
        assert response.text.startswith("OK"), response.text
        if _game(context).active != SeatNumber(number):
            return
    raise AssertionError(context.agent.text)


@given(f"seat {SEAT} has recorded an effect with delta {{delta}}")
def step_impl(context: Any, number: int, delta: str) -> None:
    response = _as_seat(context, number, "effect", source="a test effect", delta=json.loads(delta))
    assert response.text.startswith("OK"), response.text


# ------------------------------------------------------------------ calls


@when(f"seat {SEAT} records an effect with delta {{delta}}")
def step_impl(context: Any, number: int, delta: str) -> None:
    _as_seat(context, number, "effect", source="a test effect", delta=json.loads(delta))


@when(f"seat {SEAT} records an immediate effect with delta {{delta}}")
def step_impl(context: Any, number: int, delta: str) -> None:
    _as_seat(
        context,
        number,
        "effect",
        source="the result of combat",
        delta=json.loads(delta),
        immediate=True,
    )


@when(f"seat {SEAT} answers its ask choice by discarding a card")
def step_impl(context: Any, number: int) -> None:
    card = _names_in(context, number, Zone.HAND)[0]
    _as_seat(context, number, "choose", choice_id=_choice_id(context), delta={"discard": [card]})


@when(f"seat {SEAT} answers its blocks choice with blocks {{blocks}}")
def step_impl(context: Any, number: int, blocks: str) -> None:
    _as_seat(context, number, "choose", choice_id=_choice_id(context), blocks=json.loads(blocks))


@when(f"seat {SEAT} chooses the first revealed card for its owner's graveyard")
def step_impl(context: Any, number: int) -> None:
    choice = next(iter(_game(context).pending), None)
    assert choice is not None, context.agent.text
    first = choice.revealed[0]
    _as_seat(
        context, number, "choose", choice_id=choice.choice_id, selections={"graveyard": [first]}
    )


@when(f"seat {SEAT} discards the first card in seat S{{other:d}}'s hand by its instance id")
def step_impl(context: Any, number: int, other: int) -> None:
    hand = _game(context).hand_of(SeatNumber(other))
    context.hidden_card = hand[0].id
    _as_seat(context, number, "effect", source="a test effect", delta={"discard": [hand[0].id]})


@when(f"seat {SEAT} attacks with targets {{targets}}")
def step_impl(context: Any, number: int, targets: str) -> None:
    by_attacker = json.loads(targets)
    _as_seat(context, number, "attack", attackers=list(by_attacker), targets=by_attacker)


@when(f"seat {SEAT} attacks with {{attackers}} dealing {{damage}}")
def step_impl(context: Any, number: int, attackers: str, damage: str) -> None:
    _as_seat(context, number, "attack", attackers=json.loads(attackers), damage=json.loads(damage))


# Registered after the attacks with targets or damage, which it would also match.
@when(f"seat {SEAT} attacks with {{attackers}}")
def step_impl(context: Any, number: int, attackers: str) -> None:
    _as_seat(context, number, "attack", attackers=json.loads(attackers))


@when(f'seat {SEAT} advances to "{{step}}"')
def step_impl(context: Any, number: int, step: str) -> None:
    _as_seat(context, number, "advance", to=step)


@when(f"seat {SEAT} concedes")
def step_impl(context: Any, number: int) -> None:
    _as_seat(context, number, "end_game", result="loss", notes="beaten")


@when(f'seat {SEAT} ends the game as a "{{result}}"')
def step_impl(context: Any, number: int, result: str) -> None:
    _as_seat(context, number, "end_game", result=result, notes="a verdict")


# ------------------------------------------------------------------ what is so


@then(f"seat {SEAT}'s life is {{life:d}}")
def step_impl(context: Any, number: int, life: int) -> None:
    assert _game(context).seat(SeatNumber(number)).life == life


@then(f"seat {SEAT} is eliminated")
def step_impl(context: Any, number: int) -> None:
    assert _game(context).seat(SeatNumber(number)).eliminated


@then(f"seat {SEAT} is the active seat")
def step_impl(context: Any, number: int) -> None:
    assert _game(context).active == SeatNumber(number)


@then(f'"{{card}}" is in seat {SEAT}\'s {{zone}}')
def step_impl(context: Any, card: str, number: int, zone: str) -> None:
    named = {"graveyard": Zone.GRAVEYARD, "exile": Zone.EXILE, "hand": Zone.HAND}[zone]
    assert card in _names_in(context, number, named), _names_in(context, number, named)


@then(f"seat {SEAT}'s graveyard holds {{count:d}} card")
@then(f"seat {SEAT}'s graveyard holds {{count:d}} cards")
def step_impl(context: Any, number: int, count: int) -> None:
    assert len(_names_in(context, number, Zone.GRAVEYARD)) == count


@then(f'seat {SEAT} controls "{{card}}"')
def step_impl(context: Any, number: int, card: str) -> None:
    found = _the_card(context, card)
    assert (found.zone, found.controller) == (Zone.BATTLEFIELD, SeatNumber(number)), found


@then(f'"{{card}}" is owned by seat {SEAT}')
def step_impl(context: Any, card: str, number: int) -> None:
    assert _the_card(context, card).owner == SeatNumber(number)


@then(f"no card seat {SEAT} owns is left in the game")
def step_impl(context: Any, number: int) -> None:
    assert [c for c in _game(context).cards if c.owner == SeatNumber(number)] == []


@then("the response shows the cards of seat S{number:d}'s hand as revealed")
def step_impl(context: Any, number: int) -> None:
    hand = _game(context).hand_of(SeatNumber(number))
    revealed = next(line for line in context.agent.text.splitlines() if "(hand) revealed" in line)
    assert all(f"{card.name} ({card.id})" in revealed for card in hand), revealed


@then("the response does not show the cards of seat S{number:d}'s hand")
def step_impl(context: Any, number: int) -> None:
    hand = _game(context).hand_of(SeatNumber(number))
    assert not any(f"({card.id})" in context.agent.text for card in hand), context.agent.text


@then("the response says the card is in a hidden zone of S{number:d}")
def step_impl(context: Any, number: int) -> None:
    expected = f"ERROR {context.hidden_card} is in a hidden zone of S{number}."
    assert context.agent.text.startswith(expected), context.agent.text


@then("the game has not ended")
def step_impl(context: Any) -> None:
    assert _game(context).result is None
    assert _game(context).status.value != "ended"


@then("the game has ended")
def step_impl(context: Any) -> None:
    assert _game(context).status.value == "ended"
