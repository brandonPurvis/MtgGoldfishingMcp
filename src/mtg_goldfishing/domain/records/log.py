"""Building a log entry from an accepted call's events and the game before and after it."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence

from mtg_goldfishing.domain.events import (
    AskAnswered,
    AssumptionMade,
    AttackDeclared,
    AutomaticPass,
    BlocksDeclared,
    CardMoved,
    CardPlayed,
    CardsDiscarded,
    CardsDrawn,
    CastTriggerApplied,
    ChecksOverridden,
    ChoiceResolved,
    CombatDamageDealt,
    CombatDamageToSeats,
    ContestedGameStarted,
    CostPaid,
    EffectRecorded,
    EliminationCause,
    Event,
    ExpectationMismatched,
    GameEnded,
    GameStarted,
    HandKept,
    ItemCountered,
    ItemRemoved,
    ItemResolved,
    ItemStacked,
    LibraryShuffled,
    MulliganTaken,
    NoBlocksDeclared,
    NoticeRaised,
    SeatEliminated,
    StepsEntered,
    TrampleDamageStated,
)
from mtg_goldfishing.domain.game.model import Game, Reminder
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by, public_form
from mtg_goldfishing.domain.records.model import (
    AutoPassRecord,
    ContestedEntry,
    EliminationRecord,
    LogEntry,
    Payment,
    ReminderRecord,
    ResolvedRecord,
    SeatEvents,
    SeatFinal,
)
from mtg_goldfishing.domain.records.redaction import (
    opposing_seat_ids,
    redacted,
    stored_arguments,
)

DELTA_TOOLS = ("play", "effect", "choose")
"""The tools whose calls apply a delta, and so can have bookkeeping added to it."""


# @spec REC-001, REC-003, REC-004, REC-005, REC-006, REC-007, REC-008, REC-027, REC-030
# @spec REC-057, REC-058, REC-065, REC-061, REC-072, REC-073, REC-075, REC-076, REC-080
# @spec REC-082, REC-083, REC-084, REC-085
def log_entry(
    *,
    tool: str,
    arguments: Mapping[str, object],
    before: Game | None,
    after: Game,
    summary: Event,
    events: Sequence[Event],
    seat: SeatNumber | None = None,
    final: Sequence[SeatFinal] | None = None,
) -> LogEntry:
    """The log entry for an accepted call that changed a game, made by `seat` (None for
    `new_game`, which no seat makes).

    `before` is the game as it was when the call was made (None for `new_game`); `after`
    is the game once the call has been counted as its next change. Everything is taken
    from the call's summary and events and from those two games, never from response text.
    Every value is JSON-compatible data, so the entry can be stored and exported.

    In a contested game the entry also places the call among the seats and holds its
    public and private events, and no opposing seat's seat id is kept anywhere in it.
    """
    reported = (summary, *events)
    played = _first(reported, CardPlayed)
    effect = _first(reported, EffectRecorded)
    seat_ids = opposing_seat_ids(after) if after.contested else ()
    entry = LogEntry(
        seq=after.change,
        turn=_turn(before, after),
        step=before.step if before else None,
        tool=tool,
        arguments=stored_arguments(copy.deepcopy(dict(arguments)), after.game_id, seat_ids),
        outcome=_outcome(tool, reported, after),
        card=played.card if played else effect.source if effect else None,
        from_zone=played.from_zone if played else None,
        delta=_delta(tool, arguments, before, after, reported),
        choices=_mapping(arguments.get("choices")),
        cast_triggers=_cast_triggers(arguments, reported),
        paid=_payment(reported),
        drawn=tuple(card for e in reported if isinstance(e, CardsDrawn) for card in e.cards),
        steps=tuple(
            entered.step for e in reported if isinstance(e, StepsEntered) for entered in e.steps
        ),
        reason=_text(arguments.get("reason")),
        override=_text(arguments.get("override")),
        overridden_checks=tuple(
            check.kind.value
            for e in reported
            if isinstance(e, ChecksOverridden)
            for check in e.checks
        ),
        expect_mismatches=tuple(
            f"{e.key}: {e.actual}, expected {e.expected}"
            for e in reported
            if isinstance(e, ExpectationMismatched)
        ),
        reminders=_reminders_issued(before, after),
        assumptions=tuple(_assumption(e) for e in reported if isinstance(e, AssumptionMade)),
        notices=tuple(e.notice.value for e in reported if isinstance(e, NoticeRaised)),
        contested=_contested(tool, before, after, seat, reported) if after.contested else None,
    )
    return redacted(entry, seat_ids)


def _turn(before: Game | None, after: Game) -> int:
    """The turn the call was made in: the turn number of a goldfish game; in a contested
    game the own turn count of the seat then active, 0 while no seat was."""
    if before is None:
        return 0
    if not after.contested:
        return before.turn
    return 0 if before.active is None else before.seat(before.active).turns


def _shown_to_others(
    after: Game, seat: SeatNumber | None, reported: Sequence[Event], public: tuple[Event, ...]
) -> tuple[SeatEvents, ...]:
    """The call's events as each seat other than the calling one may see them, for each
    that may see more of them than their public form."""
    shown: list[SeatEvents] = []
    for other in after.seats:
        if other.number == seat:
            continue
        seen = as_seen_by(reported, other.number)
        if seen != public:
            shown.append(SeatEvents(other.number, seen))
    return tuple(shown)


# @spec REC-028, REC-029, REC-031, REC-038, REC-039, REC-040, REC-060, REC-062, REC-067
# @spec REC-068, REC-077, REC-078, REC-032, REC-034, REC-036, REC-037, REC-066, REC-035
# @spec REC-088
def _contested(
    tool: str,
    before: Game | None,
    after: Game,
    seat: SeatNumber | None,
    reported: Sequence[Event],
) -> ContestedEntry:
    """Who made the call and where the game stood; what any seat may see of it, and what
    each other seat that may see more of it is shown. `new_game`, which no seat makes, is
    shown to no seat."""
    public: tuple[Event, ...] = ()
    private: tuple[SeatEvents, ...] = ()
    if tool != "new_game":
        public = public_form(reported)
        private = _shown_to_others(after, seat, reported, public)
    return ContestedEntry(
        seat=seat,
        active=before.active if before else None,
        table_turn=before.turn if before else 0,
        round=before.round if before else 0,
        eliminated=tuple(
            EliminationRecord(e.seat, e.cause.value)
            for e in reported
            if isinstance(e, SeatEliminated)
        ),
        no_blocks=tuple(e.seat for e in reported if isinstance(e, NoBlocksDeclared)),
        public=public,
        private=private,
        stacked=next((e.item for e in reported if isinstance(e, ItemStacked)), None),
        resolved=tuple(
            ResolvedRecord(e.item, e.controller, e.source, copy.deepcopy(e.delta), e.to)
            for e in reported
            if isinstance(e, ItemResolved)
        ),
        countered=tuple(e.item for e in reported if isinstance(e, ItemCountered)),
        removed=tuple(e.item for e in reported if isinstance(e, ItemRemoved)),
        auto_passes=tuple(
            AutoPassRecord(e.seat, e.item) for e in reported if isinstance(e, AutomaticPass)
        ),
    )


def _stated_triggers(arguments: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The call's cast triggers as received, in the order listed."""
    stated = arguments.get("cast_triggers")
    if not isinstance(stated, list | tuple):
        return []
    return [entry for entry in stated if isinstance(entry, Mapping)]


