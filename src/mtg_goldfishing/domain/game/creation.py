"""`new_game`: a game on a loaded deck, shuffled and dealt."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, GameStarted
from mtg_goldfishing.domain.game.model import (
    OPENING_HAND,
    OPPONENTS,
    CardInstance,
    Game,
    ImaginaryOpponents,
    Seat,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.game.shuffling import shuffle_library

TESTED_SEAT = SeatNumber(1)
"""The tested seat of a goldfish game, its only seat."""


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def seat_up(game: Game, deck: LoadedDeck, seat: Seat) -> None:
    """Add a seat and its deck's cards to a game: commanders to the command zone, the rest
    to the seat's library, which is then shuffled, and seven cards dealt from it.

    Instance ids go to commanders first, then the other cards, each group ordered by
    lower-cased name with copies adjacent; the library starts in that order, which is
    ascending instance order.
    """
    game.seats.append(seat)
    for name in sorted(deck.commanders, key=str.lower):
        commander = CardInstance(
            game.new_instance_id(),
            name,
            Zone.COMMAND,
            owner=seat.number,
            controller=seat.number,
            is_commander=True,
        )
        game.cards.append(commander)
        seat.commander_casts[commander.id] = 0
    for entry in sorted(deck.entries, key=lambda e: e.name.lower()):
        for _ in range(entry.count):
            card = CardInstance(
                game.new_instance_id(),
                entry.name,
                Zone.LIBRARY,
                owner=seat.number,
                controller=seat.number,
            )
            game.cards.append(card)
            seat.library.append(card.id)
    shuffle_library(game, seat.number)
    draw(game, seat.number, OPENING_HAND)


# @spec GAME-001, GAME-002, GAME-003, GAME-005, GAME-006, GAME-007, GAME-008, GAME-009
# @spec GAME-055, GAME-076, GAME-084, GAME-100
def new_game(
    deck: LoadedDeck | None,
    *,
    deck_id: str,
    game_id: str,
    seed: int,
    turn_limit: object = None,
    draw_first_turn: object = None,
) -> Result:
    """Create a goldfish game: one seat, the tested seat, numbered 1 and named by the game
    id, against three imaginary opponents."""
    if deck is None:
        return Refusal.error(Error(ErrorKind.UNKNOWN_DECK, subject=deck_id))
    if turn_limit is not None and not _is_positive_int(turn_limit):
        return Refusal.error(Error(ErrorKind.BAD_TURN_LIMIT, subject=str(turn_limit)))
    if draw_first_turn is not None and not isinstance(draw_first_turn, bool):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="draw_first_turn"))
    game = Game(
        game_id=game_id,
        seed=seed,
        seats=[],
        turn_limit=turn_limit if isinstance(turn_limit, int) else None,
        draw_first_turn=draw_first_turn if isinstance(draw_first_turn, bool) else True,
    )
    tested = Seat(TESTED_SEAT, SeatId(game_id), deck.deck_id, tested=True)
    seat_up(game, deck, tested)
    game.imaginary = ImaginaryOpponents(
        commander_damage={c.id: [0] * OPPONENTS for c in game.commanders_of(TESTED_SEAT)}
    )
    hand = tuple(card.name for card in game.hand_of(TESTED_SEAT))
    return Applied(game, GameStarted(game_id, seed, hand))
