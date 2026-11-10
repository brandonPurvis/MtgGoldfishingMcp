"""Building a log entry from an accepted call's events and the game before and after it."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence

from mtg_goldfishing.domain.events import (
    AssumptionMade,
    AttackDeclared,
    CardMoved,
    CardPlayed,
    CardsDiscarded,
    CardsDrawn,
    ChecksOverridden,
    ChoiceResolved,
    CombatDamageDealt,
    CostPaid,
    EffectRecorded,
    Event,
    ExpectationMismatched,
    GameEnded,
    GameStarted,
    HandKept,
    MulliganTaken,
    NoticeRaised,
    StepsEntered,
)
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import LogEntry, Payment, ReminderRecord

DELTA_TOOLS = ("play", "effect", "choose")
"""The tools whose calls apply a delta, and so can have bookkeeping added to it."""


# @spec REC-001, REC-003, REC-004, REC-005, REC-006, REC-007, REC-008
def log_entry(
    *,
    tool: str,
    arguments: Mapping[str, object],
    before: Game | None,
    after: Game,
    summary: Event,
    events: Sequence[Event],
) -> LogEntry:
    """The log entry for an accepted call that changed a game.

    `before` is the game as it was when the call was made (None for `new_game`); `after`
    is the game once the call has been counted as its next change. Everything is taken
    from the call's summary and events and from those two games, never from response text.
    Every value is JSON-compatible data, so the entry can be stored and exported.
    """
    reported = (summary, *events)
    played = _first(reported, CardPlayed)
    effect = _first(reported, EffectRecorded)
    return LogEntry(
        seq=after.change,
        turn=before.turn if before else 0,
        step=before.step if before else None,
        tool=tool,
        arguments=copy.deepcopy(dict(arguments)),
        outcome=_outcome(tool, reported),
        card=played.card if played else effect.source if effect else None,
        from_zone=played.from_zone if played else None,
        delta=_delta(tool, arguments, before, after, reported),
        choices=_mapping(arguments.get("choices")),
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
    )


def _first[E](reported: Sequence[Event], kind: type[E]) -> E | None:
    return next((e for e in reported if isinstance(e, kind)), None)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): copy.deepcopy(item) for key, item in value.items()}


def _delta(
    tool: str,
    arguments: Mapping[str, object],
    before: Game | None,
    after: Game,
    reported: Sequence[Event],
) -> dict[str, object] | None:
    """The delta as received, with the bookkeeping the service added under `added`.

    `added` is `{"shuffles": int, "commander_redirected": [name], "tokens_gone": [name]}`:
    the library shuffles the call performed, the commanders sent to the command zone
    instead of the graveyard or exile, and the tokens that ceased to exist on leaving the
    battlefield. The delta is None when the call carried none and the service added nothing.
    """
    if tool not in DELTA_TOOLS:
        return None
    received = _mapping(arguments.get("delta"))
    moves = [e for e in reported if isinstance(e, CardMoved)]
    added: dict[str, object] = {
        "shuffles": after.shuffles - before.shuffles if before else 0,
        "commander_redirected": [m.card for m in moves if m.commander_redirected],
        "tokens_gone": [m.card for m in moves if m.token_gone],
    }
    if received is None and not any(added.values()):
        return None
    return {**(received or {}), "added": added}


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


def _reminders_issued(before: Game | None, after: Game) -> tuple[ReminderRecord, ...]:
    """The reminders the call issued: those the game gained in its current turn.

    A game keeps only the current turn's reminders, adding to them as steps are entered.
    """
    kept = len(before.reminders) if before and before.turn == after.turn else 0
    return tuple(
        ReminderRecord(
            card=reminder.name,
            step=reminder.step,
            instance_id=reminder.instance_id,
            card_name=reminder.card_name
            or _card_name(before, after, reminder.instance_id)
            or reminder.name,
            turn=after.turn,
        )
        for reminder in after.reminders[kept:]
    )


def _card_name(before: Game | None, after: Game, instance_id: str) -> str | None:
    for game in (after, before):
        card = game.find(instance_id) if game else None
        if card is not None:
            return card.name
    return None


def _outcome(tool: str, reported: Sequence[Event]) -> dict[str, object] | None:
    """What the tool produced that no other field of the entry carries.

    Cards discarded are an outcome only of `advance`; a delta's discard is in the delta.
    """
    outcome: dict[str, object] = {}
    for event in reported:
        if isinstance(event, GameStarted | MulliganTaken):
            outcome["hand"] = list(event.hand)
        elif isinstance(event, HandKept):
            outcome["hand"] = list(event.hand)
            outcome["bottomed"] = list(event.bottomed)
        elif isinstance(event, ChoiceResolved):
            outcome["placements"] = [{"card": p.card, "to": p.to} for p in event.placements]
        elif isinstance(event, AttackDeclared):
            outcome["attackers"] = list(event.attackers)
            outcome["blocked"] = list(event.blocked)
            outcome["targets"] = dict(event.commander_targets)
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
