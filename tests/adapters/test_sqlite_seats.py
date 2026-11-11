"""Seats in the SQLite adapter: the `seats` table, and the migration of games stored before it.

The stored game comes from `fixtures/goldfish_game_schema_1.json`: the rows a schema-1 service
wrote while a goldfish game was played to a pending choice in turn 2, and what that service
then answered to the calls that followed.
"""

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.adapters.memory import FixedClock, FixedIdSource, InMemoryCardCatalog
from mtg_goldfishing.adapters.sqlite import MIGRATIONS, SqliteDatabase, SqliteStores
from mtg_goldfishing.adapters.system import InProcessGameLocks
from mtg_goldfishing.application.service import Service
from mtg_goldfishing.domain.game import seats
from tests.support.builders import a_game
from tests.support.card_data import recorded_cards
from tests.support.stored import a_call

# The seat model is reached untyped here, so the tests read the same before and after it exists.
SeatNumber: Any = seats.SeatNumber
SeatId: Any = seats.SeatId

GAME = "gtest000001"
STORED: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "goldfish_game_schema_1.json").read_text(encoding="utf-8")
)
STORED_GAME: str = STORED["game_id"]
STORED_STATE: dict[str, Any] = json.loads(STORED["tables"]["games"][0]["state"])
SEATS_SCHEMA = 2


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "goldfishing.db"


@pytest.fixture
def stores(path: Path) -> Iterator[SqliteStores]:
    opened = SqliteStores.open(path)
    yield opened
    opened.database.close()


@pytest.fixture
def from_before_seats(path: Path) -> Path:
    """A database at schema 1 holding the stored goldfish game, its deck and its records."""
    SqliteDatabase(path, migrations=MIGRATIONS[:1]).close()
    connection = sqlite3.connect(path)
    with connection:
        for table, rows in STORED["tables"].items():
            for row in rows:
                columns = ", ".join(row)
                marks = ", ".join("?" for _ in row)
                connection.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(row.values())
                )
    connection.close()
    return path


@pytest.fixture
def migrated(from_before_seats: Path) -> Iterator[SqliteStores]:
    """The stores a service finds when it starts against the schema-1 database."""
    opened = SqliteStores.open(from_before_seats)
    yield opened
    opened.database.close()


def _query(path: Path, sql: str, *parameters: object) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql, parameters).fetchall()
    finally:
        connection.close()


def _execute(path: Path, sql: str, *parameters: object) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(sql, parameters)
    finally:
        connection.close()


def _schema_version(path: Path) -> object:
    return _query(path, "SELECT version FROM schema_version")[0][0]


def _a_game_of_two_seats() -> Any:
    builder: Any = a_game().with_hand("Forest")
    return builder.and_an_opposing_seat().with_hand("Island").build().game


def _service(stores: SqliteStores) -> Service:
    """The service as the stored game was played: real response text, a set clock."""
    return Service(
        games=stores.games,
        decks=stores.decks,
        records=stores.records,
        unit_of_work=stores.unit_of_work,
        catalog=InMemoryCardCatalog(recorded_cards(), ()),
        locks=InProcessGameLocks(),
        ids=FixedIdSource(),
        clock=FixedClock(),
        renderer=TextRenderer(),
    )


SEAT_COLUMNS = "SELECT seat_id, game_id, seat_number, deck_id, tested FROM seats"


# ------------------------------------------------------------------ the seats table


# @spec STOR-016, STOR-017
def test_adding_a_goldfish_game_writes_one_seats_row_keyed_by_its_game_id(
    stores: SqliteStores, path: Path
) -> None:
    stores.games.add(a_game().build().game)

    assert _query(path, SEAT_COLUMNS) == [(GAME, GAME, 1, "dtest", 1)]


# @spec STOR-016
def test_adding_a_game_writes_a_seats_row_for_each_of_its_seats(
    stores: SqliteStores, path: Path
) -> None:
    game = _a_game_of_two_seats()
    opposing = game.seat(SeatNumber(2))
    stores.games.add(game)

    assert _query(path, SEAT_COLUMNS + " ORDER BY seat_number") == [
        (GAME, GAME, 1, "dtest", 1),
        (opposing.seat_id.value, GAME, 2, opposing.deck_id, 0),
    ]


