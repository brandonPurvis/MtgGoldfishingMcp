"""The facts behind the status line every response about a game ends with."""

from __future__ import annotations

from dataclasses import dataclass

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import NoticeKind
from mtg_goldfishing.domain.game.cards_in_play import is_land
from mtg_goldfishing.domain.game.model import OPPONENTS, Game, GameStatus
from mtg_goldfishing.domain.steps import Step


@dataclass(frozen=True)
class CommanderStatus:
    name: str
    damage: tuple[int, ...]
    tax: int


@dataclass(frozen=True)
class GameSummary:
    game_id: str
    status: GameStatus
    turn: int
    step: Step | None
    hand: int
    lands: int
    untapped_lands: int
    pool: str
    life: int
    damage_dealt: int
    commanders: tuple[CommanderStatus, ...]
    change: int
    mulligans: int
    result: str | None
    notices: tuple[NoticeKind, ...]


def summarize(game: Game, deck: LoadedDeck) -> GameSummary:
    lands = [card for card in game.battlefield if is_land(deck, card)]
    return GameSummary(
        game_id=game.game_id,
        status=game.status,
        turn=game.turn,
        step=game.step,
        hand=len(game.hand),
        lands=len(lands),
        untapped_lands=sum(1 for card in lands if not card.tapped),
        pool=str(game.mana_pool),
        life=game.life,
        damage_dealt=game.damage_dealt,
        commanders=tuple(
            CommanderStatus(
                name=commander.name,
                damage=tuple(game.commander_damage.get(commander.id, [0] * OPPONENTS)),
                tax=game.commander_tax(commander),
            )
            for commander in game.commanders
        ),
        change=game.change,
        mulligans=game.mulligans,
        result=game.result.outcome.value if game.result else None,
        notices=tuple(game.notices),
    )
