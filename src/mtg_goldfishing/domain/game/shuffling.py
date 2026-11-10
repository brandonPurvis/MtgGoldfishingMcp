"""Seeded shuffling: a seat's nth shuffle depends only on the seed, its shuffle key, n and
its library."""

from __future__ import annotations

import hashlib
import random

from mtg_goldfishing.domain.events import LibraryShuffled
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber


def shuffled(items: list[str], seed: int, n: int, shuffle_key: str = "") -> list[str]:
    """A Fisher–Yates shuffle drawing only on the generator's basic uniform float.

    The generator is seeded from `<seed>:<n>` for the tested seat, whose shuffle key is
    empty, and from `<seed>:<shuffle_key>:<n>` for an opposing seat.
    """
    text = f"{seed}:{n}" if not shuffle_key else f"{seed}:{shuffle_key}:{n}"
    digest = hashlib.sha256(text.encode()).hexdigest()
    generator = random.Random(int(digest, 16))
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        j = int(generator.random() * (i + 1))
        result[i], result[j] = result[j], result[i]
    return result


# @spec GAME-010, GAME-083, GAME-085
def shuffle_library(game: Game, seat: SeatNumber) -> LibraryShuffled:
    """Shuffle one seat's library on its own stream, counting only that seat's shuffles."""
    shuffling = game.seat(seat)
    shuffling.library = shuffled(
        shuffling.library, game.seed, shuffling.shuffles, shuffling.shuffle_key
    )
    shuffling.shuffles += 1
    return LibraryShuffled()
