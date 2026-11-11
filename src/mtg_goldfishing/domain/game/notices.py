"""End conditions: watched for, announced by notices, never acted on."""

from __future__ import annotations

from mtg_goldfishing.domain.events import Event, NoticeKind
from mtg_goldfishing.domain.game.model import (
    COMMANDER_DAMAGE_TO_WIN,
    DAMAGE_TO_WIN,
    OPPONENTS,
    Game,
    ImaginaryOpponents,
)
from mtg_goldfishing.domain.game.movement import raise_notice


def _commander_damage_reached(imaginary: ImaginaryOpponents) -> bool:
    return all(
        any(
            damage[opponent] >= COMMANDER_DAMAGE_TO_WIN
            for damage in imaginary.commander_damage.values()
        )
        for opponent in range(OPPONENTS)
    )


# @spec GAME-038, GAME-039, GAME-041, GAME-140, PLAY-051, GAME-146
def examine_end_conditions(game: Game) -> list[Event]:
    """Raise every notice whose end condition now holds and has not been raised before.

    The conditions are a goldfish game's: damage to the imaginary opponents, and the tested
    seat's life, which raises a notice and never eliminates the seat.
    """
    imaginary = game.imaginary
    if imaginary is None:
        return []
    events: list[Event] = []
    if imaginary.damage_dealt >= DAMAGE_TO_WIN:
        events.extend(raise_notice(game, NoticeKind.DAMAGE))
    if imaginary.commander_damage and _commander_damage_reached(imaginary):
        events.extend(raise_notice(game, NoticeKind.COMMANDER_DAMAGE))
    if game.tested.life <= 0:
        events.extend(raise_notice(game, NoticeKind.LIFE))
    return events


# @spec GAME-040, GAME-144
def examine_turn_limit(game: Game) -> list[Event]:
    """The turn limit counts rounds; in a goldfish game the round is the turn."""
    if game.turn_limit is not None and game.round == game.turn_limit:
        return raise_notice(game, NoticeKind.TURN_LIMIT)
    return []
