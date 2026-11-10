"""The auto payment system: of every valid payment, the one that leaves the most options.

Payments are compared by these rules in order, each breaking ties left by the one before:
most other cards still castable; most colors still available; most mana still available;
the cheapest kind of source; the lowest instance ids. (Phyrexian symbols are paid with life
before the search, whenever life stays at 1 or more.)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

from mtg_goldfishing.domain.mana import COLORS, ManaString
from mtg_goldfishing.domain.payment.matching import Assignment, Requirement, Unit, assign
from mtg_goldfishing.domain.payment.sources import CREATURE, LIFE_LAND, OTHER_PERMANENT, Source

PAYMENT_LIMIT = 20_000


@dataclass(frozen=True)
class OtherCard:
    """A card in hand or a commander the auto payment system tries to keep castable."""

    costs: tuple[tuple[ManaString, str], ...]  # each castable face: its cost and type line


@dataclass(frozen=True)
class SourcePayment:
    """The sources chosen to pay a requirement, the output chosen for each, and how it pays."""

    sources: tuple[Source, ...]
    outputs: tuple[tuple[Unit, ...], ...]
    assignment: Assignment


@dataclass
class _Group:
    sources: list[Source]

    @property
    def size(self) -> int:
        return len(self.sources)


def _groups(sources: Sequence[Source]) -> list[_Group]:
    groups: dict[tuple[object, ...], _Group] = {}
    for source in sources:
        groups.setdefault(source.group_key(), _Group([])).sources.append(source)
    return list(groups.values())


def _activation_order_ok(chosen: Sequence[Source], extra_units: int) -> bool:
    """Sources whose ability costs mana need mana from elsewhere to be activated first."""
    costed = sorted((s for s in chosen if s.mana_cost), key=lambda s: s.mana_cost.symbol_count())
    if not costed:
        return True
    available = extra_units + sum(s.most_mana for s in chosen if not s.mana_cost)
    for source in costed:
        if available < source.mana_cost.symbol_count():
            return False
        available += source.most_mana - source.mana_cost.symbol_count()
    return True


def pay_from(
    requirement: Requirement,
    pool: Sequence[Unit],
    chosen: Sequence[Source],
    *,
    life_budget: int,
) -> SourcePayment | None:
    """Pay a requirement with exactly these sources (and the pool), choosing their outputs."""
    if sum(s.life for s in chosen) + requirement.life > life_budget:
        return None
    if not _activation_order_ok(chosen, len(pool)):
        return None
    total = requirement
    for source in chosen:
        if source.mana_cost:
            total = total.plus(source.mana_cost)
    layouts = [source.unit_choices() for source in chosen]
    for outputs in product(*layouts):
        units = list(pool) + [unit for output in outputs for unit in output]
        assignment = assign(total, units)
        if assignment is not None:
            return SourcePayment(tuple(chosen), tuple(tuple(o) for o in outputs), assignment)
    return None


def can_pay_with(
    requirement: Requirement, pool: Sequence[Unit], sources: Sequence[Source], *, life_budget: int
) -> bool:
    """Whether some subset of the sources pays the requirement (decided exactly)."""
    if pay_from(requirement, pool, sources, life_budget=life_budget) is not None:
        return True
    costed = [s for s in sources if s.mana_cost or s.life]
    if not costed:
        return False
    plain = [s for s in sources if not (s.mana_cost or s.life)]
    for keep in product((True, False), repeat=len(costed)):
        chosen = plain + [s for s, k in zip(costed, keep, strict=True) if k]
        if pay_from(requirement, pool, chosen, life_budget=life_budget) is not None:
            return True
    return False


ScoreKey = tuple[int, int, int, tuple[int, int, int], tuple[int, ...]]


def _castable(
    others: Sequence[OtherCard], pool: Sequence[Unit], remaining: Sequence[Source], life: int
) -> int:
    count = 0
    for card in others:
        for cost, type_line in card.costs:
            usable = [
                s for s in remaining if s.restriction is None or s.restriction.allows(type_line)
            ]
            requirement = Requirement.of(cost, phyrexian_life=0)
            if can_pay_with(requirement, pool, usable, life_budget=life):
                count += 1
                break
    return count


def score_key(
    payment: SourcePayment | None,
    available: Sequence[Source],
    pool_left: Sequence[Unit],
    others: Sequence[OtherCard],
    life_budget: int,
) -> ScoreKey:
    """How good a payment is, as a key where smaller is better, rule by rule."""
    sources = payment.sources if payment else ()
    used = {id(s) for s in sources}
    remaining = [s for s in available if id(s) not in used]
    if payment is None:
        left_units = list(pool_left)
    else:
        units = list(pool_left) + [unit for output in payment.outputs for unit in output]
        left_units = [
            unit
            for unit, kind in zip(units, payment.assignment.paid_as, strict=True)
            if kind is None
        ]
    colors = {c for s in remaining for c in s.colors}
    colors |= {c for u in left_units for c in u if c in COLORS}
    mana = sum(s.most_mana for s in remaining) + len(left_units)
    kinds = (
        sum(1 for s in sources if s.rank == CREATURE),
        sum(1 for s in sources if s.rank == OTHER_PERMANENT),
        sum(1 for s in sources if s.rank == LIFE_LAND),
    )
    castable = _castable(others, left_units, remaining, life_budget)
    return (-castable, -len(colors), -mana, kinds, tuple(sorted(s.number for s in sources)))


# @spec PAY-018, PAY-022, PAY-023, PAY-024, PAY-025, PAY-026, PAY-027, PAY-028, PAY-029
def choose_payment(
    requirement: Requirement,
    pool: Sequence[Unit],
    available: Sequence[Source],
    others: Sequence[OtherCard],
    *,
    life_budget: int,
    limit: int = PAYMENT_LIMIT,
) -> tuple[SourcePayment, ScoreKey] | None:
    """The best valid payment of a requirement from the pool and available sources.

    `pool` is the mana left in the pool that may pay this cost. Identical sources are
    interchangeable; payments are examined in a fixed order, at most `limit` of them.
    """
    if not can_pay_with(requirement, pool, available, life_budget=life_budget):
        return None
    groups = _groups(available)
    used = [0] * len(groups)
    best: tuple[ScoreKey, SourcePayment] | None = None
    examined = 0

    def chosen() -> list[Source]:
        return [s for g, n in zip(groups, used, strict=True) for s in g.sources[:n]]

    def rest_from(start: int) -> list[Source]:
        return [
            s
            for i, (g, n) in enumerate(zip(groups, used, strict=True))
            for s in (g.sources if i >= start else g.sources[:n])
        ]

    def search(start: int) -> None:
        nonlocal best, examined
        if examined >= limit:
            return
        payment = pay_from(requirement, pool, chosen(), life_budget=life_budget)
        if payment is not None:
            examined += 1
            key = score_key(payment, available, pool, others, life_budget)
            if best is None or key < best[0]:
                best = (key, payment)
            return
        for i in range(start, len(groups)):
            if used[i] >= groups[i].size:
                continue
            used[i] += 1
            if can_pay_with(requirement, pool, rest_from(i), life_budget=life_budget):
                search(i)
            used[i] -= 1
            if examined >= limit:
                return

    search(0)
    return (best[1], best[0]) if best else None
