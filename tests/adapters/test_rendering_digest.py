"""The text of coordination between seats: the digest lines a contested response begins with,
what `wait` answers, and the notices and errors that come with them."""

from __future__ import annotations

import json
from typing import Any

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application import outcome as outcomes
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain import events
from mtg_goldfishing.domain.events import (
    Asked,
    AskedKind,
    CardsDrawn,
    ChoiceRevealedTo,
    EffectRecorded,
    Error,
    ErrorKind,
    HiddenCardsDrawn,
    LifeChanged,
    LogExported,
    NoticeKind,
    Refused,
    StateListed,
)
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.summary import summarize
from tests.support.builders import a_game

RENDERER = TextRenderer()
S1, S2, S3 = SeatNumber(1), SeatNumber(2), SeatNumber(3)


def contested_summary(seat: SeatNumber = S3, **options: Any) -> Any:
    builder: Any = a_game().and_an_opposing_seat().and_an_opposing_seat()
    situation = builder.build()
    return summarize(situation.game, situation.deck, seat)


def element(seat: SeatNumber, change: int, *happened: object) -> Any:
    made: Any = outcomes.DigestElement  # type: ignore[attr-defined]
    return made(seat, change, tuple(happened))


def response(*digest: Any, seat: SeatNumber = S3, summary: object = None) -> list[str]:
    made: Any = Outcome
    outcome = made(
        Status.OK,
        summary or StateListed("summary"),
        (),
        contested_summary(seat),
        seat=seat,
        digest=tuple(digest),
    )
    return RENDERER.render("get_state", outcome).response.splitlines()


def event(name: str, *fields: object) -> Any:
    kind: Any = getattr(events, name)
    return kind(*fields)


# ------------------------------------------------------------------ digest lines


# @spec TOOL-035
def test_a_contested_response_begins_with_a_digest_line_per_change_oldest_first() -> None:
    lines = response(
        element(S1, 4, EffectRecorded("Phyrexian Arena")),
        element(S2, 5, LifeChanged(1, 41, S2)),
    )
    assert [line.split(":")[0] for line in lines[:2]] == ["S1 #4", "S2 #5"]
    assert lines[2].startswith("OK ")


# @spec TOOL-036
def test_everything_one_change_caused_is_on_its_one_line_separated_by_semicolons() -> None:
    lines = response(element(S1, 4, EffectRecorded("Phyrexian Arena"), LifeChanged(1, 41, S1)))
    digest = [line for line in lines if line.startswith("S1 #4: ")]
    assert len(digest) == 1
    assert digest[0].count("; ") == 1
    assert "Phyrexian Arena" in digest[0]


# @spec TOOL-057
def test_a_digest_line_names_the_reading_seat_by_its_number_and_never_as_you() -> None:
    lines = response(element(S2, 6, CardsDrawn(("Forest",), S3)), seat=S3)
    assert "S3 drew Forest" in lines[0]
    assert "you" not in lines[0].casefold().split()


# @spec TOOL-037
def test_a_digest_line_shows_another_seat_s_draw_as_a_count_and_names_no_card() -> None:
    lines = response(element(S2, 6, HiddenCardsDrawn(S2, 2)))
    assert "S2 drew 2 cards" in lines[0]


# @spec TOOL-064
def test_a_digest_line_shows_a_mulligan_taken_and_a_hand_kept_by_their_counts() -> None:
    lines = response(
        element(S2, 2, event("HiddenMulliganTaken", S2, 2)),
        element(S2, 3, event("HiddenHandKept", S2, 6, 1)),
    )
    assert lines[0] == "S2 #2: S2 took a mulligan (2 taken)"
    assert lines[1] == "S2 #3: S2 kept 6, bottomed 1"


# @spec TOOL-065
def test_a_digest_line_shows_a_look_at_a_hand_by_who_looks_and_whose_hand() -> None:
    lines = response(element(S3, 7, ChoiceRevealedTo("hand", S3, S1)))
    assert lines[0] == "S3 #7: S3 looks at S1's hand (CHOICE hand)"


# @spec TOOL-038
def test_a_contested_response_with_an_empty_digest_has_no_digest_lines() -> None:
    assert response()[0].startswith("OK ")


