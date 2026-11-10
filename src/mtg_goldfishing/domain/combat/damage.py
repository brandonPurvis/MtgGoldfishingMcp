"""Combat damage: applying the declared attack on entering the combat damage step."""

from __future__ import annotations

import re

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import AttackerDamage, CombatDamageDealt, Event
from mtg_goldfishing.domain.game.cards_in_play import face_name, power
from mtg_goldfishing.domain.game.model import OPPONENTS, CardInstance, Game, Zone
from mtg_goldfishing.domain.game.notices import examine_end_conditions

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
def deal_combat_damage(game: Game, deck: LoadedDeck) -> list[Event]:
    """Each unblocked attacker still on the battlefield deals its damage to a goldfish game's
    imaginary opponents; then the attack ends."""
    attack = game.declared_attack
    if attack is None:
        return []
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
