"""Seeded shuffling: the nth shuffle of a game depends only on the seed, n and the library."""

from __future__ import annotations

import hashlib
import random

from mtg_goldfishing.domain.events import LibraryShuffled
from mtg_goldfishing.domain.game.model import Game


def shuffled(items: list[str], seed: int, n: int) -> list[str]:
    """A Fisher–Yates shuffle drawing only on the generator's basic uniform float."""
    digest = hashlib.sha256(f"{seed}:{n}".encode()).hexdigest()
    generator = random.Random(int(digest, 16))
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        j = int(generator.random() * (i + 1))
        result[i], result[j] = result[j], result[i]
    return result


# @spec GAME-010
def shuffle_library(game: Game) -> LibraryShuffled:
    game.library = shuffled(game.library, game.seed, game.shuffles)
    game.shuffles += 1
    return LibraryShuffled()