# @spec STOR-016
def test_a_game_s_seats_rows_are_written_in_the_same_transaction_as_the_game(
    stores: SqliteStores, path: Path
) -> None:
    stores.unit_of_work.begin()
    stores.games.add(a_game().build().game)
    stores.unit_of_work.rollback()

    assert _query(path, "SELECT count(*) FROM seats") == [(0,)]


# @spec STOR-018
def test_a_seat_id_is_answered_from_the_seats_table_and_not_from_game_documents(
    stores: SqliteStores, path: Path
) -> None:
    stores.games.add(a_game().build().game)
    _execute(
        path,
        "INSERT INTO seats (seat_id, game_id, seat_number, deck_id, tested)"
        " VALUES ('gonlyinrow', ?, 3, 'dtest', 0)",
        GAME,
    )
    repository: Any = stores.games

    found = repository.find_seat(SeatId("gonlyinrow"))

    assert (found.game_id, found.seat) == (GAME, SeatNumber(3))


# @spec STOR-020
def test_saving_a_game_leaves_its_seats_rows_as_they_were_written(
    stores: SqliteStores, path: Path
) -> None:
    game = _a_game_of_two_seats()
    stores.games.add(game)
    written = _query(path, SEAT_COLUMNS + " ORDER BY seat_number")
    game.seat(SeatNumber(2)).deck_id = "dchanged"
    game.seat(SeatNumber(2)).eliminated = True
    stores.games.save(game, version=1)

    assert _query(path, SEAT_COLUMNS + " ORDER BY seat_number") == written


# @spec STOR-023
def test_calls_are_indexed_by_game_id_and_seat_number(stores: SqliteStores, path: Path) -> None:
    indexes = [str(name) for _, name, *_ in _query(path, "PRAGMA index_list('calls')")]

    indexed = [
        [column for _, _, column in _query(path, f"PRAGMA index_info('{name}')")]
        for name in indexes
    ]

    assert ["game_id", "seat"] in indexed


# ------------------------------------------------------------------ the migration that adds seats


# @spec STOR-024
def test_the_migration_gives_every_stored_game_a_seats_row_for_its_tested_seat(
    migrated: SqliteStores, path: Path
) -> None:
    deck_id = STORED["tables"]["games"][0]["deck_id"]

    assert _query(path, SEAT_COLUMNS) == [(STORED_GAME, STORED_GAME, 1, deck_id, 1)]


# @spec STOR-025
def test_the_migration_adds_a_seat_number_to_calls_left_null_on_stored_call_records(
    migrated: SqliteStores, path: Path
) -> None:
    stored_calls = len(STORED["tables"]["calls"])

    assert _query(path, "SELECT count(*), count(seat) FROM calls") == [(stored_calls, 0)]


# @spec STOR-026
def test_the_migration_moves_what_one_player_has_into_the_tested_seat(
    migrated: SqliteStores,
) -> None:
    stored = migrated.games.get(STORED_GAME)
    assert stored is not None
    game: Any = stored.game
    (seat,) = game.seats

    assert (seat.number, seat.seat_id, seat.tested, seat.deck_id) == (
        SeatNumber(1),
        SeatId(STORED_GAME),
        True,
        STORED_STATE["deck_id"],
    )
    assert (seat.life, seat.mulligans, seat.shuffles, seat.land_drops_used, seat.library) == (
        STORED_STATE["life"],
        STORED_STATE["mulligans"],
        STORED_STATE["shuffles"],
        STORED_STATE["land_drops_used"],
        STORED_STATE["library"],
    )
    assert (seat.commander_casts, seat.kept, seat.turns, seat.eliminated) == (
        STORED_STATE["commander_casts"],
        True,
        STORED_STATE["turn"],
        False,
    )


