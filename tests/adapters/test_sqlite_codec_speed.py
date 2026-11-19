"""The storage speed check: the codec timed against the standard library's JSON module.

Run on request with `pytest -m speed`: timings are too noisy to gate every commit. Each
side is run afresh many times and the medians are compared, so the ratio holds on any
machine that is not busy with something else.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable

import pytest

from mtg_goldfishing.adapters.sqlite.codec import decode, encode, to_data
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from tests.support.reference import a_reference_contested_game, a_reference_deck

pytestmark = pytest.mark.speed

RUNS = 25
READ_LIMIT = 5.0
WRITE_LIMIT = 4.0

REFERENCES: dict[str, tuple[Callable[[], object], object]] = {
    "reference deck": (a_reference_deck, LoadedDeck),
    "reference contested game": (a_reference_contested_game, Game),
}

not_yet_fast = pytest.mark.xfail(
    strict=True, reason="the codec still inspects type hints value by value"
)


def median_seconds(run: Callable[[], object]) -> float:
    run()
    times = []
    for _ in range(RUNS):
        started = time.perf_counter()
        run()
        times.append(time.perf_counter() - started)
    return statistics.median(times)


# @spec STOR-051
@not_yet_fast
@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_reading_a_stored_document_costs_at_most_five_json_parses(name: str) -> None:
    build, kind = REFERENCES[name]
    text = encode(build(), kind)

    codec = median_seconds(lambda: decode(text, kind))
    parser = median_seconds(lambda: json.loads(text))

    assert codec / parser <= READ_LIMIT


# @spec STOR-052
@not_yet_fast
@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_writing_a_stored_document_costs_at_most_four_json_writes(name: str) -> None:
    build, kind = REFERENCES[name]
    value = build()
    data = to_data(value, kind)

    codec = median_seconds(lambda: encode(value, kind))
    writer = median_seconds(lambda: json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    assert codec / writer <= WRITE_LIMIT
