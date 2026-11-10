"""`expect`: comparing what the agent believes with the game's state, as warnings."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import ExpectationMismatched
from mtg_goldfishing.domain.game.cards_in_play import is_land
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.arguments import Expectation
from mtg_goldfishing.domain.steps import Step


def next_cast_tax(game: Game, seat: SeatNumber) -> int:
    """The tax on the seat's next cast of its commander; the higher, with two commanders."""
    return max((game.seat(seat).commander_tax(c) for c in game.commanders_of(seat)), default=0)


def _counted(game: Game, deck: LoadedDeck, seat: SeatNumber, key: str) -> int:
    counted = game.seat(seat)
    lands = [card for card in game.battlefield_of(seat) if is_land(deck, card)]
    imaginary = game.imaginary
    values = {
        "hand": lambda: len(game.hand_of(seat)),
        "lands": lambda: len(lands),
        "untapped_lands": lambda: sum(1 for card in lands if not card.tapped),
        "life": lambda: counted.life,
        "library": lambda: len(counted.library),
        "tax": lambda: next_cast_tax(game, seat),
        "damage_dealt": lambda: imaginary.damage_dealt if imaginary else 0,
    }
    return values[key]()


def _mismatch(
    game: Game, deck: LoadedDeck, seat: SeatNumber, expected: Expectation
) -> ExpectationMismatched | None:
    value = expected.value
    if isinstance(value, ManaString):
        pool = game.seat(seat).mana_pool
        if pool.same_symbols_as(value):
            return None
        return ExpectationMismatched(expected.key, str(pool), str(value) or "{}")
    if isinstance(value, Step):
        if game.step is value:
            return None
        actual = game.step.value if game.step else "none"
        return ExpectationMismatched(expected.key, actual, value.value)
    count = _counted(game, deck, seat, expected.key)
    if count == value:
        return None
    return ExpectationMismatched(expected.key, str(count), str(value))


# @spec PLAY-068, PLAY-069, PLAY-071, PLAY-072, PLAY-073
def compare(
    game: Game, deck: LoadedDeck, seat: SeatNumber, expectations: Sequence[Expectation]
) -> list[ExpectationMismatched]:
    """One warning per value the acting seat expects that differs from the game as it now
    stands, as that seat's own."""
    found = (_mismatch(game, deck, seat, expected) for expected in expectations)

    return [mismatch for mismatch in found if mismatch is not None]
