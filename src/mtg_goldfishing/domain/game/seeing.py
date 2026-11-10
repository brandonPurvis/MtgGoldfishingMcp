"""What a seat may see of the events of a call: the public filter.

An event that moves a card into, between or out of a seat's own hidden zones is shown to
that seat by name, whichever seat's call caused it; every other seat sees its public form.
Cards revealed by a pending choice are shown only to the seat the choice is addressed to.
"""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.events import (
    CardsDrawn,
    CardsRevealed,
    ChoiceRevealedTo,
    Event,
    HiddenCardsDrawn,
)
from mtg_goldfishing.domain.game.seats import SeatNumber


def _seen(event: Event, seat: SeatNumber) -> Event:
    if isinstance(event, CardsDrawn) and event.seat is not None and event.seat != seat:
        return HiddenCardsDrawn(event.seat, len(event.cards))
    if isinstance(event, CardsRevealed) and event.seat is not None and event.seat != seat:
        return ChoiceRevealedTo(event.kind, event.seat, event.hand_of)
    return event


# @spec APP-033, GAME-107, TURN-042, GAME-090, GAME-094
def as_seen_by(events: Sequence[Event], seat: SeatNumber) -> tuple[Event, ...]:
    """The events as `seat` may see them: a card another seat drew is shown as a count, and
    cards revealed for another seat's pending choice as the choice's kind and seats.

    A goldfish game's events name no seat and are shown as they are.
    """
    return tuple(_seen(event, seat) for event in events)
