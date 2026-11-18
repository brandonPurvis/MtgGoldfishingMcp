"""How station cards read in responses: the charge counters that make one a creature in the
`get_state` listing, and the station cards a `load_deck` report names."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.listing_lines import state_lines
from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.domain.events import DeckLoaded, DeckReport
from mtg_goldfishing.domain.game.listing import list_state
from mtg_goldfishing.domain.reading.model import StationReading, StationReport
from tests.support.acting import S1
from tests.support.builders import a_game

RENDERER = TextRenderer()
ATRAXA = "Atraxa, Praetors' Voice"


def listed(charge: int) -> list[str]:
    situation = a_game().with_battlefield("Synthesizer Labship", counters={"charge": charge})
    built = situation.build()
    listing: Any = list_state(built.game, built.deck, S1)
    return state_lines(listing)


# @spec TOOL-112
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_that_is_a_creature_is_listed_with_its_power_and_toughness() -> None:
    assert any(
        "Synthesizer Labship: counters 9 charge; creature 4/4 (9+ charge counters)" in line
        for line in listed(9)
    )


# @spec TOOL-112
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_a_station_card_short_of_its_charge_counters_is_listed_with_what_it_needs() -> None:
    assert any(
        "Synthesizer Labship: counters 4 charge; creature at 9 charge counters" in line
        for line in listed(4)
    )


# @spec TOOL-113
@pytest.mark.xfail(strict=True, reason="station cards are not read yet (issue 62)")
def test_load_deck_lists_station_cards_with_the_charge_counters_each_needs() -> None:
    stations = (
        StationReport("Synthesizer Labship", StationReading(9)),
        StationReport(
            "U.S.S. Defiant, Mirror Migrant",
            StationReading(8, ("assumes it is a creature at its highest station symbol",)),
        ),
    )
    outcome = Outcome(
        Status.OK, DeckLoaded("d3f9a01c2e", 100, (ATRAXA,), report=DeckReport(stations=stations))
    )
    lines = RENDERER.render("load_deck", outcome).response.splitlines()
    assert (
        "Creatures by station: Synthesizer Labship (9 charge counters),"
        " U.S.S. Defiant, Mirror Migrant"
        " (8 charge counters; assumes it is a creature at its highest station symbol)"
    ) in lines
