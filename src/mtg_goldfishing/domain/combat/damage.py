"""Combat damage: applying the declared attack on entering the combat damage step."""

from __future__ import annotations

import re

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AttackerDamage,
    CombatDamageDealt,
    CombatDamageToSeats,
    DamagedSeat,
    Event,
    SeatHit,
)
from mtg_goldfishing.domain.game.cards_in_play import face_name, power
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.elimination import check_eliminations
from mtg_goldfishing.domain.game.model import OPPONENTS, Attack, CardInstance, Game, Zone
from mtg_goldfishing.domain.game.notices import examine_end_conditions
from mtg_goldfishing.domain.game.seats import SeatNumber

_NUMBER = re.compile(r"^-?\d+$")


def numeric_power(deck: LoadedDeck, card: CardInstance) -> int | None:
    """The power of the face in play as a number, or None when it is not one."""
    value = power(deck, card)
    if value is None or not _NUMBER.match(value.strip()):
        return None
    return int(value)


def default_damage(deck: LoadedDeck, card: CardInstance) -> int:
    base = numeric_power(deck, card) or 0
    return max(0, base + card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0))


# @spec CMBT-022, CMBT-023, CMBT-024, CMBT-025, CMBT-026, CMBT-027
def deal_combat_damage(game: Game, deck: LoadedDeck, decks: Decks | None = None) -> list[Event]:
    """Each unblocked attacker still on the battlefield deals its damage to a goldfish game's
    imaginary opponents, or to the seat it attacks in a contested game; then the attack ends.
    `decks` gives each seat's deck; omitted, every seat plays `deck`."""
    attack = game.declared_attack
    if attack is None:
        return []
    if game.contested:
        return _deal_to_seats(game, decks or Decks.everyone_playing(game, deck), attack)
    imaginary = game.imaginary_opponents
    hits: list[AttackerDamage] = []
    for attacker_id in attack.attackers:
        card = game.find(attacker_id)
        if attacker_id in attack.blocked or card is None or card.zone is not Zone.BATTLEFIELD:
            continue
        damage = attack.damage.get(attacker_id, default_damage(deck, card))
        imaginary.damage_dealt += damage
        target = None
        if card.is_commander:
            target = attack.commander_targets.get(attacker_id, 0)
            imaginary.commander_damage.setdefault(card.id, [0] * OPPONENTS)[target] += damage
        hits.append(AttackerDamage(face_name(deck, card), damage, target))
    game.declared_attack = None
    commanders = game.commanders_of(game.active_seat.number)
    events: list[Event] = [
        CombatDamageDealt(
            tuple(hits),
            imaginary.damage_dealt,
            tuple((c.name, tuple(imaginary.commander_damage[c.id])) for c in commanders),  # type: ignore[misc]
        )
    ]
    events.extend(examine_end_conditions(game))
    return events


def _damage_of(game: Game, decks: Decks, attack: Attack, card: CardInstance) -> int | None:
    """What one attacker deals the seat it attacks, or None when it deals nothing: it has
    left the battlefield, changed control or lost its target, or is blocked with no trample
    damage stated. A blocked attacker deals exactly its trample damage, whatever its power
    and its `damage` entry."""
    target = attack.targets.get(card.id)
    if card.zone is not Zone.BATTLEFIELD or card.controller != game.active or target is None:
        return None
    if not game.seat(SeatNumber(target)).in_game:
        return None
    if card.id in attack.blocked:
        return attack.trample.get(card.id)
    return attack.damage.get(card.id, default_damage(decks.of(card.owner), card))


def _commander_damage_to(game: Game, seat: SeatNumber) -> tuple[tuple[str, int], ...]:
    """Each commander's combat damage to a seat so far, for those that have dealt it any."""
    return tuple(
        (commander.name, dealt)
        for owner in game.seats
        for commander in game.commanders_of(owner.number)
        if (dealt := owner.commander_damage_to(commander, seat))
    )


# @spec CMBT-050, CMBT-052, CMBT-061, CMBT-062, CMBT-063, CMBT-064, CMBT-065, CMBT-066
# @spec CMBT-067, CMBT-074, CMBT-075, CMBT-077, CMBT-082, CMBT-097, GAME-130
def _deal_to_seats(game: Game, decks: Decks, attack: Attack) -> list[Event]:
    """Each attacker's damage comes off the life of the seat it attacks, a commander's also
    counting against that seat; nothing happens to any creature. Eliminations follow, once
    the whole combat's damage has been applied."""
    hits: list[SeatHit] = []
    damaged: list[SeatNumber] = []
    for attacker_id in attack.attackers:
        card = game.find(attacker_id)
        dealt = None if card is None else _damage_of(game, decks, attack, card)
        if card is None or dealt is None:
            continue
        target = SeatNumber(attack.targets[attacker_id])
        game.seat(target).life -= dealt
        if card.is_commander:
            by_seat = game.seat(card.owner).commander_damage.setdefault(card.id, {})
            by_seat[str(target.value)] = by_seat.get(str(target.value), 0) + dealt
        hits.append(SeatHit(face_name(decks.of(card.owner), card), dealt, target))
        if target not in damaged:
            damaged.append(target)
    game.declared_attack = None
    seats = tuple(
        DamagedSeat(seat, game.seat(seat).life, _commander_damage_to(game, seat))
        for seat in damaged
    )
    return [CombatDamageToSeats(tuple(hits), seats), *check_eliminations(game)]
