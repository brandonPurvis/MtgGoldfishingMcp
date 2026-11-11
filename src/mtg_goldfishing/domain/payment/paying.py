"""Paying a cost: agent-directed sources first, then the pool, then the auto payment system."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import islice, product

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AssumptionKind,
    AssumptionMade,
    CheckKind,
    CostPaid,
    Error,
    ErrorKind,
    Event,
    FailedCheck,
    InstanceChosen,
)
from mtg_goldfishing.domain.game.cards_in_play import (
    card_of,
    face_name,
    is_land,
    is_summoning_sick,
)
from mtg_goldfishing.domain.game.model import (
    CardInstance,
    Destination,
    Game,
    PaymentRecord,
    Zone,
)
from mtg_goldfishing.domain.game.movement import move
from mtg_goldfishing.domain.game.naming import Purpose, resolve
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import COLORS, Mana, ManaPool, ManaString, Restriction
from mtg_goldfishing.domain.payment.auto import (
    OtherCard,
    ScoreKey,
    SourcePayment,
    choose_payment,
    score_key,
)
from mtg_goldfishing.domain.payment.matching import (
    Assignment,
    Requirement,
    Unit,
    phyrexian_symbols,
    spend_pool,
    ways_to_pay_phyrexian,
)
from mtg_goldfishing.domain.payment.sources import (
    Source,
    available_sources,
    most_mana_of,
    most_of_color,
    sources_of,
)

_CHOICE_LIMIT = 64


@dataclass(frozen=True)
class PayWith:
    """A source the agent names, optionally with the mana it makes this time."""

    source: str
    mana: ManaString | None = None


@dataclass(frozen=True)
class PayInstructions:
    """`pay`: sources to use first, a replacement cost, life to pay."""

    with_sources: tuple[PayWith, ...] = ()
    cost: ManaString | None = None
    life: int = 0

    @property
    def is_automatic(self) -> bool:
        return not self.with_sources and self.cost is None and not self.life


def _text_list(value: object) -> list[object] | None:
    return list(value) if isinstance(value, list) else None


# @spec APP-028
def read_pay(data: object) -> PayInstructions | Error:
    """Read the `pay` argument as received."""
    if data is None:
        return PayInstructions()
    if not isinstance(data, Mapping):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="pay")
    unknown = set(data) - {"with", "cost", "life"}
    if unknown:
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="pay", names=tuple(sorted(unknown)))
    with_sources: list[PayWith] = []
    entries = data.get("with", [])
    if isinstance(entries, str):
        entries = [entries]
    if not isinstance(entries, list):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="pay.with")
    for entry in entries:
        if isinstance(entry, str):
            with_sources.append(PayWith(entry))
        elif isinstance(entry, Mapping) and isinstance(entry.get("source"), str):
            mana_text = entry.get("mana")
            mana = None
            if mana_text is not None:
                mana = ManaString.read(str(mana_text))
                if mana is None or not mana.can_be_produced():
                    return Error(ErrorKind.UNPARSEABLE_MANA, subject=str(mana_text))
            with_sources.append(PayWith(str(entry["source"]), mana))
        else:
            return Error(ErrorKind.MALFORMED_ARGUMENT, subject="pay.with")
    cost = None
    if data.get("cost") is not None:
        cost = ManaString.read(str(data["cost"]))
        if cost is None:
            return Error(ErrorKind.UNPARSEABLE_MANA, subject=str(data["cost"]))
    life = data.get("life", 0)
    if not isinstance(life, int) or isinstance(life, bool) or life < 0:
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="pay.life")
    return PayInstructions(tuple(with_sources), cost, life)


@dataclass(frozen=True)
class _NamedUse:
    """One way a named source may be used: through which ability, making which mana."""

    source: Source | None
    output: tuple[Unit, ...]


@dataclass
class _Named:
    """A source the agent named, and the ways it may be used in this payment."""

    card: CardInstance
    uses: list[_NamedUse]


@dataclass(frozen=True)
class PlannedUnit:
    """One mana in play for a payment: where it comes from and what it pays as.

    `pool_mana` is set for mana already in the pool; `paid_as` is None for mana left over,
    which stays in (or goes to) the pool.
    """

    unit: Unit
    restriction: Restriction | None
    pool_mana: Mana | None
    paid_as: str | None


@dataclass
class PaymentPlan:
    """Everything a payment will do, worked out before anything is changed."""

    cost: ManaString
    named: list[tuple[CardInstance, Source | None]]
    sources: tuple[Source, ...]
    units: list[PlannedUnit]
    life: int
    snow: bool
    chosen: list[InstanceChosen] = field(default_factory=list)

    @property
    def mana_spent(self) -> int:
        return sum(1 for unit in self.units if unit.paid_as is not None)


def other_cards(
    game: Game, deck: LoadedDeck, seat: SeatNumber, playing: CardInstance | None
) -> list[OtherCard]:
    """The paying seat's cards in hand (other than the one being played) and its commanders
    in the command zone."""
    paying = game.seat(seat)
    others: list[OtherCard] = []
    for card in game.hand_of(seat):
        if playing is not None and card.id == playing.id:
            continue
        data = card_of(deck, card)
        if data is None or is_land(deck, card):
            continue
        costs = tuple(
            (face.mana_cost.with_x(0), face.type_line) for face in data.faces if face.has_mana_cost
        )
        if costs:
            others.append(OtherCard(costs))
    for card in game.in_zone(Zone.COMMAND, seat):
        if not card.is_commander or (playing is not None and card.id == playing.id):
            continue
        data = card_of(deck, card)
        if data is None:
            continue
        tax = ManaString.parse(f"{{{paying.commander_tax(card)}}}")
        costs = tuple(
            (face.mana_cost.with_x(0) + tax, face.type_line)
            for face in data.faces
            if face.has_mana_cost
        )
        if costs:
            others.append(OtherCard(costs))
    return others


def _units_of(mana: ManaString) -> list[Unit]:
    return [frozenset({kind}) for kind in mana.produced()]


def _ability_making(abilities: Sequence[Source], mana: ManaString) -> Source | None:
    """The ability of a named source that can make the stated mana, else its first."""
    stated = sorted(mana.produced())
    for ability in abilities:
        if any(sorted(option) == stated for option in ability.options):
            return ability
    return abilities[0] if abilities else None


def _resolve_named(
    game: Game, deck: LoadedDeck, seat: SeatNumber, entries: Sequence[PayWith]
) -> tuple[list[_Named], list[Error | FailedCheck], list[InstanceChosen]]:
    named: list[_Named] = []
    problems: list[Error | FailedCheck] = []
    names = [entry.source for entry in entries]
    found = resolve(game, deck, seat, names, [Zone.BATTLEFIELD], purpose=Purpose.TAP)
    if isinstance(found, Error):
        return [], [found], []
    cards, chosen_events = found
    for entry, card in zip(entries, cards, strict=True):
        name = face_name(deck, card)
        if card.tapped:
            problems.append(Error(ErrorKind.SOURCE_TAPPED, subject=name))
            continue
        if is_summoning_sick(game, deck, card):
            problems.append(FailedCheck(CheckKind.SUMMONING_SICK_SOURCE, subject=name))
        abilities = [s for s in sources_of(game, deck, card) if s.options]
        if entry.mana is not None:
            source = _ability_making(abilities, entry.mana)
            named.append(_Named(card, [_NamedUse(source, tuple(_units_of(entry.mana)))]))
        elif abilities:
            uses = [
                _NamedUse(ability, tuple(output))
                for ability in abilities
                for output in ability.unit_choices()
            ]
            named.append(_Named(card, uses))
        else:
            problems.append(Error(ErrorKind.SOURCE_MANA_UNKNOWN, subject=name))
    return named, problems, list(chosen_events)


def _missing_colors(
    requirement: Requirement, pool: Sequence[Unit], sources: Sequence[Source]
) -> tuple[str, ...]:
    missing = []
    for color in COLORS:
        needed = sum(1 for need in requirement.constrained if need == frozenset({color}))
        if not needed:
            continue
        makers = sum(1 for unit in pool if color in unit) + most_of_color(sources, color)
        if makers < needed:
            missing.append(color)
    return tuple(missing)


def _plan_units(
    first: Sequence[tuple[Unit, Restriction | None, Mana | None]],
    spent: Assignment,
    payment: SourcePayment | None,
) -> list[PlannedUnit]:
    """Combine how the pool and named sources paid with how the auto-chosen sources paid."""
    planned: list[PlannedUnit] = []
    leftover_index = 0
    second = payment.assignment.paid_as if payment else ()
    for (unit, restriction, pool_mana), paid in zip(first, spent.paid_as, strict=True):
        kind = paid
        if kind is None and payment is not None:
            kind = second[leftover_index]
            leftover_index += 1
        planned.append(PlannedUnit(unit, restriction, pool_mana, kind))
    if payment is not None:
        source_units = [
            (unit, source.restriction)
            for source, output in zip(payment.sources, payment.outputs, strict=True)
            for unit in output
        ]
        for (unit, restriction), kind in zip(source_units, second[leftover_index:], strict=True):
            planned.append(PlannedUnit(unit, restriction, None, kind))
    return planned


@dataclass(frozen=True)
class _Found:
    """How a requirement is paid: the pool and named mana spent, then the sources chosen."""

    key: ScoreKey
    spent: Assignment
    payment: SourcePayment | None


def _pay_rest(
    requirement: Requirement,
    units: Sequence[Unit],
    available: Sequence[Source],
    others: Sequence[OtherCard],
    life_budget: int,
) -> _Found | None:
    """Pay a requirement's mana from mana already made (the pool and named sources) first.

    `life_budget` is the life left once the requirement's own life is paid; it bounds only
    the life the chosen sources cost. When spending the mana already made first leaves a
    remainder no source can pay, that mana and the sources are considered together, so
    spending the pool never makes a cost unpayable.
    """
    requirement = replace(requirement, life=0)
    spent, rest = spend_pool(requirement, units)
    leftover = [u for u, kind in zip(units, spent.paid_as, strict=True) if kind is None]
    if rest.is_empty:
        return _Found(score_key(None, available, leftover, others, life_budget), spent, None)
    chosen = choose_payment(rest, leftover, available, others, life_budget=life_budget)
    if chosen is None and spent.spent:
        spent = Assignment((None,) * len(units))
        chosen = choose_payment(requirement, units, available, others, life_budget=life_budget)
    if chosen is None:
        return None
    payment, key = chosen
    return _Found(key, spent, payment)


PlanKey = tuple[int, ScoreKey]


# @spec PAY-021
def _plan_with_uses(
    life: int,
    cost: ManaString,
    uses: Sequence[_NamedUse],
    *,
    first: Sequence[tuple[Unit, Restriction | None, Mana | None]],
    available: Sequence[Source],
    others: Sequence[OtherCard],
    extra_life: int,
) -> tuple[PlanKey, Requirement, _Found] | None:
    """The best payment once the named sources' uses are fixed.

    Phyrexian symbols are paid with life as far as a valid payment remains: as many as
    life allows are tried first, then one fewer, and so on.
    """
    named_life = sum(use.source.life for use in uses if use.source is not None)
    budget = life - 1 - extra_life - named_life
    units = [unit for unit, _, _ in first]
    most = min(phyrexian_symbols(cost), max(0, budget) // 2)
    for with_life in range(most, -1, -1):
        best: tuple[PlanKey, Requirement, _Found] | None = None
        for way in ways_to_pay_phyrexian(cost, with_life):
            requirement = Requirement.of(cost, life_for=way)
            for use in uses:
                if use.source is not None and use.source.mana_cost:
                    requirement = requirement.plus(use.source.mana_cost)
            found = _pay_rest(requirement, units, available, others, budget - requirement.life)
            if found is None:
                continue
            key: PlanKey = (-with_life, found.key)
            if best is None or key < best[0]:
                best = (key, requirement, found)
        if best is not None:
            return best
    return None


# @spec PAY-020, PAY-030, PAY-031, PAY-032, PAY-033, PAY-034, PAY-035, PAY-036, PAY-038
# @spec PAY-044


def plan_payment(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    cost: ManaString,
    *,
    paying_for: str | None,
    playing: CardInstance | None,
    instructions: PayInstructions,
    subject: str,
) -> tuple[PaymentPlan | None, list[Error | FailedCheck]]:
    """Work out how the paying seat will pay a cost, and the errors and failed checks found
    doing so: from its own pool, with the sources it controls, and with its own life.

    The plan is None when the cost is not payable or an error stops the payment.
    """
    paying = game.seat(seat)
    named, problems, chosen_events = _resolve_named(game, deck, seat, instructions.with_sources)
    if any(isinstance(p, Error) for p in problems):
        return None, problems
    if instructions.cost is not None:
        cost = instructions.cost
    pool_mana = [
        unit
        for unit in paying.mana_pool.units
        if unit.restriction is None or unit.restriction.allows(paying_for)
    ]
    named_ids = {entry.card.id for entry in named}
    available = [
        s
        for s in available_sources(game, deck, seat, paying_for=paying_for)
        if s.instance_id not in named_ids
    ]
    others = other_cards(game, deck, seat, playing)
    best: tuple[PlanKey, PaymentPlan] | None = None
    for uses in islice(product(*(entry.uses for entry in named)), _CHOICE_LIMIT):
        first: list[tuple[Unit, Restriction | None, Mana | None]] = [
            (frozenset({m.kind}), m.restriction, m) for m in pool_mana
        ]
        for use in uses:
            restriction = use.source.restriction if use.source is not None else None
            first.extend((unit, restriction, None) for unit in use.output)
        planned = _plan_with_uses(
            paying.life,
            cost,
            uses,
            first=first,
            available=available,
            others=others,
            extra_life=instructions.life,
        )
        if planned is None:
            continue
        key, requirement, found = planned
        sources = found.payment.sources if found.payment else ()
        plan = PaymentPlan(
            cost=cost,
            named=[(entry.card, use.source) for entry, use in zip(named, uses, strict=True)],
            sources=sources,
            units=_plan_units(first, found.spent, found.payment),
            life=requirement.life
            + instructions.life
            + sum(use.source.life for use in uses if use.source is not None)
            + sum(s.life for s in sources),
            snow=requirement.snow > 0,
            chosen=chosen_events,
        )
        if best is None or key < best[0]:
            best = (key, plan)
    if best is None:
        units = [frozenset({m.kind}) for m in pool_mana]
        budget = paying.life - 1 - instructions.life
        requirement = Requirement.of(
            cost, phyrexian_life=min(phyrexian_symbols(cost), max(0, budget) // 2)
        )
        problems.append(
            FailedCheck(
                CheckKind.COST_NOT_PAYABLE,
                subject=subject,
                cost=cost,
                number=len(units) + most_mana_of(available),
                names=_missing_colors(requirement, units, available),
            )
        )
        return None, problems
    return best[1], problems


def _mana_of(unit: Unit, restriction: Restriction | None) -> Mana:
    return Mana(min(unit, key="CWUBRG".index), restriction)


# @spec PAY-007, PAY-017, PAY-039, PAY-042
def apply_payment(game: Game, deck: LoadedDeck, seat: SeatNumber, plan: PaymentPlan) -> list[Event]:
    """Carry out the paying seat's planned payment: tap, sacrifice, pay its life, update its
    pool."""
    paying = game.seat(seat)
    tapped: list[str] = []
    sacrificed: list[str] = []
    moves: list[Event] = []
    for card, source in plan.named:
        name = face_name(deck, card)
        if source is not None and source.sacrifices:
            sacrificed.append(name)
            moves.extend(move(game, deck, card, Destination.GRAVEYARD))
        else:
            card.tapped = True
            tapped.append(name)
    for source in plan.sources:
        game.instance(source.instance_id).tapped = True
        tapped.append(source.name)
    from_pool = [u.pool_mana for u in plan.units if u.pool_mana is not None and u.paid_as]
    surplus = [
        _mana_of(u.unit, u.restriction)
        for u in plan.units
        if u.pool_mana is None and u.paid_as is None
    ]
    remaining = list(paying.mana_pool.units)
    for mana in from_pool:
        remaining.remove(mana)
    paying.mana_pool = ManaPool(tuple(remaining) + tuple(surplus))
    paying.life -= plan.life
    paying.turn_stats.mana_spent += plan.mana_spent
    paying.turn_stats.payments.append(PaymentRecord(plan.cost, plan.mana_spent, plan.life))

    events: list[Event] = [
        *plan.chosen,
        CostPaid(
            cost=plan.cost,
            tapped=tuple(tapped),
            sacrificed=tuple(sacrificed),
            life=plan.life,
            from_pool=str(ManaPool(tuple(from_pool))) if from_pool else "",
            surplus=str(ManaPool(tuple(surplus))) if surplus else "",
        ),
        *moves,
    ]
    if plan.snow:
        events.append(AssumptionMade(AssumptionKind.SNOW_AS_GENERIC))
    return events