# @spec TOOL-056
def test_a_get_log_response_is_json_alone() -> None:
    outcome = Outcome(
        Status.OK, LogExported(0, 0, 0), (), contested_summary(), {"entries": []}, seat=S3
    )
    assert json.loads(RENDERER.render("get_log", outcome).response) == {"entries": []}


# @spec TOOL-039
def test_a_goldfish_response_has_no_digest_line_no_stack_and_no_act() -> None:
    situation = a_game().build()
    summary = summarize(situation.game, situation.deck, S1)
    lines = TextRenderer().render(
        "get_state", Outcome(Status.OK, StateListed("summary"), (), summary)
    )
    assert lines.response.splitlines()[0].startswith("OK ")
    assert "Stack" not in lines.response
    assert " Act " not in lines.response


# ------------------------------------------------------------------ what wait answers


# @spec TOOL-063, APP-066
def test_a_wait_that_timed_out_says_who_is_still_asked_and_what() -> None:
    timed_out = event("StillWaiting", Asked((S1,), AskedKind.TURN))
    lines = response(summary=timed_out, seat=S2)
    assert lines[0] == "OK Still waiting: S1 is asked to take its turn."


# @spec TOOL-063, APP-066
def test_a_wait_that_timed_out_during_mulligans_names_every_seat_still_to_keep() -> None:
    timed_out = event("StillWaiting", Asked((S1, S3), AskedKind.KEEP))
    lines = response(summary=timed_out, seat=S2)
    assert lines[0] == "OK Still waiting: S1 and S3 are asked to keep or mulligan."


# @spec APP-063
def test_a_wait_answered_to_the_seat_to_act_says_once_what_it_is_asked() -> None:
    builder: Any = a_game().and_an_opposing_seat()
    situation = builder.build()
    summary = summarize(situation.game, situation.deck, S1)
    asked = event("SeatToAct", Asked((S1,), AskedKind.TURN))
    text = RENDERER.render("wait", Outcome(Status.OK, asked, (), summary, seat=S1)).response
    assert text.splitlines()[0] == "OK You are asked to take your turn."
    assert text.count("asked to take your turn") == 1


# @spec APP-074
def test_a_goldfish_wait_says_what_the_only_seat_is_asked() -> None:
    situation = a_game().in_mulligan().build()
    summary = summarize(situation.game, situation.deck, S1)
    asked = event("SeatToAct", Asked((S1,), AskedKind.KEEP))
    text = RENDERER.render("wait", Outcome(Status.OK, asked, (), summary)).response
    assert text.splitlines()[0] == "OK You are asked to keep or mulligan."


# @spec APP-089
def test_a_wait_answered_to_an_eliminated_seat_says_it_is_out() -> None:
    lines = response(summary=event("SeatOut", S2), seat=S2)
    assert lines[0] == "OK S2 is out of the game; nothing more is asked of it."


# @spec APP-088
def test_a_wait_answered_on_an_ended_game_says_the_game_has_ended() -> None:
    lines = response(summary=event("GameHasEnded"), seat=S2)
    assert lines[0] == "OK The game has ended."


# @spec APP-073, APP-078
def test_a_timeout_out_of_range_is_an_error_giving_the_range() -> None:
    error: Any = Error(getattr(ErrorKind, "BAD_TIMEOUT"))  # noqa: B009
    outcome = Outcome(Status.ERROR, Refused((error,), ()), (), contested_summary(S2), seat=S2)
    text = RENDERER.render("wait", outcome).response
    assert text.splitlines()[0] == "ERROR timeout must be a number of seconds from 1 to 60."


# ------------------------------------------------------------------ notices


# @spec GAME-145, GAME-043
def test_each_seat_s_empty_library_notice_names_that_seat() -> None:
    builder: Any = a_game().and_an_opposing_seat()
    situation = builder.build()
    situation.game.seat(S2).notices.append(NoticeKind.EMPTY_LIBRARY)  # type: ignore[attr-defined]
    summary = summarize(situation.game, situation.deck, S1)
    text = RENDERER.render("get_state", Outcome(Status.OK, StateListed("summary"), (), summary))
    assert "Notice: S2's library ran out: a draw found too few cards" in text.response
