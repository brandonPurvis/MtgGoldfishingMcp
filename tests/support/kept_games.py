"""The end-of-test check on the games the in-memory game repository keeps.

No caller may change a game the repository returned or was handed to add or save. The
repository raises when asked for such a game, but a raise inside a call is answered as an
internal failure, and a game changed by a read-only call may never be asked for again. So
every in-memory game repository the test composition root builds is watched, and when an
application test or an in-process feature scenario ends, every game each one keeps is
compared with its private copy; any difference fails the test.
"""

from __future__ import annotations

from mtg_goldfishing.adapters.memory import InMemoryGameRepository

_watched: list[InMemoryGameRepository] = []


def watched(games: InMemoryGameRepository) -> InMemoryGameRepository:
    """Watch a repository built for the running test, until that test ends."""
    _watched.append(games)
    return games


# @spec APP-102
def check_kept_games() -> None:
    """Stop watching the repositories built so far, and fail if any game one keeps was
    changed after it was kept."""
    games = list(_watched)
    _watched.clear()
    changed = [game_id for repository in games for game_id in repository.changed_games()]
    assert not changed, (
        "a game the in-memory game repository keeps was changed after it was kept, which no "
        f"caller may do: {', '.join(changed)}"
    )


def stop_watching() -> None:
    """Stop watching the repositories built so far, without checking them."""
    _watched.clear()
