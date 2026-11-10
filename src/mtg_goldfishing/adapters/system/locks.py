"""Game locks within one process: a lock per game id, made when first wanted."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field

from mtg_goldfishing.application.ports import GameLocks


@dataclass
class _GameLock:
    lock: threading.Lock = field(default_factory=threading.Lock)
    wanted_by: int = 0


# @spec APP-014, APP-015, APP-016
class InProcessGameLocks(GameLocks):
    """One lock per game id. Calls for different games never wait on each other.

    A game's lock exists while some call holds or waits for it, and is dropped after, so
    the number of locks kept follows the number of games in play, not the number ever played.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, _GameLock] = {}

    def hold(self, game_id: str) -> AbstractContextManager[None]:
        return self._held(game_id)

    @contextmanager
    def _held(self, game_id: str) -> Iterator[None]:
        with self._guard:
            game_lock = self._locks.setdefault(game_id, _GameLock())
            game_lock.wanted_by += 1
        try:
            with game_lock.lock:
                yield
        finally:
            with self._guard:
                game_lock.wanted_by -= 1
                if game_lock.wanted_by == 0:
                    del self._locks[game_id]
