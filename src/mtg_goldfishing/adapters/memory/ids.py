"""An id source for tests: game ids and seeds from fixed sequences."""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Iterator

GAME_ID_PATTERN = re.compile(r"^[a-z0-9]{10}$")
"""Ten lower-case letters or digits: what `IdSource.new_game_id` gives."""


def _counting_game_ids() -> Iterator[str]:
    for number in itertools.count(1):
        yield f"{number:010d}"


# @spec APP-013
class FixedIdSource:
    """Yields the game ids and seeds it was given, in order.

    Without game ids it counts `0000000001`, `0000000002`, ...; without seeds, 1, 2, ....
    Asking past the end of a given sequence is a defect in the test and raises.
    """

    def __init__(
        self, *, game_ids: Iterable[str] | None = None, seeds: Iterable[int] | None = None
    ) -> None:
        if game_ids is None:
            self._game_ids: Iterator[str] = _counting_game_ids()
        else:
            given = tuple(game_ids)
            for game_id in given:
                if not GAME_ID_PATTERN.match(game_id):
                    raise ValueError(f"{game_id!r} is not a game id of ten letters or digits")
            self._game_ids = iter(given)
        if seeds is None:
            self._seeds: Iterator[int] = itertools.count(1)
        else:
            given_seeds = tuple(seeds)
            if any(seed <= 0 for seed in given_seeds):
                raise ValueError("seeds must be positive")
            self._seeds = iter(given_seeds)

    def new_game_id(self) -> str:
        return next(self._game_ids)

    def new_seed(self) -> int:
        return next(self._seeds)
