"""The facts behind the status line every response about a game ends with."""

from __future__ import annotations

from dataclasses import dataclass

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Asked, NoticeKind
from mtg_goldfishing.domain.game.acting import seats_to_act
from mtg_goldfishing.domain.game.cards_in_play import is_land
from mtg_goldfishing.domain.game.model import OPPONENTS, Game, GameStatus
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.steps import Step


@dataclass(frozen=True)
class CommanderStatus:
    """A commander's damage — to each imaginary opponent in a goldfish game, to each other
    seat in ascending seat number in a contested game — and its tax."""

    name: str
    damage: tuple[int, ...]
    tax: int


@dataclass(frozen=True)
class SeatStanding:
    """What the status line shows of another seat: its life, or that it is out."""

    seat: SeatNumber
    life: int
    eliminated: bool


@dataclass(frozen=True)
class TableSummary:
    """What a contested game's status line adds: the calling seat, the active seat, every
    other seat's standing in ascending seat number, the stack's size and who is to act."""

    seat: SeatNumber
    active: SeatNumber | None
    others: tuple[SeatStanding, ...]
    stack: int
    asked: Asked | None
    eliminated: bool


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
    table: TableSummary | None = None


# @spec GAME-089, APP-035
def summarize(game: Game, deck: LoadedDeck, seat: SeatNumber) -> GameSummary:
    """The game as one seat's status line shows it: that seat's own turn count, zones, pool,
    life and commanders; a goldfish game's damage to its imaginary opponents; and, in a
    contested game, every other seat's life and who is to act."""
    shown = game.seat(seat)
    imaginary = game.imaginary
    others = [other for other in game.seats if other.number != seat]
    lands = [card for card in game.battlefield_of(seat) if is_land(deck, card)]
    return GameSummary(
        game_id=game.game_id,
        status=game.status,
        turn=shown.turns,
        step=game.step,
        hand=len(game.hand_of(seat)),
        lands=len(lands),
        untapped_lands=sum(1 for card in lands if not card.tapped),
        pool=str(shown.mana_pool),
        life=shown.life,
        damage_dealt=imaginary.damage_dealt if imaginary else 0,
        commanders=tuple(
            CommanderStatus(
                name=commander.name,
                damage=tuple(
                    imaginary.commander_damage.get(commander.id, [0] * OPPONENTS)
                    if imaginary
                    else (shown.commander_damage_to(commander, o.number) for o in others)
                ),
                tax=shown.commander_tax(commander),
            )
            for commander in game.commanders_of(seat)
        ),
        change=game.change,
        mulligans=shown.mulligans,
        result=game.result.outcome.value if game.result else None,
        notices=tuple(game.notices),
        table=None
        if imaginary
        else TableSummary(
            seat=seat,
            active=game.active,
            others=tuple(SeatStanding(o.number, o.life, o.eliminated) for o in others),
            stack=0,
            asked=seats_to_act(game),
            eliminated=shown.eliminated,
        ),
    )
