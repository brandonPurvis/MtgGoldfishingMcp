"""The auto payment system: of every valid payment, the one that leaves the most options.

Payments are compared by these rules in order, each breaking ties left by the one before:
most other cards still castable; most colors still available; most mana still available;
the cheapest kind of source; the lowest instance ids. (Which Phyrexian symbols are paid with
life is decided by the caller, which searches with as many paid with life as allow a payment.)

A permanent with several mana abilities is used through at most one of them in a payment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

from mtg_goldfishing.domain.mana import COLORS, ManaString
from mtg_goldfishing.domain.payment.matching import Assignment, Requirement, Unit, assign
from mtg_goldfishing.domain.payment.sources import (
    CREATURE,
    LIFE_LAND,
    OTHER_PERMANENT,
    Source,
    by_permanent,
    most_mana_of,
)

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
    """Interchangeable permanents, lowest instance first, each with the same abilities."""

    permanents: list[tuple[Source, ...]]

    @property
    def size(self) -> int:
        return len(self.permanents)

    @property
    def abilities(self) -> int:
        return len(self.permanents[0])

    def ways_to_use(self) -> list[tuple[int, ...]]:
        """Every split of the permanents among the abilities: how many pay through each.

        Leaving a permanent unused is worth trying only when every ability has a cost.
        """
        must_use_all = any(not (s.mana_cost or s.life) for s in self.permanents[0])
        lowest = self.size if must_use_all else 0
        return [
            split
            for total in range(self.size, lowest - 1, -1)
            for split in _splits(total, self.abilities)
        ]


def _splits(total: int, parts: int) -> list[tuple[int, ...]]:
    if parts == 1:
        return [(total,)]
    return [
        (first, *rest)
        for first in range(total, -1, -1)
        for rest in _splits(total - first, parts - 1)
    ]


def _groups(sources: Sequence[Source]) -> list[_Group]:
    groups: dict[tuple[object, ...], _Group] = {}
    for abilities in by_permanent(sources):
        key = tuple(source.group_key() for source in abilities)
        groups.setdefault(key, _Group([])).permanents.append(abilities)
    for group in groups.values():
        group.permanents.sort(key=lambda abilities: abilities[0].number)
    return list(groups.values())


def _chosen(groups: Sequence[_Group], counts: Sequence[Sequence[int]]) -> list[Source]:
    """The sources used when, in each group, `counts[g][a]` permanents pay through ability a."""
    chosen: list[Source] = []
    for group, per_ability in zip(groups, counts, strict=True):
        start = 0
        for ability, n in enumerate(per_ability):
            chosen.extend(abilities[ability] for abilities in group.permanents[start : start + n])
            start += n
    return chosen


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
    """Whether the sources, each permanent through at most one ability, pay the requirement.

    Decided exactly: every way of using the permanents is tried, interchangeable ones by count.
    """
    groups = _groups(sources)
    for counts in product(*(group.ways_to_use() for group in groups)):
        chosen = _chosen(groups, counts)
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
    used = {s.instance_id for s in sources}
    remaining = [s for s in available if s.instance_id not in used]
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
    mana = most_mana_of(remaining) + len(left_units)
    kinds = (
        sum(1 for s in sources if s.rank == CREATURE),
        sum(1 for s in sources if s.rank == OTHER_PERMANENT),
        sum(1 for s in sources if s.rank == LIFE_LAND),
    )
    castable = _castable(others, left_units, remaining, life_budget)
    return (-castable, -len(colors), -mana, kinds, tuple(sorted(s.number for s in sources)))


# @spec PAY-018, PAY-022, PAY-023, PAY-024, PAY-025, PAY-026, PAY-027, PAY-028, PAY-029
# @spec PAY-041
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

    `pool` is the mana left in the pool that may pay this cost. Identical permanents are
    interchangeable; payments are examined in a fixed order, at most `limit` of them. The
    search adds one permanent at a time through one of its abilities, taking the slots (a
    group of interchangeable permanents and one of their abilities) in a fixed order and
    never returning to an earlier slot.
    """
    if not can_pay_with(requirement, pool, available, life_budget=life_budget):
        return None
    groups = _groups(available)
    slots = [(g, a) for g, group in enumerate(groups) for a in range(group.abilities)]
    used = [[0] * group.abilities for group in groups]
    best: tuple[ScoreKey, SourcePayment] | None = None
    examined = 0

    def chosen() -> list[Source]:
        return _chosen(groups, used)

    def rest_from(start: int) -> list[Source]:
        """The chosen sources, and every source the search may still add from slot `start` on."""
        rest = chosen()
        for g, a in slots[start:]:
            rest.extend(abilities[a] for abilities in groups[g].permanents[sum(used[g]) :])
        return rest

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
        for s in range(start, len(slots)):
            g, a = slots[s]
            if sum(used[g]) >= groups[g].size:
                continue
            used[g][a] += 1
            if can_pay_with(requirement, pool, rest_from(s), life_budget=life_budget):
                search(s)
            used[g][a] -= 1
            if examined >= limit:
                return

    search(0)
    return (best[1], best[0]) if best else None
