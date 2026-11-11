"""Game change announcements within one process: the latest change of each game, and one
condition that waiting calls sleep on."""

from __future__ import annotations

import threading

from mtg_goldfishing.application.ports import GameChanges


# @spec APP-041, APP-048
class InProcessGameChanges(GameChanges):
    """The latest change announced for each game, and a condition waiting calls sleep on.

    A wait for a change after a number already passed returns at once, so a change announced
    between a waiting seat's look at the game and the start of its wait is never missed.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest: dict[str, int] = {}

    def announce(self, game_id: str, change: int) -> None:
        with self._condition:
            self._latest[game_id] = max(change, self._latest.get(game_id, change))
            self._condition.notify_all()

    def wait_for_change(self, game_id: str, after: int, timeout: float) -> bool:
        def changed() -> bool:
            latest = self._latest.get(game_id)
            return latest is not None and latest > after

        with self._condition:
            return self._condition.wait_for(changed, timeout=timeout)
