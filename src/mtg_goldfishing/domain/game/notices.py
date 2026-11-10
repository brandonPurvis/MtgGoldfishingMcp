"""End conditions: watched for, announced by notices, never acted on."""

from __future__ import annotations

from mtg_goldfishing.domain.events import Event, NoticeKind
from mtg_goldfishing.domain.game.model import (
    COMMANDER_DAMAGE_TO_WIN,
    DAMAGE_TO_WIN,
    OPPONENTS,
    Game,
)
from mtg_goldfishing.domain.game.movement import raise_notice


def _commander_damage_reached(game: Game) -> bool:
    return all(
        any(
            damage[opponent] >= COMMANDER_DAMAGE_TO_WIN for damage in game.commander_damage.values()
        )
        for opponent in range(OPPONENTS)
    )


# @spec GAME-038, GAME-039, GAME-041, PLAY-051
def examine_end_conditions(game: Game) -> list[Event]:
    """Raise every notice whose end condition now holds and has not been raised before."""
    events: list[Event] = []
    if game.damage_dealt >= DAMAGE_TO_WIN:
        events.extend(raise_notice(game, NoticeKind.DAMAGE))
    if game.commander_damage and _commander_damage_reached(game):
        events.extend(raise_notice(game, NoticeKind.COMMANDER_DAMAGE))
    if game.life <= 0:
        events.extend(raise_notice(game, NoticeKind.LIFE))
    return events


# @spec GAME-040
def examine_turn_limit(game: Game) -> list[Event]:
    if game.turn_limit is not None and game.turn == game.turn_limit:
        return raise_notice(game, NoticeKind.TURN_LIMIT)
    return []
