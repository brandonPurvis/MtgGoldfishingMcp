"""Seeded shuffling: a seat's nth shuffle depends only on the seed, its shuffle key, n and
its library; the turn order depends only on the seed and the seats asked for."""

from __future__ import annotations

import hashlib
import random

from mtg_goldfishing.domain.events import LibraryShuffled
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.seats import SeatNumber


def _drawn[T](items: list[T], text: str) -> list[T]:
    """A Fisher–Yates walk driven only by the basic uniform float of a generator seeded with
    the integer value of the SHA-256 hash of `text`: i from the last index down to 1, swapping
    index i with index ⌊random()·(i+1)⌋."""
    digest = hashlib.sha256(text.encode()).hexdigest()
    generator = random.Random(int(digest, 16))
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        j = int(generator.random() * (i + 1))
        result[i], result[j] = result[j], result[i]
    return result


def shuffled(items: list[str], seed: int, n: int, shuffle_key: str = "") -> list[str]:
    """A library shuffle, seeded from `<seed>:<n>` for the tested seat, whose shuffle key is
    empty, and from `<seed>:<shuffle_key>:<n>` for an opposing seat."""
    return _drawn(items, f"{seed}:{n}" if not shuffle_key else f"{seed}:{shuffle_key}:{n}")


# @spec GAME-080, GAME-081
def turn_order[T](tested: T, opposing: list[T], seed: int, position: int | None) -> list[T]:
    """The seats in turn order, drawn from `<seed>:order`: the tested seat and then the
    opposing seats in the order asked for are shuffled together, or, when `position` is
    given, the opposing seats alone are, and the tested seat takes that place, from 1."""
    text = f"{seed}:order"
    if position is None:
        return _drawn([tested, *opposing], text)
    others = _drawn(opposing, text)
    return [*others[: position - 1], tested, *others[position - 1 :]]


# @spec GAME-010, GAME-083, GAME-085
def shuffle_library(game: Game, seat: SeatNumber) -> LibraryShuffled:
    """Shuffle one seat's library on its own stream, counting only that seat's shuffles."""
    shuffling = game.seat(seat)
    shuffling.library = shuffled(
        shuffling.library, game.seed, shuffling.shuffles, shuffling.shuffle_key
    )
    shuffling.shuffles += 1
    return LibraryShuffled()
