"""Hooks every test run shares."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from tests.support.kept_games import check_kept_games, stop_watching


# @spec APP-102
@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    """Fail a test that changed a game an in-memory game repository built for it keeps."""
    try:
        result = yield
    except BaseException:
        stop_watching()
        raise
    check_kept_games()
    return result
