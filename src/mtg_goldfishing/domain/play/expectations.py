"""`expect`: comparing what the agent believes with the game's state, as warnings."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import ExpectationMismatched
from mtg_goldfishing.domain.game.cards_in_play import is_land
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.arguments import Expectation
from mtg_goldfishing.domain.steps import Step


def next_cast_tax(game: Game) -> int:
    """The tax on the next cast of the commander; the higher, with two commanders."""
    return max((game.commander_tax(c) for c in game.commanders), default=0)


def _counted(game: Game, deck: LoadedDeck, key: str) -> int:
    lands = [card for card in game.battlefield if is_land(deck, card)]
    return {
        "hand": lambda: len(game.hand),
        "lands": lambda: len(lands),
        "untapped_lands": lambda: sum(1 for card in lands if not card.tapped),
        "life": lambda: game.life,
        "library": lambda: len(game.library),
        "tax": lambda: next_cast_tax(game),
        "damage_dealt": lambda: game.damage_dealt,
    }[key]()


def _mismatch(game: Game, deck: LoadedDeck, expected: Expectation) -> ExpectationMismatched | None:
    value = expected.value
    if isinstance(value, ManaString):
        if game.mana_pool.same_symbols_as(value):
            return None
        return ExpectationMismatched(expected.key, str(game.mana_pool), str(value) or "{}")
    if isinstance(value, Step):
        if game.step is value:
            return None
        actual = game.step.value if game.step else "none"
        return ExpectationMismatched(expected.key, actual, value.value)
    count = _counted(game, deck, expected.key)
    if count == value:
        return None
    return ExpectationMismatched(expected.key, str(count), str(value))


# @spec PLAY-068, PLAY-069, PLAY-071, PLAY-072, PLAY-073
def compare(
    game: Game, deck: LoadedDeck, expectations: Sequence[Expectation]
) -> list[ExpectationMismatched]:
    """One warning per expected value that differs from the game as it now stands."""
    found = (_mismatch(game, deck, expected) for expected in expectations)
    return [mismatch for mismatch in found if mismatch is not None]
