"""An application test that breaks the rule on purpose: it changes a game the in-memory game
repository keeps. It is not collected with the suite (its file name does not start with
`test_`); `test_kept_games_checked.py` runs it on its own and expects it to fail when it
ends."""

from __future__ import annotations

from tests.support.builders import a_game
from tests.support.service import a_service


def test_changing_a_game_the_repository_keeps() -> None:
    harness = a_service()
    harness.holding(a_game().build())

    harness.game().tested.life = 1
