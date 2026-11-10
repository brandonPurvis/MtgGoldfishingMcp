"""Naming cards in calls: full names, face names or instance ids, ignoring case."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, InstanceChosen
from mtg_goldfishing.domain.game.cards_in_play import names_of
from mtg_goldfishing.domain.game.model import CardInstance, Game, Zone

_INSTANCE_ID = re.compile(r"^c\d+$", re.IGNORECASE)


class Purpose(Enum):
    """What the operation will do with the card, which decides the natural candidate."""

    ANY = "any"
    TAP = "tap"
    UNTAP = "untap"


def is_instance_id(name: str) -> bool:
    return bool(_INSTANCE_ID.match(name.strip()))


def matches(deck: LoadedDeck, card: CardInstance, name: str) -> bool:
    """Whether a name given in a call refers to this instance."""
    wanted = name.strip().casefold()
    if is_instance_id(name):
        return card.id == wanted
    return any(candidate.casefold() == wanted for candidate in names_of(deck, card))


def _preference(card: CardInstance, purpose: Purpose) -> tuple[int, int]:
    natural = {Purpose.TAP: not card.tapped, Purpose.UNTAP: card.tapped}.get(purpose, True)
    return (0 if natural else 1, card.number)


def _differ(cards: Sequence[CardInstance]) -> bool:
    first = cards[0]
    return any(
        (c.tapped, c.counters, c.face) != (first.tapped, first.counters, first.face)
        for c in cards[1:]
    )


def _missing(game: Game, deck: LoadedDeck, name: str, zones: Sequence[Zone]) -> Error:
    elsewhere = next(
        (c.zone.value for c in game.cards if c.zone not in zones and matches(deck, c, name)),
        None,
    )
    return Error(
        ErrorKind.CARD_NOT_IN_ZONE,
        subject=name,
        zone=" or ".join(zone.value for zone in zones),
        found_in=elsewhere,
    )


# @spec GAME-013, GAME-014, GAME-015, GAME-016, GAME-017, GAME-018
def resolve(
    game: Game,
    deck: LoadedDeck,
    names: Sequence[str],
    zones: Sequence[Zone],
    purpose: Purpose = Purpose.ANY,
) -> tuple[list[CardInstance], list[InstanceChosen]] | Error:
    """Resolve each name to a different instance in the expected zones, in zone order.

    Instance ids are resolved first; each name then takes a matching instance no id or
    earlier name has taken, so a name given more than once means that many different
    instances. When the matching instances differ from one another, the chosen instance
    is reported by id. The result follows the order of the names given.
    """

    def candidates_for(name: str) -> list[CardInstance]:
        return [
            card
            for zone in zones
            for card in sorted(game.in_zone(zone), key=lambda c: _preference(c, purpose))
            if matches(deck, card, name)
        ]

    picks: dict[int, CardInstance] = {}
    taken: set[str] = set()
    for position, name in enumerate(names):
        if not is_instance_id(name):
            continue
        key = name.strip().lower()
        if key in taken:
            return Error(ErrorKind.INSTANCE_REPEATED, subject=key)
        found = candidates_for(name)
        if not found:
            return _missing(game, deck, name, zones)
        picks[position] = found[0]
        taken.add(key)
    named_by_id = set(taken)
    reported: list[InstanceChosen] = []
    for position, name in enumerate(names):
        if is_instance_id(name):
            continue
        candidates = candidates_for(name)
        if not candidates:
            return _missing(game, deck, name, zones)
        free = [card for card in candidates if card.id not in taken]
        if not free:
            wanted = name.strip().casefold()
            return Error(
                ErrorKind.TOO_FEW_MATCHING,
                subject=name,
                number=len(candidates),
                expected=sum(1 for n in names if n.strip().casefold() == wanted)
                + sum(1 for card in candidates if card.id in named_by_id),
            )
        pick = free[0]
        if len(candidates) > 1 and _differ(candidates):
            reported.append(InstanceChosen(name, pick.id))
        picks[position] = pick
        taken.add(pick.id)
    return [picks[position] for position in range(len(names))], reported


def resolve_one(
    game: Game,
    deck: LoadedDeck,
    name: str,
    zones: Sequence[Zone],
    purpose: Purpose = Purpose.ANY,
) -> tuple[CardInstance, list[InstanceChosen]] | Error:
    found = resolve(game, deck, [name], zones, purpose)
    if isinstance(found, Error):
        return found
    cards, reported = found
    return cards[0], reported
