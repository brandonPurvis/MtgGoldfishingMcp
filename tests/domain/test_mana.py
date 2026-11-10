"""Mana strings and the mana pool as value objects."""

import dataclasses

import pytest

from mtg_goldfishing.domain.mana import (
    Mana,
    ManaPool,
    ManaString,
    Restriction,
    SymbolKind,
)


# @spec PAY-001
@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        ("{W}", [SymbolKind.COLOR]),
        ("{C}", [SymbolKind.COLORLESS]),
        ("{3}", [SymbolKind.GENERIC]),
        ("{X}", [SymbolKind.X]),
        ("{S}", [SymbolKind.SNOW]),
        ("{W/U}", [SymbolKind.HYBRID]),
        ("{2/W}", [SymbolKind.GENERIC_HYBRID]),
        ("{W/P}", [SymbolKind.PHYREXIAN]),
        ("{2}{G}{G}", [SymbolKind.GENERIC, SymbolKind.COLOR, SymbolKind.COLOR]),
        ("", []),
    ],
)
def test_a_mana_string_is_a_sequence_of_known_symbols(text: str, kinds: list[SymbolKind]) -> None:
    assert [symbol.kind for symbol in ManaString.parse(text).symbols] == kinds


# @spec PAY-001
@pytest.mark.parametrize("text", ["G", "{Q}", "{2}{", "{W/Q}", "2G", "{-1}", "{G} {G}x"])
def test_text_that_is_not_a_mana_string_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="mana string"):
        ManaString.parse(text)


# @spec APP-005
def test_mana_strings_compare_by_value_and_cannot_be_changed() -> None:
    first, second = ManaString.parse("{1}{G}"), ManaString.parse("{1}{G}")
    assert first == second
    assert hash(first) == hash(second)
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.symbols = ()  # type: ignore[misc]


def test_a_mana_string_writes_itself_back_as_text() -> None:
    assert str(ManaString.parse("{2}{W/U}{G}")) == "{2}{W/U}{G}"


# @spec PLAY-016
def test_x_is_replaced_by_the_announced_value() -> None:
    assert ManaString.parse("{X}{X}{R}").with_x(3) == ManaString.parse("{3}{3}{R}")


# @spec PLAY-016
def test_costs_add_together() -> None:
    assert ManaString.parse("{1}{G}") + ManaString.parse("{2}") == ManaString.parse("{1}{G}{2}")


def test_a_mana_string_knows_whether_it_contains_x() -> None:
    assert ManaString.parse("{X}{R}").has_x
    assert not ManaString.parse("{2}{R}").has_x


def test_mana_produced_by_a_mana_string_is_one_unit_per_symbol_with_numbers_as_colorless() -> None:
    assert ManaString.parse("{W}{U}").produced() == ("W", "U")
    assert ManaString.parse("{C}{C}").produced() == ("C", "C")
    assert ManaString.parse("{2}").produced() == ("C", "C")


def test_a_mana_string_with_hybrid_symbols_cannot_be_produced() -> None:
    with pytest.raises(ValueError, match="produce"):
        ManaString.parse("{W/U}").produced()


# @spec PAY-009
def test_an_empty_pool_is_written_as_empty_braces() -> None:
    assert str(ManaPool()) == "{}"


# @spec PAY-009
def test_restricted_mana_in_the_pool_is_marked_with_a_star() -> None:
    creatures_only = Restriction("Spend this mana only to cast creature spells.", ("Creature",))
    pool = ManaPool((Mana("G"), Mana("G", creatures_only)))
    assert str(pool) == "{G}{G}*"


def test_adding_mana_to_a_pool_gives_a_new_pool() -> None:
    pool = ManaPool()
    bigger = pool.add(ManaString.parse("{R}{R}"))
    assert str(pool) == "{}"
    assert str(bigger) == "{R}{R}"


# @spec PLAY-072
def test_pools_can_be_compared_as_symbols_ignoring_order_and_restrictions() -> None:
    creatures_only = Restriction("creatures", ("Creature",))
    pool = ManaPool((Mana("G", creatures_only), Mana("R")))
    assert pool.same_symbols_as(ManaString.parse("{R}{G}"))
    assert not pool.same_symbols_as(ManaString.parse("{R}"))


def test_a_mana_unit_must_be_a_color_or_colorless() -> None:
    with pytest.raises(ValueError, match="mana"):
        Mana("X")
