"""Blocks in a contested game: on entering declare blockers, each attacked seat is asked, with a
pending choice, which of its creatures block."""

from __future__ import annotations

from mtg_goldfishing.domain.events import BlocksRequested, Event, NoBlocksDeclared
from mtg_goldfishing.domain.game.cards_in_play import face_name, is_creature
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Attack, Game, GameStatus, PendingChoice, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber

SOURCE = "combat"


def _still_attacking(game: Game, attack: Attack, attacker_id: str) -> bool:
    """An attacker still on the battlefield, under the attacking seat's control, attacking a
    seat still in the game."""
    card = game.find(attacker_id)
    target = attack.targets.get(attacker_id)
    return (
        card is not None
        and card.zone is Zone.BATTLEFIELD
        and card.controller == game.active
        and target is not None
        and game.seat(SeatNumber(target)).in_game
    )


def _can_block(game: Game, decks: Decks, seat: SeatNumber) -> bool:
    """Whether a seat controls an untapped creature."""
    return any(
        not card.tapped and is_creature(decks.of(card.owner), card)
        for card in game.battlefield_of(seat)
    )


# @spec CMBT-034, CMBT-035, CMBT-036, CMBT-037, CMBT-047, CMBT-049
def request_blocks(game: Game, decks: Decks) -> list[Event]:
    """Drop from the declared attack every attacker that has left the battlefield, changed
    control or lost its target seat; then ask each attacked seat still in the game, in turn
    order from the seat after the active seat, to block the attackers attacking it. A seat
    with no untapped creature is not asked: no blocks are declared for it."""
    attack = game.declared_attack
    if attack is None or game.active is None:
        return []
    attack.attackers = [a for a in attack.attackers if _still_attacking(game, attack, a)]
    events: list[Event] = []
    for other in game.others_from(game.active):
        attacking_it = [a for a in attack.attackers if attack.targets.get(a) == other.number.value]
        if not attacking_it or not other.in_game:
            continue
        if not _can_block(game, decks, other.number):
            events.append(NoBlocksDeclared(other.number))
            continue
        choice_id = game.new_choice_id()
        game.pending.append(
            PendingChoice(
                choice_id, other.number, SOURCE, "blocks", [], None, attackers=attacking_it
            )
        )
        names = tuple(
            face_name(decks.of(game.instance(a).owner), game.instance(a)) for a in attacking_it
        )
        events.append(BlocksRequested(choice_id, other.number, names))
    if game.pending:
        game.status = GameStatus.PENDING_CHOICE
    return events
