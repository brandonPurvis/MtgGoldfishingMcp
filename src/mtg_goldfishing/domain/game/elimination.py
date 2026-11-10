"""Elimination: a seat leaving a contested game at 0 life, at 21 combat damage from one
commander, or by conceding.

The game checks every seat still in it once a delta has been applied in full and once a
combat's damage has been applied, never partway through either. An eliminated seat's cards
leave the game, the permanents it controlled go back to their owners, and the pending
choices it would answer, or that show its hand, are discarded. Its turn, if it was the
active seat, ends once nothing is left waiting (see `turn`).
"""

from __future__ import annotations

from mtg_goldfishing.domain.events import EliminationCause, Event, NoticeKind, SeatEliminated
from mtg_goldfishing.domain.game.model import COMMANDER_DAMAGE_TO_WIN, Game, GameStatus
from mtg_goldfishing.domain.game.movement import raise_notice
from mtg_goldfishing.domain.game.seats import SeatNumber


def _commander_damage_to(game: Game, seat: SeatNumber) -> int:
    """The most combat damage any one commander has dealt to a seat."""
    return max(
        (
            damage.get(str(seat.value), 0)
            for other in game.seats
            for damage in other.commander_damage.values()
        ),
        default=0,
    )


def _cause(game: Game, seat: SeatNumber) -> EliminationCause | None:
    """Why a seat leaves the game now, if it does: life first, then commander damage."""
    if game.seat(seat).life <= 0:
        return EliminationCause.LIFE
    if _commander_damage_to(game, seat) >= COMMANDER_DAMAGE_TO_WIN:
        return EliminationCause.COMMANDER_DAMAGE
    return None


def _from_the_active_seat(game: Game) -> list[SeatNumber]:
    """Every seat in turn order starting from the active seat (from the first seat when no
    seat is active)."""
    first = game.active or game.seats[0].number
    return [first, *(other.number for other in game.others_from(first))]


# @spec GAME-128, GAME-129, GAME-130, GAME-139, GAME-141, GAME-160, GAME-169, CMBT-065
def check_eliminations(game: Game) -> list[Event]:
    """Eliminate, one at a time in turn order from the active seat, every seat still in a
    contested game that is at 0 life or less or has been dealt 21 combat damage by one
    commander. A goldfish game's seat is never eliminated."""
    if not game.contested:
        return []
    events: list[Event] = []
    for seat in _from_the_active_seat(game):
        if not game.seat(seat).in_game:
            continue
        cause = _cause(game, seat)
        if cause is not None:
            events.extend(eliminate(game, seat, cause))
    return events


# @spec GAME-132, GAME-133, GAME-135, GAME-138, GAME-162, GAME-163, GAME-142, GAME-143
# @spec TURN-036
def eliminate(
    game: Game, seat: SeatNumber, cause: EliminationCause, notes: str = ""
) -> list[Event]:
    """The seat leaves the game.

    Every card it owns leaves every zone; every permanent it controls but does not own
    returns to its owner. The pending choices addressed to it, and every look at its hand,
    are discarded; an `ask` its effect made of another seat still waits. When it is the
    active seat, its declared attack and the blocks asked for it are discarded too.
    """
    leaving = game.seat(seat)
    leaving.eliminated = True
    leaving.library = []
    game.cards = [card for card in game.cards if card.owner != seat]
    for card in game.cards:
        if card.controller == seat:
            card.controller = card.owner
    active_out = game.active == seat
    game.pending = [
        choice
        for choice in game.pending
        if seat not in (choice.seat, choice.hand_of)
        and not (active_out and choice.kind == "blocks")
    ]
    game.hand_looks = [look for look in game.hand_looks if seat not in (look.seat, look.hand_of)]
    if active_out:
        game.declared_attack = None
    if game.status is GameStatus.PENDING_CHOICE and not game.pending:
        game.status = GameStatus.ACTIVE
    events: list[Event] = [SeatEliminated(seat, cause, notes)]
    if leaving.tested:
        events.extend(raise_notice(game, NoticeKind.TESTED_SEAT_ELIMINATED))
    if all(not other.in_game for other in game.seats if not other.tested):
        events.extend(raise_notice(game, NoticeKind.OPPONENTS_ELIMINATED))
    return events
