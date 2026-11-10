"""`play` and `effect`: the agent states an outcome; the game adds the bookkeeping it implies."""

from __future__ import annotations

from dataclasses import dataclass, replace

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.deck.definitions import apply_definition, definition_reading
from mtg_goldfishing.domain.deck.model import CardDefinition, LoadedDeck
from mtg_goldfishing.domain.events import (
    AssumptionKind,
    AssumptionMade,
    CardMoved,
    CardPlayed,
    CheckKind,
    ChecksOverridden,
    CostPaid,
    EffectRecorded,
    Error,
    ErrorKind,
    Event,
    FailedCheck,
)
from mtg_goldfishing.domain.game.cards_in_play import card_of, reading_of
from mtg_goldfishing.domain.game.model import CardInstance, Destination, Game, Zone
from mtg_goldfishing.domain.game.movement import move
from mtg_goldfishing.domain.game.naming import is_instance_id, matches, resolve_one
from mtg_goldfishing.domain.game.notices import examine_end_conditions
from mtg_goldfishing.domain.game.results import Applied, Problems, Refusal, Result
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.payment.paying import (
    PayInstructions,
    apply_payment,
    plan_payment,
    read_pay,
)
from mtg_goldfishing.domain.play.arguments import (
    Choices,
    Delta,
    Expectation,
    read_choices,
    read_delta,
    read_destination,
    read_expect,
)
from mtg_goldfishing.domain.play.delta import apply_delta
from mtg_goldfishing.domain.play.expectations import compare
from mtg_goldfishing.domain.reading.reader import read_card

OUTSIDE = "outside"
_FROM_ZONES = {
    "hand": Zone.HAND,
    "command": Zone.COMMAND,
    "graveyard": Zone.GRAVEYARD,
    "exile": Zone.EXILE,
    "library": Zone.LIBRARY,
}
_WITHOUT_FROM = (Zone.HAND, Zone.COMMAND)


def _x_replaced(
    cost: ManaString, choices: Choices, card: str | None
) -> tuple[ManaString, list[Event]]:
    """Each {X} replaced by the announced X; X is 0, and said so, when none was announced."""
    if not cost.has_x:
        return cost, []
    if choices.x is None:
        return cost.with_x(0), [AssumptionMade(AssumptionKind.X_IS_ZERO, card)]
    return cost.with_x(choices.x), []


def _pay(
    game: Game,
    deck: LoadedDeck,
    cost: ManaString,
    instructions: PayInstructions,
    problems: Problems,
    *,
    paying_for: str | None,
    playing: CardInstance | None,
    subject: str,
) -> list[Event]:
    """Pay a cost already worked out; an unpayable cost, once overridden, is paid with nothing."""
    plan, found = plan_payment(
        game,
        deck,
        cost,
        paying_for=paying_for,
        playing=playing,
        instructions=replace(instructions, cost=None),
        subject=subject,
    )
    problems.extend(found)
    if plan is not None:
        return apply_payment(game, deck, plan)
    unpayable = any(
        isinstance(p, FailedCheck) and p.kind is CheckKind.COST_NOT_PAYABLE for p in found
    )
    return [CostPaid(cost, unpaid=True)] if unpayable else []


@dataclass(frozen=True)
class _Arguments:
    """The structured arguments `play` and `effect` share, read into value objects."""

    delta: Delta
    choices: Choices
    pay: PayInstructions
    expect: tuple[Expectation, ...]


def _read_arguments(
    delta: object, choices: object, pay: object, expect: object
) -> _Arguments | Error:
    read_d = read_delta(delta)
    if isinstance(read_d, Error):
        return read_d
    read_c = read_choices(choices)
    if isinstance(read_c, Error):
        return read_c
    read_p = read_pay(pay)
    if isinstance(read_p, Error):
        return read_p
    read_e = read_expect(expect)
    if isinstance(read_e, Error):
        return read_e
    return _Arguments(read_d, read_c, read_p, read_e)


def _finish(
    changed: Game,
    deck: LoadedDeck,
    problems: Problems,
    *,
    override: str | None,
    summary: Event,
    events: list[Event],
    expectations: tuple[Expectation, ...],
) -> Result:
    """Judge the call; if applied, compare expectations and re-examine end conditions."""
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    reported: list[Event] = [judged] if isinstance(judged, ChecksOverridden) else []
    reported.extend(events)
    reported.extend(compare(changed, deck, expectations))
    reported.extend(examine_end_conditions(changed))
    return Applied(changed, summary, tuple(reported))


