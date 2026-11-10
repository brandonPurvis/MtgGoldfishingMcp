"""Whether, and how, a set of mana pays a cost. Decided exactly, by bipartite matching.

A cost becomes a *requirement*: symbols that need a particular kind of mana (a color, a
colorless mana, either of two colors), a number of generic mana, and generic hybrid
symbols that take one mana of their color or two of any kind. Mana available to pay it
is a list of *units*, each the set of kinds it can be.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from itertools import combinations, product

from mtg_goldfishing.domain.mana import COLORLESS, ManaString, SymbolKind

Unit = frozenset[str]

_KIND_ORDER = "CWUBRG"


@dataclass(frozen=True)
class Requirement:
    """What a cost needs, after X has been announced and Phyrexian symbols decided."""

    constrained: tuple[Unit, ...] = ()
    generic: int = 0
    generic_hybrid: tuple[str, ...] = ()
    life: int = 0
    snow: int = 0

    @classmethod
    def of(
        cls,
        cost: ManaString,
        *,
        phyrexian_life: int = 0,
        life_for: Collection[int] | None = None,
    ) -> Requirement:
        """The requirement of a cost, paying some of its Phyrexian symbols with life.

        `life_for` gives the positions, among the cost's Phyrexian symbols, of those paid
        with life; without it, the first `phyrexian_life` of them are.
        """
        constrained: list[Unit] = []
        generic = 0
        generic_hybrid: list[str] = []
        life = 0
        snow = 0
        paid_with_life = set(range(phyrexian_life)) if life_for is None else set(life_for)
        phyrexian = 0
        for symbol in cost.symbols:
            match symbol.kind:
                case SymbolKind.COLOR:
                    constrained.append(frozenset(symbol.colors))
                case SymbolKind.COLORLESS:
                    constrained.append(frozenset({COLORLESS}))
                case SymbolKind.GENERIC:
                    generic += symbol.amount
                case SymbolKind.SNOW:
                    generic += 1
                    snow += 1
                case SymbolKind.HYBRID:
                    constrained.append(frozenset(symbol.colors))
                case SymbolKind.GENERIC_HYBRID:
                    generic_hybrid.append(symbol.colors[0])
                case SymbolKind.PHYREXIAN:
                    if phyrexian in paid_with_life:
                        life += 2
                    else:
                        constrained.append(frozenset(symbol.colors))
                    phyrexian += 1
                case SymbolKind.X:
                    pass
        return cls(tuple(constrained), generic, tuple(generic_hybrid), life, snow)

    def plus(self, cost: ManaString) -> Requirement:
        """This requirement and the mana cost of an ability used to pay it."""
        extra = Requirement.of(cost, phyrexian_life=0)
        return replace(
            self,
            constrained=self.constrained + extra.constrained,
            generic=self.generic + extra.generic,
            generic_hybrid=self.generic_hybrid + extra.generic_hybrid,
        )

    @property
    def mana_needed(self) -> int:
        """The least number of mana that can pay this requirement."""
        return len(self.constrained) + self.generic + len(self.generic_hybrid)

    @property
    def is_empty(self) -> bool:
        return self.mana_needed == 0


def phyrexian_symbols(cost: ManaString) -> int:
    return sum(1 for symbol in cost.symbols if symbol.kind is SymbolKind.PHYREXIAN)


def ways_to_pay_phyrexian(cost: ManaString, with_life: int) -> list[tuple[int, ...]]:
    """The distinct ways to pay `with_life` of a cost's Phyrexian symbols with life.

    Each way is the positions, among the Phyrexian symbols, of those paid with life; ways
    that differ only between symbols of the same color are given once, in a fixed order.
    """
    colors = [s.colors for s in cost.symbols if s.kind is SymbolKind.PHYREXIAN]
    ways: list[tuple[int, ...]] = []
    seen: set[tuple[tuple[str, ...], ...]] = set()
    for way in combinations(range(len(colors)), with_life):
        paid = tuple(sorted(colors[i] for i in way))
        if paid not in seen:
            seen.add(paid)
            ways.append(way)
    return ways


def _match(requirements: Sequence[Unit], units: Sequence[Unit]) -> list[int | None] | None:
    """A matching of every requirement to a distinct unit able to pay it, or None."""
    owner: list[int | None] = [None] * len(units)

    def augment(r: int, seen: list[bool]) -> bool:
        for u, unit in enumerate(units):
            if seen[u] or not (requirements[r] & unit):
                continue
            seen[u] = True
            current = owner[u]
            if current is None or augment(current, seen):
                owner[u] = r
                return True
        return False

    for r in range(len(requirements)):
        if not augment(r, [False] * len(units)):
            return None
    return owner


def _kind_paid(requirement: Unit, unit: Unit) -> str:
    both = requirement & unit
    return min(both, key=_KIND_ORDER.index)


def _generic_preference(unit: Unit) -> tuple[int, int]:
    """Spend colorless and narrow units on generic mana first, keeping flexible ones."""
    return (0 if unit == frozenset({COLORLESS}) else 1, len(unit))


@dataclass(frozen=True)
class Assignment:
    """How a requirement is paid: the kind each unit pays as, None for units not spent."""

    paid_as: tuple[str | None, ...]

    @property
    def spent(self) -> int:
        return sum(1 for kind in self.paid_as if kind is not None)


# @spec PAY-002, PAY-003, PAY-004, PAY-019
def assign(requirement: Requirement, units: Sequence[Unit]) -> Assignment | None:
    """Pay a requirement from units, or None if they cannot pay it.

    Generic hybrid symbols are paid with a mana of their color where possible.
    """
    hybrids = requirement.generic_hybrid
    for by_color in product((True, False), repeat=len(hybrids)):
        needs = list(requirement.constrained) + [
            frozenset({color}) for color, paid in zip(hybrids, by_color, strict=True) if paid
        ]
        generic = requirement.generic + 2 * by_color.count(False)
        if len(needs) + generic > len(units):
            continue
        owner = _match(needs, units)
        if owner is None:
            continue
        paid_as: list[str | None] = [
            None if r is None else _kind_paid(needs[r], units[u]) for u, r in enumerate(owner)
        ]
        leftover = sorted(
            (u for u, r in enumerate(owner) if r is None),
            key=lambda u: (_generic_preference(units[u]), u),
        )
        for u in leftover[:generic]:
            paid_as[u] = min(units[u], key=_KIND_ORDER.index)
        return Assignment(tuple(paid_as))
    return None


def can_pay(requirement: Requirement, units: Sequence[Unit]) -> bool:
    return assign(requirement, units) is not None


def _partial_match(requirements: Sequence[Unit], units: Sequence[Unit]) -> list[int | None]:
    """A largest matching of requirements to units; requirements may go unmatched."""
    owner: list[int | None] = [None] * len(units)

    def augment(r: int, seen: list[bool]) -> bool:
        for u, unit in enumerate(units):
            if seen[u] or not (requirements[r] & unit):
                continue
            seen[u] = True
            current = owner[u]
            if current is None or augment(current, seen):
                owner[u] = r
                return True
        return False

    for r in range(len(requirements)):
        augment(r, [False] * len(units))
    return owner


# @spec PAY-006
def spend_pool(requirement: Requirement, pool: Sequence[Unit]) -> tuple[Assignment, Requirement]:
    """Spend as much of a requirement as the pool can pay, before any source is tapped.

    Pool mana goes to the narrowest requirements first (a single color or colorless before
    a hybrid), so what is left is as easy as it can be for the sources to pay. Returns how
    each pool unit was spent and what is left to pay.
    """
    order = sorted(
        range(len(requirement.constrained)), key=lambda r: (len(requirement.constrained[r]), r)
    )
    needs = [requirement.constrained[r] for r in order]
    owner = _partial_match(needs, pool)
    paid_as: list[str | None] = [
        None if r is None else _kind_paid(needs[r], pool[u]) for u, r in enumerate(owner)
    ]
    matched = {order[r] for r in owner if r is not None}
    constrained = tuple(need for r, need in enumerate(requirement.constrained) if r not in matched)
    hybrids_left: list[str] = []
    for color in requirement.generic_hybrid:
        spare = next(
            (u for u, kind in enumerate(paid_as) if kind is None and color in pool[u]), None
        )
        if spare is None:
            hybrids_left.append(color)
        else:
            paid_as[spare] = color
    generic = requirement.generic
    leftover = sorted(
        (u for u, kind in enumerate(paid_as) if kind is None),
        key=lambda u: (_generic_preference(pool[u]), u),
    )
    for u in leftover[:generic]:
        paid_as[u] = min(pool[u], key=_KIND_ORDER.index)
    generic -= min(generic, len(leftover))
    rest = replace(
        requirement,
        constrained=constrained,
        generic=generic,
        generic_hybrid=tuple(hybrids_left),
        life=requirement.life,
    )
    return Assignment(tuple(paid_as)), rest
