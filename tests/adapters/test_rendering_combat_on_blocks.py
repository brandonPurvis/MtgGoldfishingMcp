"""The text a seat reads about combat on blocks in a contested game: the attackers a `blocks`
choice may block, with the evasion the service holds for each; a block refused for an
attacker's evasion; evasion stated on an attack; a trample statement; and the cards that grant
evasion or reach in the `load_deck` report."""

from __future__ import annotations

from typing import Any

from mtg_goldfishing.adapters.mcp.listing_lines import state_lines
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.events import DeckLoaded, DeckReport, Refused
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.reading.model import KeywordGrant, KeywordReading, KeywordReport
from tests.support.acting import S1, S2, acted
from tests.support.builders import Situation
from tests.support.combat import (
    a_duel,
    advanced,
    at_blocks,
    attacked,
    attacking,
    blocked,
    blocking,
    card_of,
    stating_trample,
)

RENDERER = TextRenderer()
ATRAXA = "Atraxa, Praetors' Voice"


def response(tool: str, situation: Situation, seat: SeatNumber, result: Any) -> str:
    """The text answering `seat`'s call, its events as that seat may see them."""
    if isinstance(result, Refusal):
        outcome = Outcome(
            Status.ERROR,
            Refused(result.errors, result.checks),
            (),
            summarize(situation.game, situation.deck, seat),
        )
        return RENDERER.render(tool, outcome).response
    assert isinstance(result, Applied), result
    (summary, *events) = as_seen_by((result.summary, *result.events), seat)
    waiting = result.game.pending
    status = Status.CHOICE if waiting and waiting[0].seat == seat else Status.OK
    outcome = Outcome(status, summary, tuple(events), summarize(result.game, situation.deck, seat))
    return RENDERER.render(tool, outcome).response


def id_of(situation: Situation, name: str) -> str:
    return card_of(situation, name, S1).id


# ------------------------------------------------------------------ the blocks choice


# @spec TOOL-079
def test_the_choice_line_shows_each_attacker_by_instance_id_with_its_evasion() -> None:
    situation = attacked(
        a_duel(attackers=("Grizzly Bears", "Wind Drake")), attackers=["Grizzly Bears", "Wind Drake"]
    )
    result = advanced(situation, "declare_blockers")
    choice = situation.game.pending[0].choice_id
    bears, drake = id_of(situation, "Grizzly Bears"), id_of(situation, "Wind Drake")
    lines = response("advance", situation, S2, result).splitlines()
    assert (
        f"Choice {choice} (blocks) for S2: attacked by Grizzly Bears ({bears}),"
        f" Wind Drake ({drake}, flying)."
    ) in lines


# @spec TOOL-079
def test_evasions_are_shown_in_order_each_once_whether_read_listed_or_both() -> None:
    situation = attacked(
        a_duel(attackers=("Sky Rider",)),
        attackers=["Sky Rider"],
        evasion={"Sky Rider": ["unblockable", "flying"]},
    )
    result = advanced(situation, "declare_blockers")
    rider = id_of(situation, "Sky Rider")
    text = response("advance", situation, S2, result)
    assert f"attacked by Sky Rider ({rider}, flying, horsemanship, can't be blocked)." in text


# @spec TOOL-079
def test_the_listing_shows_a_blocks_choice_s_attackers_with_their_evasion() -> None:
    situation = at_blocks(a_duel(attackers=("Wind Drake",)), attackers=["Wind Drake"])
    choice = situation.game.pending[0].choice_id
    listing: Any = list_state(situation.game, situation.deck, S2)
    drake = id_of(situation, "Wind Drake")
    assert f"  {choice} (blocks): attacked by Wind Drake ({drake}, flying)" in state_lines(listing)


# ------------------------------------------------------------------ a refused block


# @spec CMBT-090
def test_a_block_refused_for_flying_names_the_blocker_the_attacker_and_where_flying_is_from() -> (
    None
):
    situation = at_blocks(a_duel(attackers=("Wind Drake",)), attackers=["Wind Drake"])
    result = blocking(situation, S2, {"Llanowar Elves": "Wind Drake"})
    text = response("choose", situation, S2, result)
    assert "Llanowar Elves cannot block Wind Drake, which has flying (read from its card)" in text


# @spec CMBT-090
def test_a_block_refused_for_evasion_stated_in_evasion_says_so() -> None:
    situation = at_blocks(
        a_duel(attackers=("Grizzly Bears",)),
        attackers=["Grizzly Bears"],
        evasion={"Grizzly Bears": "unblockable"},
    )
    result = blocking(situation, S2, {"Llanowar Elves": "Grizzly Bears"})
    text = response("choose", situation, S2, result)
    assert "Llanowar Elves cannot block Grizzly Bears, which can't be blocked (stated in" in text


# @spec CMBT-090
def test_a_block_refused_for_a_reading_under_a_condition_gives_the_assumption() -> None:
    situation = at_blocks(a_duel(attackers=("Island Skimmer",)), attackers=["Island Skimmer"])
    result = blocking(situation, S2, {"Llanowar Elves": "Island Skimmer"})
    text = response("choose", situation, S2, result)
    assert "assumes its condition is met" in text


# @spec CMBT-091
def test_an_overridden_evasion_check_is_named_in_the_response() -> None:
    situation = at_blocks(a_duel(attackers=("Wind Drake",)), attackers=["Wind Drake"])
    result = blocking(situation, S2, {"Llanowar Elves": "Wind Drake"}, override="it has reach")
    text = response("choose", situation, S2, acted(situation, result))
    assert "Llanowar Elves cannot block Wind Drake" in text


# ------------------------------------------------------------------ the attack


# @spec CMBT-080
def test_an_attack_says_the_evasion_stated_for_each_attacker() -> None:
    situation = a_duel(attackers=("Grizzly Bears",))
    result = attacking(situation, attackers=["Grizzly Bears"], evasion={"Grizzly Bears": "flying"})
    assert "Evasion stated: Grizzly Bears (flying)." in response("attack", situation, S1, result)


# @spec CMBT-101
def test_a_trample_statement_reads_with_each_attacker_s_trample_damage_and_seat() -> None:
    situation = at_blocks(a_duel(attackers=("Shivan Dragon",)), attackers=["Shivan Dragon"])
    blocked(situation, S2, {"Llanowar Elves": "Shivan Dragon"})
    result = stating_trample(situation, {"Shivan Dragon": 3})
    first = response("attack", situation, S2, result).splitlines()[0]
    assert first == "OK Trample damage: Shivan Dragon 3 to S2."


# ------------------------------------------------------------------ load_deck


# @spec DECK-041
def test_load_deck_lists_the_cards_that_grant_evasion_or_reach() -> None:
    granting = (KeywordReport("Levitation", "flying", KeywordReading(grant=KeywordGrant())),)
    build: Any = DeckReport
    report = build(granting_evasion_or_reach=granting)
    outcome = Outcome(Status.OK, DeckLoaded("d3f9a01c2e", 100, (ATRAXA,), report=report))
    lines = RENDERER.render("load_deck", outcome).response.splitlines()
    assert "Grants evasion or reach: Levitation (flying)" in lines