# ------------------------------------------------------------------------------------ play


def _outside_card(
    game: Game, name: str, outside: Card | None, definition: CardDefinition | None
) -> CardInstance | Error:
    """A new instance of a card from outside the game, from its card data or a definition."""
    if definition is not None:
        data = apply_definition(outside, definition)
        if isinstance(data, Error):
            return data
        reading = definition_reading(data, definition)
    elif outside is not None:
        data, reading = outside, read_card(outside)
    else:
        return Error(ErrorKind.CARD_DATA_NEEDED, subject=name)
    # The instance is in no zone until it is played; exile stands in, and nothing reads it.
    instance = CardInstance(
        game.new_instance_id(), data.name, Zone.EXILE, definition=data, reading=reading
    )
    game.cards.append(instance)
    return instance


def _played_face(deck: LoadedDeck, instance: CardInstance, name: str) -> tuple[int, Face] | None:
    data = card_of(deck, instance)
    if data is None:
        return None
    index = 0 if is_instance_id(name) else (data.face_named(name) or 0)
    return index, data.faces[index]


def _spell_cost(
    game: Game,
    instance: CardInstance,
    face: Face,
    *,
    from_zone: Zone | None,
    choices: Choices,
    instructions: PayInstructions,
) -> tuple[ManaString, list[Event]]:
    if instructions.cost is not None:
        return _x_replaced(instructions.cost, choices, face.name)
    events: list[Event] = []
    if not face.has_mana_cost:
        events.append(AssumptionMade(AssumptionKind.NO_MANA_COST, face.name))
    cost = face.mana_cost + (choices.extra_cost or ManaString())
    tax = game.commander_tax(instance) if instance.is_commander else 0
    if from_zone is Zone.COMMAND and tax:
        cost = cost + ManaString.parse(f"{{{tax}}}")
    cost, assumed = _x_replaced(cost, choices, face.name)
    return cost, events + assumed


def _check_timing(
    game: Game, deck: LoadedDeck, instance: CardInstance, face: Face
) -> FailedCheck | None:
    if game.step is not None and game.step.is_main:
        return None
    if face.is_land:
        return FailedCheck(CheckKind.LAND_TIMING, subject=face.name, step=game.step)
    if face.is_instant or reading_of(deck, instance).flash.own:
        return None
    return FailedCheck(CheckKind.SPELL_TIMING, subject=face.name, step=game.step)


