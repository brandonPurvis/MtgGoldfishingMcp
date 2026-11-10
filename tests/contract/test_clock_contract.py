"""What every Clock promises. Add another adapter's clock as one more fixture param."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from mtg_goldfishing.adapters.memory import FixedClock
from mtg_goldfishing.adapters.system import SystemClock
from mtg_goldfishing.application.ports import Clock


# @spec APP-012, APP-013
@pytest.fixture(params=[FixedClock, SystemClock], ids=["fixed", "system"])
def clock(request: pytest.FixtureRequest) -> Clock:
    new_clock: Callable[[], Clock] = request.param
    return new_clock()


def test_the_time_is_given_in_utc(clock: Clock) -> None:
    assert clock.now().utcoffset() == timedelta(0)


def test_the_time_never_goes_backwards(clock: Clock) -> None:
    first = clock.now()
    assert clock.now() >= first


# @spec APP-013
def test_a_fixed_clock_tells_the_time_it_was_set_to() -> None:
    clock = FixedClock()
    clock.set(datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC))
    assert clock.now() == datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


def test_a_fixed_clock_refuses_a_time_without_a_time_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        FixedClock(datetime(2026, 5, 6))


def test_the_system_clock_tells_the_current_time() -> None:
    before = datetime.now(UTC)
    told = SystemClock().now()
    assert before <= told <= datetime.now(UTC)
