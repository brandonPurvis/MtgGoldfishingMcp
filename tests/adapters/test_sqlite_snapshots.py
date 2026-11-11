"""Turn snapshots on SQLite: kept by game and table turn, never replaced."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.sqlite import SqliteStores
from tests.support.stored import a_contested_snapshot, a_snapshot

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M3c: not built")
GAME = "gtest000001"


# @spec STOR-028
@NOT_BUILT
def test_a_snapshot_row_is_keyed_by_the_table_turn(tmp_path: Path) -> None:
    stores = SqliteStores.open(tmp_path / "games.sqlite3")
    try:
        stores.records.add_snapshot(GAME, a_contested_snapshot(3, table_turn=5, written_by=9))
        stores.records.add_snapshot(GAME, a_contested_snapshot(3, table_turn=6, written_by=11))
        rows = (
            stores.database.connection()
            .execute("SELECT turn FROM snapshots WHERE game_id = ? ORDER BY turn", (GAME,))
            .fetchall()
        )
    finally:
        stores.database.close()
    assert rows == [(5,), (6,)]


# @spec STOR-028
def test_a_goldfish_snapshot_row_is_keyed_by_its_turn(tmp_path: Path) -> None:
    stores = SqliteStores.open(tmp_path / "games.sqlite3")
    try:
        stores.records.add_snapshot(GAME, a_snapshot(4, written_by=9))
        rows = stores.database.connection().execute("SELECT turn FROM snapshots").fetchall()
    finally:
        stores.database.close()
    assert rows == [(4,)]


# @spec STOR-029
def test_a_second_snapshot_for_a_table_turn_raises_and_writes_nothing(tmp_path: Path) -> None:
    stores = SqliteStores.open(tmp_path / "games.sqlite3")
    try:
        stores.records.add_snapshot(GAME, a_snapshot(4, written_by=9))
        with pytest.raises(sqlite3.IntegrityError):
            stores.records.add_snapshot(GAME, a_snapshot(4, written_by=10))
        (snapshot,) = stores.records.read(GAME).snapshots
    finally:
        stores.database.close()
    assert snapshot.written_by == 9
