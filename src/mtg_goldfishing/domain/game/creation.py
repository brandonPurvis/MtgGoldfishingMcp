"""`new_game`: a game on a loaded deck, shuffled and dealt."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    ContestedGameStarted,
    Error,
    ErrorKind,
    GameStarted,
    SeatStarted,
)
from mtg_goldfishing.domain.game.model import (
    OPENING_HAND,
    OPPONENTS,
    STARTING_LIFE,
    CardInstance,
    Game,
    ImaginaryOpponents,
    Seat,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.game.shuffling import shuffle_library, turn_order

TESTED_SEAT = SeatNumber(1)
"""The tested seat of a goldfish game, its only seat."""

MOST_OPPONENTS = 3
"""A contested game has one to three opposing seats."""


@dataclass(frozen=True)
class OpposingDeck:
    """An opposing seat as `new_game` asks for it: the deck id given, the loaded deck it
    names (None when it names none), and the seat id the seat is to have."""

    deck_id: str
    deck: LoadedDeck | None
    seat_id: str


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
# @spec GAME-055, GAME-076, GAME-084, GAME-100, GAME-056, GAME-057, GAME-058, GAME-059
# @spec GAME-060, GAME-062, GAME-063, GAME-065, GAME-066, GAME-067, GAME-068, GAME-069
# @spec GAME-070, GAME-071, GAME-072, GAME-073, GAME-074, GAME-075, GAME-077, GAME-079
# @spec GAME-082, GAME-086, GAME-087
def new_game(
    deck: LoadedDeck | None,
    *,
    deck_id: str,
    game_id: str,
    seed: int,
    turn_limit: object = None,
    draw_first_turn: object = None,
    opposing: Sequence[OpposingDeck] = (),
    starting_life: object = None,
    position: object = None,
) -> Result:
    """Create a game: a goldfish game when no opposing seat is asked for — one seat, the
    tested seat, numbered 1 and named by the game id, against three imaginary opponents — or
    a contested game of the tested seat and one opposing seat for each opposing deck.

    Instance ids go seat by seat, the tested seat first and then the opposing seats in the
    order asked for, so the tested seat's cards are numbered as in a goldfish game; turn
    order, and so the seat numbers, is drawn from the seed.
    """
    if deck is None:
        return Refusal.error(Error(ErrorKind.UNKNOWN_DECK, subject=deck_id))
    if len(opposing) > MOST_OPPONENTS:
        return Refusal.error(
            Error(ErrorKind.TOO_MANY_OPPONENTS, number=len(opposing), expected=MOST_OPPONENTS)
        )
    for asked in opposing:
        if asked.deck is None:
            return Refusal.error(Error(ErrorKind.UNKNOWN_DECK, subject=asked.deck_id))
    if turn_limit is not None and not _is_positive_int(turn_limit):
        return Refusal.error(Error(ErrorKind.BAD_TURN_LIMIT, subject=str(turn_limit)))
    if draw_first_turn is not None and not isinstance(draw_first_turn, bool):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="draw_first_turn"))
    seats = 1 + len(opposing)
    lives = _starting_lives(starting_life, seats)
    if isinstance(lives, Error):
        return Refusal.error(lives)
    place = _position(position, seats)
    if isinstance(place, Error):
        return Refusal.error(place)
    game = Game(
        game_id=game_id,
        seed=seed,
        seats=[],
        turn_limit=turn_limit if isinstance(turn_limit, int) else None,
        draw_first_turn=draw_first_turn if isinstance(draw_first_turn, bool) else True,
    )
    if not opposing:
        tested = Seat(
            TESTED_SEAT,
            SeatId(game_id),
            deck.deck_id,
            tested=True,
            life=lives[0],
            starting_life=lives[0],
        )
        seat_up(game, deck, tested)
        game.imaginary = ImaginaryOpponents(
            commander_damage={c.id: [0] * OPPONENTS for c in game.commanders_of(TESTED_SEAT)}
        )
        hand = tuple(card.name for card in game.hand_of(TESTED_SEAT))
        return Applied(game, GameStarted(game_id, seed, hand))
    asked_for = [(deck, SeatId(game_id), ""), *_opposing_seats(opposing)]
    keys = [key for _, _, key in asked_for]
    ordered = turn_order(keys[0], keys[1:], seed, place)
    for (seat_deck, seat_id, key), life in zip(asked_for, lives, strict=True):
        number = SeatNumber(ordered.index(key) + 1)
        seat = Seat(
            number,
            seat_id,
            seat_deck.deck_id,
            tested=not key,
            shuffle_key=key,
            life=life,
            starting_life=life,
        )
        seat_up(game, seat_deck, seat)
    game.seats.sort(key=lambda seat: seat.number)
    started = tuple(
        SeatStarted(seat.number, seat.seat_id.value, seat.deck_id, seat.life, seat.tested)
        for seat in game.seats
    )
    return Applied(game, ContestedGameStarted(game_id, seed, started))


def _opposing_seats(opposing: Sequence[OpposingDeck]) -> list[tuple[LoadedDeck, SeatId, str]]:
    """Each opposing seat's deck, seat id and shuffle key (`o1`, `o2`, `o3` in order)."""
    seats: list[tuple[LoadedDeck, SeatId, str]] = []
    for k, asked in enumerate(opposing, start=1):
        assert asked.deck is not None, "an opposing deck that is not loaded is refused first"
        seats.append((asked.deck, SeatId(asked.seat_id), f"o{k}"))
    return seats


def _starting_lives(value: object, seats: int) -> list[int] | Error:
    """Each seat's starting life, the tested seat's first: one number for every seat, or,
    in a contested game, a list with one value per seat. Default 40; never below 1."""
    if value is None:
        return [STARTING_LIFE] * seats
    if _is_whole(value):
        assert isinstance(value, int)
        if value < 1:
            return Error(ErrorKind.BAD_STARTING_LIFE, subject=str(value), number=seats)
        return [value] * seats
    if not isinstance(value, list):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="starting_life")
    if seats == 1 or len(value) != seats or not all(_is_positive_int(life) for life in value):
        return Error(ErrorKind.BAD_STARTING_LIFE, subject=str(value), number=seats)
    return [int(life) for life in value]


def _position(value: object, seats: int) -> int | Error | None:
    """The tested seat's place in turn order, from 1, or None to draw it from the seed.

    A goldfish game's only seat is first, and is given no position.
    """
    if value is None:
        return None
    if not _is_whole(value):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="position")
    assert isinstance(value, int)
    if seats == 1 or not 1 <= value <= seats:
        return Error(ErrorKind.BAD_POSITION, subject=str(value), number=value, expected=seats)
    return value


def _is_whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
