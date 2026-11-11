"""The text of cast triggers and answer text: a goldfish game's `Cast trigger:` lines and where
they go among the event lines, the refusals of a land with cast triggers, a goldfish cast trigger
that would reveal cards and answer text that is too long, and an `ask` answer read with its
answer text by the answering seat and in every other seat's digest."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer, digest_line
from mtg_goldfishing.application.outcome import DigestElement, Outcome, Status
from mtg_goldfishing.domain.events import Refused
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by, public_form
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from tests.support.acting import S1, S2, S3, a_trigger, acted, playing
from tests.support.builders import Situation, a_game

RENDERER = TextRenderer()
STORM = "Thousand-Year Storm"
PYROMANCER = "Young Pyromancer"


def lines(tool: str, situation: Situation, seat: SeatNumber, result: Any) -> list[str]:
    """The text answering `seat`'s call, its events as that seat may see them."""
    if isinstance(result, Refusal):
        outcome = Outcome(
            Status.ERROR,
            Refused(result.errors, result.checks),
            (),
            summarize(situation.game, situation.deck, seat),
        )
        return RENDERER.render(tool, outcome).response.splitlines()
    assert isinstance(result, Applied), result
    (summary, *events) = as_seen_by((result.summary, *result.events), seat)
    outcome = Outcome(
        Status.OK, summary, tuple(events), summarize(result.game, situation.deck, seat)
    )
    return RENDERER.render(tool, outcome).response.splitlines()


def a_goldfish_table() -> Situation:
    return (
        a_game()
        .with_hand("Lightning Bolt", "Forest")
        .with_battlefield("Mountain")
        .with_library("Island", "Swamp")
        .build()
    )


def a_storm_bolt(situation: Situation) -> Any:
    triggers = [
        a_trigger(STORM, {"draw": 1}),
        a_trigger(
            PYROMANCER,
            {"tokens": [{"name": "Elemental", "types": "Creature — Elemental", "pt": "1/1"}]},
        ),
    ]
    return playing(situation, S1, "Lightning Bolt", delta={"damage": 3}, cast_triggers=triggers)


# ------------------------------------------------------------------ goldfish cast triggers


# @spec TOOL-086
def test_a_goldfish_play_shows_one_line_per_cast_trigger_in_the_order_listed() -> None:
    situation = a_goldfish_table()
    shown = lines("play", situation, S1, a_storm_bolt(situation))
    assert [line for line in shown if line.startswith("Cast trigger:")] == [
        "Cast trigger: Thousand-Year Storm.",
        "Cast trigger: Young Pyromancer.",
    ]


# @spec TOOL-016
def test_cast_trigger_lines_come_after_the_payment_and_before_the_moves() -> None:
    situation = a_goldfish_table()
    shown = lines("play", situation, S1, a_storm_bolt(situation))
    assert [line.split(" ")[0] for line in shown[1:5]] == ["Paid", "Cast", "Cast", "Drew"]


# ------------------------------------------------------------------ refusals


# @spec PLAY-132
def test_a_land_with_cast_triggers_is_refused_saying_a_land_is_not_cast() -> None:
    situation = a_goldfish_table()
    result = playing(situation, S1, "Forest", cast_triggers=[a_trigger(STORM, {"draw": 1})])
    headline = lines("play", situation, S1, result)[0]
    assert headline.startswith("ERROR ")
    for words in ("land is not cast", "with effect"):
        assert words in headline, words


# @spec PLAY-137
def test_a_goldfish_cast_trigger_that_reveals_is_refused_saying_to_record_it_with_effect() -> None:
    situation = a_goldfish_table()
    trigger = a_trigger("Ponder", {"look": {"n": 3, "rest": "library_top"}})
    result = playing(situation, S1, "Lightning Bolt", cast_triggers=[trigger])
    headline = lines("play", situation, S1, result)[0]
    assert headline.startswith("ERROR ")
    for words in ("look or search", "with effect after the play"):
        assert words in headline, words


# @spec PLAY-140
def test_answer_text_that_is_too_long_is_refused_saying_how_long_it_may_be() -> None:
    situation = a_contested_table()
    asked(situation)
    result = answering(situation, "x" * 250)
    headline = lines("choose", situation, S2, result)[0]
    assert headline.startswith("ERROR ")
    for words in ("250 characters", "200"):
        assert words in headline, words


# ------------------------------------------------------------------ answer text


def a_contested_table() -> Situation:
    builder: Any = a_game().with_library("Forest")
    builder = builder.and_an_opposing_seat().with_hand("Island")
    return builder.and_an_opposing_seat().build()


def asked(situation: Situation) -> None:
    delta = {"ask": [{"seats": [2], "text": "name a card"}]}
    acted(
        situation,
        effect(
            situation.game, situation.deck, S1, source="Meddling Mage", delta=delta, immediate=True
        ),
    )


def answering(situation: Situation, text: object) -> Any:
    operate: Any = choose
    choice = situation.game.pending[0].choice_id
    return operate(situation.game, situation.deck, S2, choice_id=choice, text=text)


# @spec TOOL-087
def test_the_answering_seat_reads_its_answer_with_its_answer_text_in_quotes() -> None:
    situation = a_contested_table()
    asked(situation)
    choice = situation.game.pending[0].choice_id
    result = answering(situation, "Lightning Bolt")
    assert lines("choose", situation, S2, result)[0] == (
        f'OK S2 answered choice {choice} (ask): "Lightning Bolt".'
    )


# @spec TOOL-087, GAME-179
def test_another_seat_s_digest_reads_the_answer_with_its_answer_text_in_quotes() -> None:
    situation = a_contested_table()
    asked(situation)
    choice = situation.game.pending[0].choice_id
    result = answering(situation, "Lightning Bolt")
    line = digest_line(DigestElement(S2, 3, public_form((result.summary, *result.events))))
    assert line == f'S2 #3: S2 answered choice {choice} (ask): "Lightning Bolt"'


# @spec TOOL-087
def test_answer_text_is_written_verbatim_with_quotes_and_backslashes_unescaped() -> None:
    situation = a_contested_table()
    asked(situation)
    result = answering(situation, 'the "Bolt" \\ 7.')
    seen = public_form((result.summary, *result.events))
    line = digest_line(DigestElement(S2, 3, seen))
    assert line.endswith('(ask): "the "Bolt" \\ 7."')


# @spec TOOL-087
def test_an_answer_without_answer_text_reads_as_before() -> None:
    situation = a_contested_table()
    asked(situation)
    choice = situation.game.pending[0].choice_id
    result = answering(situation, "   ")
    assert lines("choose", situation, S2, result)[0] == f"OK S2 answered choice {choice} (ask)."


# @spec TOOL-087
def test_the_answer_text_is_shown_to_a_seat_that_neither_asked_nor_answered() -> None:
    situation = a_contested_table()
    asked(situation)
    result = answering(situation, "Lightning Bolt")
    seen = as_seen_by((result.summary, *result.events), S3)
    assert '(ask): "Lightning Bolt"' in digest_line(DigestElement(S2, 3, seen))
