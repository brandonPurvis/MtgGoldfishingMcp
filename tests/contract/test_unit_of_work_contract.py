"""What every UnitOfWork promises, run against each adapter that implements it."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from mtg_goldfishing.application.ports import GameRecords, StoredGame
from tests.support.builders import a_game
from tests.support.stored import a_call, a_log_entry, a_rich_deck, a_snapshot
from tests.support.stores import STORE_ADAPTER_IDS, STORE_ADAPTERS, OpenStores, Stores

GAME = "gtest000001"


# @spec APP-012, APP-013, STOR-001
@pytest.fixture(params=STORE_ADAPTERS, ids=STORE_ADAPTER_IDS)
def stores(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Stores]:
    open_stores: OpenStores = request.param
    with open_stores(tmp_path) as opened:
        opened.games.add(a_game().build().game)
        yield opened


def _a_call_s_writes(stores: Stores) -> None:
    """Everything one changing call saves: the game, its log entry, a snapshot, its call record."""
    changed = a_game().with_life(31).build().game
    changed.change = 1
    stores.games.save(changed, version=1)
    stores.records.append_entry(GAME, a_log_entry(1))
    stores.records.add_snapshot(GAME, a_snapshot(3, written_by=1))
    stores.records.add_call(a_call(GAME, 1))
    stores.decks.add(a_rich_deck())


# @spec STOR-006
def test_committing_a_unit_of_work_keeps_the_game_it_saved(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.commit()

    changed = a_game().with_life(31).build().game
    changed.change = 1
    assert stores.games.get(GAME) == StoredGame(changed, 2)


# @spec STOR-006
def test_committing_a_unit_of_work_keeps_the_records_it_added(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.commit()

    assert stores.records.read(GAME) == GameRecords(
        (a_log_entry(1),), (a_snapshot(3, written_by=1),), (replace(a_call(GAME, 1), id=1),)
    )


# @spec STOR-006
def test_committing_a_unit_of_work_keeps_the_deck_it_added(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.commit()

    assert stores.decks.get("drich") == a_rich_deck()


# @spec STOR-006, STOR-007
def test_rolling_back_a_unit_of_work_leaves_the_game_as_before_it_began(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.rollback()

    assert stores.games.get(GAME) == StoredGame(a_game().build().game, 1)


# @spec STOR-006, STOR-007
def test_rolling_back_a_unit_of_work_leaves_no_records_it_added(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.rollback()

    assert stores.records.read(GAME) == GameRecords((), (), ())


# @spec STOR-007
def test_rolling_back_a_unit_of_work_leaves_no_deck_it_added(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.rollback()

    assert stores.decks.get("drich") is None


# @spec STOR-007
def test_rolling_back_keeps_what_was_saved_before_the_unit_of_work_began(stores: Stores) -> None:
    stores.records.add_call(a_call(GAME, None, tool="get_state"))
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.rollback()

    assert stores.records.read(GAME).calls == (replace(a_call(GAME, None, tool="get_state"), id=1),)


def test_a_unit_of_work_reads_its_own_writes_before_it_commits(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)

    seen = stores.games.get(GAME)
    stores.unit_of_work.commit()

    assert (seen and seen.version) == 2


def test_a_save_after_a_rolled_back_unit_of_work_starts_from_the_version_before_it(
    stores: Stores,
) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.rollback()

    assert stores.games.save(a_game().build().game, version=1) is True


def test_a_call_record_written_in_its_own_unit_after_a_rollback_is_kept(stores: Stores) -> None:
    stores.unit_of_work.begin()
    _a_call_s_writes(stores)
    stores.unit_of_work.rollback()
    stores.unit_of_work.begin()
    stores.records.add_call(a_call(GAME, 0, tool="play"))
    stores.unit_of_work.commit()

    assert [call.tool for call in stores.records.read(GAME).calls] == ["play"]
