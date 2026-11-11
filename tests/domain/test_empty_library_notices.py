"""The empty library notice of a contested game: one for each seat, naming it, raised the
first time that seat draws with too few cards."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.play.playing import effect
from tests.support.acting import S1, S2, S3, acted
from tests.support.builders import Situation, a_game


def three_seats_with_empty_libraries() -> Situation:
    builder: Any = a_game().and_an_opposing_seat().and_an_opposing_seat()
    return builder.build()


def drew(situation: Situation, seat: SeatNumber) -> list[Any]:
    result = acted(
        situation, effect(situation.game, situation.deck, seat, source="x", delta={"draw": 1})
    )
    return [e for e in (result.summary, *result.events) if type(e).__name__ == "NoticeRaised"]


# @spec GAME-145
def test_a_seat_drawing_from_an_empty_library_raises_its_own_notice_naming_it() -> None:
    situation = three_seats_with_empty_libraries()
    (notice,) = drew(situation, S2)
    assert (notice.notice.value, notice.seat) == ("empty_library", S2)


# @spec GAME-145
def test_a_second_seat_s_empty_library_raises_its_own_notice_beside_the_first() -> None:
    situation = three_seats_with_empty_libraries()
    drew(situation, S2)
    (notice,) = drew(situation, S1)
    assert notice.seat == S1


# @spec GAME-165
def test_a_seat_s_empty_library_notice_is_raised_once_however_often_it_draws_short() -> None:
    situation = three_seats_with_empty_libraries()
    drew(situation, S2)
    assert drew(situation, S2) == []


# @spec GAME-145, GAME-043
def test_every_seat_is_shown_each_seat_s_empty_library_notice() -> None:
    situation = three_seats_with_empty_libraries()
    drew(situation, S2)
    drew(situation, S1)
    summary: Any = summarize(situation.game, situation.deck, S3)
    assert [(kind.value, seat) for kind, seat in summary.seat_notices] == [
        ("empty_library", S1),
        ("empty_library", S2),
    ]
