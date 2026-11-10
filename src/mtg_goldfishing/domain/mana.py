"""Mana strings, mana units and the mana pool."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum

COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G")
COLORLESS = "C"
MANA_KINDS: tuple[str, ...] = (*COLORS, COLORLESS)

_SYMBOL = re.compile(r"\{([^{}]*)\}")


class SymbolKind(Enum):
    COLOR = "color"
    COLORLESS = "colorless"
    GENERIC = "generic"
    X = "x"
    SNOW = "snow"
    HYBRID = "hybrid"
    GENERIC_HYBRID = "generic_hybrid"
    PHYREXIAN = "phyrexian"


@dataclass(frozen=True)
class Symbol:
    """One brace-enclosed symbol of a mana string."""

    kind: SymbolKind
    colors: tuple[str, ...] = ()
    amount: int = 0

    def __str__(self) -> str:
        match self.kind:
            case SymbolKind.COLOR:
                body = self.colors[0]
            case SymbolKind.COLORLESS:
                body = COLORLESS
            case SymbolKind.GENERIC:
                body = str(self.amount)
            case SymbolKind.X:
                body = "X"
            case SymbolKind.SNOW:
                body = "S"
            case SymbolKind.HYBRID:
                body = "/".join(self.colors)
            case SymbolKind.GENERIC_HYBRID:
                body = f"{self.amount}/{self.colors[0]}"
            case SymbolKind.PHYREXIAN:
                body = f"{self.colors[0]}/P"
        return "{" + body + "}"


def _parse_symbol(body: str) -> Symbol | None:
    simple = {"C": SymbolKind.COLORLESS, "X": SymbolKind.X, "S": SymbolKind.SNOW}
    if body in COLORS:
        return Symbol(SymbolKind.COLOR, (body,))
    if body in simple:
        return Symbol(simple[body])
    if body.isascii() and body.isdigit():
        return Symbol(SymbolKind.GENERIC, amount=int(body))
    left, slash, right = body.partition("/")
    if not slash:
        return None
    if left in COLORS and right in COLORS and left != right:
        return Symbol(SymbolKind.HYBRID, (left, right))
    if left.isascii() and left.isdigit() and right in COLORS:
        return Symbol(SymbolKind.GENERIC_HYBRID, (right,), int(left))
    if left in COLORS and right == "P":
        return Symbol(SymbolKind.PHYREXIAN, (left,))
    return None


@dataclass(frozen=True)
class ManaString:
    """A sequence of mana symbols: a cost, or mana to be produced."""

    symbols: tuple[Symbol, ...] = ()

    # @spec PAY-001
    @classmethod
    def read(cls, text: str) -> ManaString | None:
        """The mana string the text spells, or None when it is not a mana string."""
        symbols = []
        position = 0
        for match in _SYMBOL.finditer(text):
            symbol = _parse_symbol(match.group(1)) if match.start() == position else None
            if symbol is None:
                return None
            symbols.append(symbol)
            position = match.end()
        if position != len(text):
            return None
        return cls(tuple(symbols))

    @classmethod
    def parse(cls, text: str) -> ManaString:
        """The mana string the text spells; for text already known to be one."""
        mana = cls.read(text)
        if mana is None:
            raise ValueError(f"not a mana string: {text!r}")
        return mana

    def symbol_count(self) -> int:
        """How many mana a payment of this string takes, counting a number as that many."""
        return sum(
            symbol.amount if symbol.kind is SymbolKind.GENERIC else 1 for symbol in self.symbols
        )

    def can_be_produced(self) -> bool:
        kinds = (SymbolKind.COLOR, SymbolKind.COLORLESS, SymbolKind.GENERIC)
        return all(symbol.kind in kinds for symbol in self.symbols)

    def __str__(self) -> str:
        return "".join(str(symbol) for symbol in self.symbols)

    def __add__(self, other: ManaString) -> ManaString:
        return ManaString(self.symbols + other.symbols)

    def __bool__(self) -> bool:
        return bool(self.symbols)

    @property
    def has_x(self) -> bool:
        return any(symbol.kind is SymbolKind.X for symbol in self.symbols)

    def with_x(self, x: int) -> ManaString:
        """This mana string with every {X} replaced by a generic symbol of the announced value."""
        generic = Symbol(SymbolKind.GENERIC, amount=x)
        return ManaString(
            tuple(generic if symbol.kind is SymbolKind.X else symbol for symbol in self.symbols)
        )

    def produced(self) -> tuple[str, ...]:
        """The mana units this string stands for when it is mana made rather than a cost."""
        units: list[str] = []
        for symbol in self.symbols:
            if symbol.kind is SymbolKind.COLOR:
                units.append(symbol.colors[0])
            elif symbol.kind is SymbolKind.COLORLESS:
                units.append(COLORLESS)
            elif symbol.kind is SymbolKind.GENERIC:
                units.extend([COLORLESS] * symbol.amount)
            else:
                raise ValueError(f"a mana source cannot produce {symbol}")
        return tuple(units)


@dataclass(frozen=True)
class Restriction:
    """What mana from a source may be spent on."""

    text: str
    card_types: tuple[str, ...] = ()

    def allows(self, type_line: str | None) -> bool:
        if type_line is None or not self.card_types:
            return False
        words = {word.lower() for word in re.split(r"[^A-Za-z]+", type_line)}
        return any(card_type.lower() in words for card_type in self.card_types)


@dataclass(frozen=True)
class Mana:
    """One unit of mana in the pool."""

    kind: str
    restriction: Restriction | None = None

    def __post_init__(self) -> None:
        if self.kind not in MANA_KINDS:
            raise ValueError(f"not a kind of mana: {self.kind!r}")

    def __str__(self) -> str:
        return "{" + self.kind + "}" + ("*" if self.restriction else "")


@dataclass(frozen=True)
class ManaPool:
    """Mana that has been made and not yet spent."""

    units: tuple[Mana, ...] = ()

    def __str__(self) -> str:
        return "".join(str(unit) for unit in self.units) or "{}"

    def __len__(self) -> int:
        return len(self.units)

    def add(self, mana: ManaString, restriction: Restriction | None = None) -> ManaPool:
        return self.add_units(tuple(Mana(kind, restriction) for kind in mana.produced()))

    def add_units(self, units: tuple[Mana, ...]) -> ManaPool:
        return ManaPool(self.units + units)

    def without(self, spent: tuple[Mana, ...]) -> ManaPool:
        remaining = list(self.units)
        for unit in spent:
            remaining.remove(unit)
        return ManaPool(tuple(remaining))

    def same_symbols_as(self, mana: ManaString) -> bool:
        return Counter(unit.kind for unit in self.units) == Counter(mana.produced())