# @spec REC-083, REC-084, REC-085
def _cast_triggers(
    arguments: Mapping[str, object], reported: Sequence[Event]
) -> tuple[dict[str, object], ...]:
    """The cast triggers the call stated, in the order listed: in a goldfish game each delta
    as applied, with what the service added; in a contested game each delta as stated, with
    the id of the stack item the trigger became. None for a call that stated none."""
    stated = _stated_triggers(arguments)
    applied = [e for e in reported if isinstance(e, CastTriggerApplied)]
    if applied:
        return tuple(
            {
                "source": event.source,
                "delta": copy.deepcopy(event.delta),
                "choices": _mapping(entry.get("choices")),
            }
            for event, entry in zip(applied, stated, strict=False)
        )
    spell = _first(reported, ItemStacked)
    if spell is None:
        return ()
    items = [e.item for e in reported if isinstance(e, ItemStacked) and e.cast_with == spell.item]
    return tuple(
        {
            "source": entry.get("source"),
            "delta": _mapping(entry.get("delta")),
            "choices": _mapping(entry.get("choices")),
            "item": item,
        }
        for entry, item in zip(stated, reversed(items), strict=False)
    )


def _without_cast_triggers(added: dict[str, object], reported: Sequence[Event]) -> None:
    """Take out of a goldfish spell's bookkeeping what its cast triggers added, which their
    own entries hold."""
    for event in reported:
        if not isinstance(event, CastTriggerApplied):
            continue
        theirs = event.delta.get("added")
        if not isinstance(theirs, Mapping):
            continue
        shuffles = theirs.get("shuffles")
        if isinstance(shuffles, int) and isinstance(added["shuffles"], int):
            added["shuffles"] -= shuffles
        for key in ("commander_redirected", "tokens_gone"):
            mine, others = added[key], theirs.get(key)
            if isinstance(mine, list) and isinstance(others, list):
                for name in others:
                    if name in mine:
                        mine.remove(name)