# @spec STOR-026
def test_the_migration_keeps_pooled_and_commander_damage_as_the_imaginary_opponents_tallies(
    migrated: SqliteStores,
) -> None:
    stored = migrated.games.get(STORED_GAME)
    assert stored is not None
    game: Any = stored.game

    assert (game.imaginary.damage_dealt, game.imaginary.commander_damage) == (
        STORED_STATE["damage_dealt"],
        STORED_STATE["commander_damage"],
    )


# @spec STOR-026
def test_the_migration_makes_the_tested_seat_owner_and_controller_of_every_card(
    migrated: SqliteStores,
) -> None:
    stored = migrated.games.get(STORED_GAME)
    assert stored is not None
    game: Any = stored.game

    assert len(game.cards) == len(STORED_STATE["cards"])
    assert {(card.owner, card.controller) for card in game.cards} == {
        (SeatNumber(1), SeatNumber(1))
    }


# @spec STOR-026
def test_the_migration_keeps_the_table_s_turn_step_pending_choice_and_most_recent_change(
    migrated: SqliteStores,
) -> None:
    stored = migrated.games.get(STORED_GAME)
    assert stored is not None
    game: Any = stored.game
    (pending,) = game.pending
    last = game.tested.last_change

    assert (game.active, game.turn, game.round, game.step.value, game.change) == (
        SeatNumber(1),
        STORED_STATE["turn"],
        STORED_STATE["turn"],
        STORED_STATE["step"],
        STORED_STATE["change"],
    )
    assert (pending.choice_id, pending.seat, pending.revealed) == (
        STORED_STATE["pending_choice"]["choice_id"],
        SeatNumber(1),
        STORED_STATE["pending_choice"]["revealed"],
    )
    assert (last.tool, last.change) == (STORED_STATE["last_change"]["tool"], game.change)


# @spec STOR-013, STOR-026
def test_the_migration_keeps_the_version_counter_and_the_records_of_a_stored_game(
    migrated: SqliteStores, path: Path
) -> None:
    stored = migrated.games.get(STORED_GAME)
    records = migrated.records.read(STORED_GAME)

    assert stored is not None
    assert (_schema_version(path), stored.version) == (
        SEATS_SCHEMA,
        STORED["tables"]["games"][0]["version"],
    )
    assert (len(records.entries), len(records.snapshots), len(records.calls)) == (
        len(STORED["tables"]["log_entries"]),
        len(STORED["tables"]["snapshots"]),
        len(STORED["tables"]["calls"]) - 1,  # the deck's own call names no game
    )


# @spec STOR-027
def test_a_goldfish_game_stored_before_seats_answers_every_later_call_as_it_did_before(
    migrated: SqliteStores, path: Path
) -> None:
    service = _service(migrated)

    answers = [
        {**call, "response": getattr(service, call["tool"])(call["arguments"]).response}
        for call in STORED["continuation"]
    ]

    assert answers == STORED["continuation"]
    assert _schema_version(path) == SEATS_SCHEMA


# @spec STOR-027
def test_a_goldfish_game_stored_before_seats_keeps_its_change_number_and_status_line(
    migrated: SqliteStores, path: Path
) -> None:
    first = STORED["continuation"][0]

    answer = _service(migrated).get_state(first["arguments"])

    assert _schema_version(path) == SEATS_SCHEMA
    assert answer.response.splitlines()[-1] == first["response"].splitlines()[-1]


# ------------------------------------------------------------------ the seat number of calls


# @spec STOR-021
@pytest.mark.xfail(strict=True, reason="M3a: call records naming seats are not built")
def test_a_call_record_s_seat_number_is_stored_in_the_seat_column(
    stores: SqliteStores, path: Path
) -> None:
    seated: Any = replace(a_call(GAME, 4), seat=SeatNumber(2))
    stores.records.add_call(seated)
    assert _query(path, "SELECT seat FROM calls") == [(2,)]


# @spec STOR-021
def test_a_call_record_that_names_no_seat_stores_a_null_seat(
    stores: SqliteStores, path: Path
) -> None:
    stores.records.add_call(a_call(GAME, 4))
    assert _query(path, "SELECT seat FROM calls") == [(None,)]
