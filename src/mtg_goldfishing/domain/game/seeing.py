"""What a seat may see of the events of a call: the public filter.

What a seat is shown of an event depends on whose hidden zones the event touches, never on
whose call caused it. An event that moves a card into, between or out of a seat's own hand
or library is shown to that seat by name; every other seat sees its public form. Cards
revealed by a pending choice are shown only to the seat the choice is addressed to.

The public form of an event is what any seat may see of it: a card moved from one hidden
zone to another is a count; a card moved between a hidden zone and a public zone or the
stack is named, since it is seen on one side of the move; a mulligan or a kept hand is its
counts; a reveal is its kind and seats. A goldfish game's events name no seat and are shown
as they are.
"""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.events import (
    CardMoved,
    CardsDrawn,
    CardsRevealed,
    ChoiceResolved,
    ChoiceRevealedTo,
    Event,
    HandKept,
    HiddenCardsDrawn,
    HiddenCardsMoved,
    HiddenHandKept,
    HiddenMulliganTaken,
    MulliganTaken,
    Placement,
)
from mtg_goldfishing.domain.game.seats import SeatNumber

HIDDEN = frozenset({"hand", "library", "library_top", "library_bottom"})
"""The zones and destinations a seat's cards are hidden in: its hand and its library."""


def _hides_from(seat: SeatNumber | None, viewer: SeatNumber | None) -> bool:
    """Whether what belongs to `seat`'s hidden zones is hidden from `viewer`; `viewer` None
    stands for any seat at all."""
    return seat is not None and seat != viewer


def _between_hidden_zones(from_zone: str, to: str) -> bool:
    return from_zone in HIDDEN and to in HIDDEN


def _placed(event: ChoiceResolved, viewer: SeatNumber | None) -> tuple[Event, ...]:
    """Revealed cards placed: those moved from one hidden zone of another seat to another are
    counted, every other placement named."""
    shown: list[Placement] = []
    counted: dict[tuple[SeatNumber, str, str], int] = {}
    for placement in event.placements:
        owner = placement.owner
        if (
            owner is not None
            and _hides_from(owner, viewer)
            and _between_hidden_zones(placement.from_zone, placement.to)
        ):
            key = (owner, placement.from_zone, placement.to)
            counted[key] = counted.get(key, 0) + 1
        else:
            shown.append(placement)
    hidden = tuple(
        HiddenCardsMoved(seat, from_zone, to, count)
        for (seat, from_zone, to), count in counted.items()
    )
    if not counted:
        return (event,)
    return (ChoiceResolved(tuple(shown)), *hidden) if shown else hidden


def _seen(event: Event, viewer: SeatNumber | None) -> tuple[Event, ...]:
    match event:
        case CardsDrawn(seat=seat) if seat is not None and _hides_from(seat, viewer):
            return (HiddenCardsDrawn(seat, len(event.cards)),)
        case CardsRevealed(seat=seat) if seat is not None and _hides_from(seat, viewer):
            return (ChoiceRevealedTo(event.kind, seat, event.hand_of),)
        case MulliganTaken(seat=seat) if seat is not None and _hides_from(seat, viewer):
            return (HiddenMulliganTaken(seat, event.mulligans),)
        case HandKept(seat=seat) if seat is not None and _hides_from(seat, viewer):
            return (HiddenHandKept(seat, len(event.hand), len(event.bottomed)),)
        case CardMoved(owner=owner) if (
            owner is not None
            and _hides_from(owner, viewer)
            and _between_hidden_zones(event.from_zone, event.to)
        ):
            return (HiddenCardsMoved(owner, event.from_zone, event.to, 1),)
        case ChoiceResolved():
            return _placed(event, viewer)
        case _:
            return (event,)


# @spec APP-033, GAME-107, TURN-042, GAME-090, GAME-094, GAME-095, GAME-154
def as_seen_by(events: Sequence[Event], seat: SeatNumber) -> tuple[Event, ...]:
    """The events as `seat` may see them: what touches its own hand or library by name,
    what touches another seat's in its public form, and cards revealed for another seat's
    pending choice as the choice's kind and seats."""
    return tuple(shown for event in events for shown in _seen(event, seat))


# @spec APP-033, GAME-091, GAME-092, GAME-093, GAME-094, GAME-153, GAME-168
def public_form(events: Sequence[Event]) -> tuple[Event, ...]:
    """The events as any seat may see them: the public form of each."""
    return tuple(shown for event in events for shown in _seen(event, None))