def _first[E](reported: Sequence[Event], kind: type[E]) -> E | None:
    return next((e for e in reported if isinstance(e, kind)), None)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): copy.deepcopy(item) for key, item in value.items()}


# @spec REC-033
def _delta(
    tool: str,
    arguments: Mapping[str, object],
    before: Game | None,
    after: Game,
    reported: Sequence[Event],
) -> dict[str, object] | None:
    """The delta as received, with the bookkeeping the service added under `added`; for a
    call whose item went on the stack, only what was added when it was cast (REC-033).

    `added` is `{"shuffles": int, "commander_redirected": [name], "tokens_gone": [name]}`:
    the library shuffles the call performed, the commanders sent to the command zone
    instead of the graveyard or exile, and the tokens that ceased to exist on leaving the
    battlefield. The delta is None when the call carried none and the service added nothing.
    """
    if tool not in DELTA_TOOLS:
        return None
    received = _mapping(arguments.get("delta"))
    stacked = next((i for i, e in enumerate(reported) if isinstance(e, ItemStacked)), None)
    if stacked is not None:
        reported = reported[:stacked]
    moves = [e for e in reported if isinstance(e, CardMoved)]
    shuffles = _shuffles(after) - _shuffles(before) if before else 0
    if stacked is not None:
        shuffles = sum(1 for e in reported if isinstance(e, LibraryShuffled))
    added: dict[str, object] = {
        "shuffles": shuffles,
        "commander_redirected": [m.card for m in moves if m.commander_redirected],
        "tokens_gone": [m.card for m in moves if m.token_gone],
    }
    _without_cast_triggers(added, reported)
    if received is None and not any(added.values()):
        return None
    return {**(received or {}), "added": added}


def _shuffles(game: Game) -> int:
    """The library shuffles of every seat so far."""
    return sum(seat.shuffles for seat in game.seats)


def _reminders(game: Game) -> list[tuple[SeatNumber, Reminder]]:
    """Every seat's reminders, seat by seat in turn order, with the seat each was issued to."""
    return [(seat.number, reminder) for seat in game.seats for reminder in seat.reminders]


def _reminder_key(seat: SeatNumber, reminder: Reminder) -> tuple[object, ...]:
    return (seat, reminder.instance_id, reminder.step, reminder.turn)


def _payment(reported: Sequence[Event]) -> Payment | None:
    paid = _first(reported, CostPaid)
    if paid is None or paid.unpaid:
        return None
    return Payment(
        cost=str(paid.cost),
        sources=(*paid.tapped, *paid.sacrificed),
        life=paid.life,
        from_pool=paid.from_pool,
        surplus=paid.surplus,
    )


def _assumption(event: AssumptionMade) -> str:
    parts = (event.kind.value, event.card, event.text)
    return ": ".join(part for part in parts if part)