# @spec PLAY-001, PLAY-002, PLAY-003, PLAY-004, PLAY-007, PLAY-008, PLAY-009, PLAY-010
# @spec PLAY-011, PLAY-012, PLAY-013, PLAY-014, PLAY-015, PLAY-016, PLAY-017, PLAY-018
# @spec PLAY-019, PLAY-020, PLAY-021, PLAY-022, PLAY-023, PLAY-024, PLAY-025, PLAY-026
# @spec PLAY-027, PLAY-028, PLAY-051, PAY-037
def play(
    game: Game,
    deck: LoadedDeck,
    *,
    card: object,
    from_zone: object = None,
    to: object = None,
    delta: object = None,
    choices: object = None,
    pay: object = None,
    expect: object = None,
    reason: object = None,
    override: str | None = None,
    outside: Card | None = None,
) -> Result:
    """Play a land, a spell or the commander, then apply the call's delta."""
    del reason  # recorded with the call by the application; never judged
    if not isinstance(card, str) or not card.strip():
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="card"))
    requested = from_zone.strip().lower() if isinstance(from_zone, str) else from_zone
    if requested is not None and requested != OUTSIDE and requested not in _FROM_ZONES:
        return Refusal.error(Error(ErrorKind.UNKNOWN_ZONE, subject=str(from_zone)))
    destination = read_destination(to) if to is not None else None
    if isinstance(destination, Error):
        return Refusal.error(destination)
    arguments = _read_arguments(delta, choices, pay, expect)
    if isinstance(arguments, Error):
        return Refusal.error(arguments)
    the_choices, instructions = arguments.choices, arguments.pay

    changed = game.copy()
    events: list[Event] = []
    if requested == OUTSIDE:
        found = _outside_card(changed, card, outside, the_choices.definition)
        if isinstance(found, Error):
            return Refusal.error(found)
        instance, origin = found, OUTSIDE
    else:
        zones = [_FROM_ZONES[str(requested)]] if requested is not None else list(_WITHOUT_FROM)
        resolved = resolve_one(changed, deck, card, zones)
        if isinstance(resolved, Error):
            return Refusal.error(resolved)
        instance, chosen = resolved
        origin = instance.zone.value
        events.extend(chosen)
    played = _played_face(deck, instance, card)
    if played is None:
        return Refusal.error(Error(ErrorKind.CARD_NOT_IN_ZONE, subject=card))
    index, face = played
    instance.face = index
    from_zone_found = None if requested == OUTSIDE else instance.zone

    problems = Problems()
    problems.add(_check_timing(changed, deck, instance, face))
    if face.is_land:
        if changed.land_drops_used >= 1:
            problems.add(
                FailedCheck(
                    CheckKind.LAND_DROP_USED, subject=face.name, number=changed.land_drops_used
                )
            )
        changed.land_drops_used += 1
    else:
        if instructions.cost is not None:
            problems.add(
                FailedCheck(CheckKind.EXPLICIT_COST, subject=face.name, cost=instructions.cost)
            )
        cost, assumed = _spell_cost(
            changed,
            instance,
            face,
            from_zone=from_zone_found,
            choices=the_choices,
            instructions=instructions,
        )
        events.extend(
            _pay(
                changed,
                deck,
                cost,
                instructions,
                problems,
                paying_for=face.type_line,
                playing=instance,
                subject=face.name,
            )
        )
        events.extend(assumed)
        if from_zone_found is Zone.COMMAND and instance.is_commander:
            changed.commander_casts[instance.id] = changed.commander_casts.get(instance.id, 0) + 1

    if destination is None:
        destination = Destination.BATTLEFIELD if face.is_permanent else Destination.GRAVEYARD
    moved = move(changed, deck, instance, destination)
    arrived = next(e for e in moved if isinstance(e, CardMoved))
    events.extend(e for e in moved if not isinstance(e, CardMoved) or e.commander_redirected)
    if instance.zone is not Zone.BATTLEFIELD:
        instance.face = 0

    applied = apply_delta(changed, deck, arguments.delta, source=instance.name)
    if isinstance(applied, Error):
        problems.add(applied)
    else:
        events.extend(applied)
    summary = CardPlayed(instance.name, face.name, origin, arrived.to, face.is_land)
    return _finish(
        changed,
        deck,
        problems,
        override=override,
        summary=summary,
        events=events,
        expectations=arguments.expect,
    )


# ---------------------------------------------------------------------------------- effect


def _answer_reminders(game: Game, changed: Game, deck: LoadedDeck, source: str) -> None:
    """An effect whose source names a permanent answers that permanent's reminders this turn."""
    named = {card.id for card in game.battlefield if matches(deck, card, source)}
    for reminder in changed.reminders:
        if reminder.instance_id in named:
            reminder.answered = True


# @spec PLAY-001, PLAY-002, PLAY-003, PLAY-004, PLAY-021, PLAY-022, PLAY-029, PLAY-030
# @spec PLAY-031, PLAY-032, PLAY-051, PAY-040
def effect(
    game: Game,
    deck: LoadedDeck,
    *,
    source: object,
    delta: object,
    choices: object = None,
    pay: object = None,
    expect: object = None,
    reason: object = None,
    override: str | None = None,
) -> Result:
    """Record a change not caused by playing a card, paying `pay` first when it is given."""
    del reason  # recorded with the call by the application; never judged
    if not isinstance(source, str):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="source"))
    arguments = _read_arguments(delta, choices, pay, expect)
    if isinstance(arguments, Error):
        return Refusal.error(arguments)
    the_choices, instructions = arguments.choices, arguments.pay

    changed = game.copy()
    events: list[Event] = []
    problems = Problems()
    if pay is not None:
        cost = (instructions.cost or ManaString()) + (the_choices.extra_cost or ManaString())
        cost, assumed = _x_replaced(cost, the_choices, None)
        events.extend(
            _pay(
                changed,
                deck,
                cost,
                instructions,
                problems,
                paying_for=None,
                playing=None,
                subject=source,
            )
        )
        events.extend(assumed)
    applied = apply_delta(changed, deck, arguments.delta, source=source)
    if isinstance(applied, Error):
        problems.add(applied)
    else:
        events.extend(applied)
    _answer_reminders(game, changed, deck, source)
    return _finish(
        changed,
        deck,
        problems,
        override=override,
        summary=EffectRecorded(source),
        events=events,
        expectations=arguments.expect,
    )
