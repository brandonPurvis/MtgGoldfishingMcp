"""The facts behind the status line every response about a game ends with."""

from __future__ import annotations

from dataclasses import dataclass

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Asked, NoticeKind
from mtg_goldfishing.domain.game.asking import seats_to_act
from mtg_goldfishing.domain.game.cards_in_play import is_land
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import OPPONENTS, Game, GameStatus, Seat
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
    """What the status line shows of another seat: its life, or that it is out, and the
    combat damage the calling seat has taken from each of its commanders, in their name
    order."""

    seat: SeatNumber
    life: int
    eliminated: bool
    commander_damage_taken: tuple[int, ...] = ()


@dataclass(frozen=True)
class TableSummary:
    """What a contested game's status line adds: the calling seat, the active seat, every
    other seat's standing in ascending seat number, the stack's size and who is to act.

    `time_asked` is how long, in whole seconds, the seats to act have been asked what they
    are asked now, when the calling seat is not among them and that is known; the domain
    reads no clock, so the application gives it.
    """

    seat: SeatNumber
    active: SeatNumber | None
    others: tuple[SeatStanding, ...]
    stack: int
    asked: Asked | None
    eliminated: bool
    time_asked: int | None = None


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
    seat_notices: tuple[tuple[NoticeKind, SeatNumber], ...] = ()
    """The notices that are one seat's own, every seat's, in seat order."""


# @spec GAME-145, GAME-043
def seat_notices(game: Game) -> tuple[tuple[NoticeKind, SeatNumber], ...]:
    """Every seat's own notices, seat by seat, shown to every seat."""
    return tuple((notice, seat.number) for seat in game.seats for notice in seat.notices)


def _standing(game: Game, other: Seat, seat: SeatNumber) -> SeatStanding:
    """Another seat's life, and the combat damage `seat` has taken from its commanders."""
    taken = tuple(
        other.commander_damage_to(commander, seat) for commander in game.commanders_of(other.number)
    )
    return SeatStanding(other.number, other.life, other.eliminated, taken)


# @spec GAME-089, APP-035, TOOL-046, TOOL-060, TOOL-093
def summarize(
    game: Game, deck: LoadedDeck, seat: SeatNumber, *, decks: Decks | None = None
) -> GameSummary:
    """The game as one seat's status line shows it: that seat's own turn count, zones, pool,
    life and commanders; a goldfish game's damage to its imaginary opponents; and, in a
    contested game, every other seat's life and who is to act. Its lands are those it
    controls, each read from its owner's deck (`decks`; omitted, every seat plays `deck`)."""
    every = decks or Decks.everyone_playing(game, deck)
    shown = game.seat(seat)
    imaginary = game.imaginary
    others = [other for other in game.seats if other.number != seat]
    lands = [card for card in game.battlefield_of(seat) if is_land(every.of(card.owner), card)]
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
        seat_notices=seat_notices(game),
        table=None
        if imaginary
        else TableSummary(
            seat=seat,
            active=game.active,
            others=tuple(_standing(game, o, seat) for o in others),
            stack=len(game.stack),
            asked=seats_to_act(game),
            eliminated=shown.eliminated,
        ),
    )