# @spec REC-041
def _reminders_issued(before: Game | None, after: Game) -> tuple[ReminderRecord, ...]:
    """The reminders the call issued: those the game holds after it and did not before. In
    a contested game each names the seat it was issued to."""
    earlier = Counter(_reminder_key(*held) for held in _reminders(before)) if before else Counter()
    issued: list[ReminderRecord] = []
    for seat, reminder in _reminders(after):
        key = _reminder_key(seat, reminder)
        if earlier[key] > 0:
            earlier[key] -= 1
            continue
        issued.append(
            ReminderRecord(
                card=reminder.name,
                step=reminder.step,
                instance_id=reminder.instance_id,
                card_name=reminder.card_name
                or _card_name(before, after, reminder.instance_id)
                or reminder.name,
                turn=after.turn,
                seat=seat if after.contested else None,
            )
        )
    return tuple(issued)


def _card_name(before: Game | None, after: Game, instance_id: str) -> str | None:
    for game in (after, before):
        card = game.find(instance_id) if game else None
        if card is not None:
            return card.name
    return None


# @spec REC-074, REC-087
def _outcome(tool: str, reported: Sequence[Event], after: Game) -> dict[str, object] | None:
    """What the tool produced that no other field of the entry carries.

    Cards discarded are an outcome only of `advance`; a delta's discard is in the delta. A
    contested game's `new_game` holds every seat's opening hand by seat number; its attack
    the seat each attacker attacks; a trample statement each named attacker's trample damage,
    by name and instance id, and the seat it attacks; its combat damage the seat each attacker
    dealt it to;
    a blocks answer each blocker and the attacker it blocks; an ask answer its answer
    text, when it carries some; a concession its notes.
    """
    outcome: dict[str, object] = {}
    for event in reported:
        if isinstance(event, ContestedGameStarted):
            outcome["hand"] = {
                str(seat.number.value): [card.name for card in after.hand_of(seat.number)]
                for seat in after.seats
            }
        elif isinstance(event, GameStarted | MulliganTaken):
            outcome["hand"] = list(event.hand)
        elif isinstance(event, HandKept):
            outcome["hand"] = list(event.hand)
            outcome["bottomed"] = list(event.bottomed)
        elif isinstance(event, AskAnswered) and event.text is not None:
            outcome["text"] = event.text
        elif isinstance(event, ChoiceResolved):
            outcome["placements"] = [{"card": p.card, "to": p.to} for p in event.placements]
        elif isinstance(event, AttackDeclared) and event.targets:
            outcome["attackers"] = list(event.attackers)
            outcome["targets"] = [
                {"attacker": attacker, "seat": seat.value} for attacker, seat in event.targets
            ]
        elif isinstance(event, AttackDeclared):
            outcome["attackers"] = list(event.attackers)
            outcome["blocked"] = list(event.blocked)
            outcome["targets"] = dict(event.commander_targets)
        elif isinstance(event, TrampleDamageStated):
            outcome["trample"] = [
                {
                    "attacker": entry.attacker,
                    "attacker_id": entry.attacker_id,
                    "damage": entry.damage,
                    "seat": entry.seat.value,
                }
                for entry in event.entries
            ]
        elif isinstance(event, CombatDamageToSeats):
            outcome["damage"] = [
                {"attacker": h.attacker, "damage": h.damage, "seat": h.seat.value}
                for h in event.hits
            ]
        elif isinstance(event, BlocksDeclared):
            outcome["blocks"] = {
                block.blocker_id: {
                    "blocker": block.blocker,
                    "attacker": block.attacker,
                    "attacker_id": block.attacker_id,
                }
                for block in event.blocks
            }
        elif isinstance(event, SeatEliminated) and event.cause is EliminationCause.CONCEDE:
            outcome["result"] = None
            outcome["notes"] = event.notes
        elif isinstance(event, CombatDamageDealt):
            outcome["damage"] = [
                {"attacker": h.attacker, "damage": h.damage, "commander_target": h.commander_target}
                for h in event.hits
            ]
        elif isinstance(event, CardsDiscarded) and tool == "advance":
            outcome["discarded"] = list(event.cards)
        elif isinstance(event, GameEnded):
            outcome["result"] = event.result
            outcome["notes"] = event.notes
    return outcome or None
