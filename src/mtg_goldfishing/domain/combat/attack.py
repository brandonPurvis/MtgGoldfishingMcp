"""`attack`: declare attackers and which of them the imaginary opponents block."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from mtg_goldfishing.domain.combat.damage import numeric_power
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AttackDeclared,
    CheckKind,
    Error,
    ErrorKind,
    Event,
    FailedCheck,
)
from mtg_goldfishing.domain.game.cards_in_play import (
    face_name,
    has_haste,
    has_vigilance,
    is_creature,
)
from mtg_goldfishing.domain.game.model import OPPONENTS, Attack, CardInstance, Game, Zone
from mtg_goldfishing.domain.game.naming import Purpose, matches, resolve
from mtg_goldfishing.domain.game.results import Applied, Problems, Refusal, Result
from mtg_goldfishing.domain.steps import Step
from mtg_goldfishing.domain.turn import Walk, return_to_declare_attackers, walk_to

_EARLY = (Step.UNTAP, Step.UPKEEP, Step.DRAW)
_BEFORE_COMBAT = (Step.MAIN1, Step.BEGIN_COMBAT)
_DECLARING = (Step.DECLARE_ATTACKERS, Step.DECLARE_BLOCKERS)


def _names(value: object, argument: str) -> list[str] | Error:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject=argument)


def _attacker_error(error: Error) -> Error:
    """A naming error for `attackers`: one not on the battlefield is said so, with its zone."""
    if error.kind is not ErrorKind.CARD_NOT_IN_ZONE:
        return error
    return replace(error, kind=ErrorKind.ATTACKER_NOT_ON_BATTLEFIELD)


def _among(
    deck: LoadedDeck, attackers: Sequence[CardInstance], names: Sequence[str]
) -> list[CardInstance] | Error:
    """Resolve names to attackers; a name given twice means two different attackers."""
    chosen: list[CardInstance] = []
    for name in names:
        found = next(
            (a for a in attackers if matches(deck, a, name) and all(a.id != c.id for c in chosen)),
            None,
        )
        if found is None:
            return Error(ErrorKind.NOT_AN_ATTACKER, subject=name)
        chosen.append(found)
    return chosen


def _damage(
    deck: LoadedDeck, attackers: Sequence[CardInstance], value: object
) -> dict[str, int] | Error:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="damage")
    damage: dict[str, int] = {}
    for name, amount in value.items():
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            return Error(ErrorKind.MALFORMED_ARGUMENT, subject="damage")
        found = _among(deck, attackers, [str(name)])
        if isinstance(found, Error):
            return found
        damage[found[0].id] = amount
    return damage


def _targets(
    deck: LoadedDeck, attackers: Sequence[CardInstance], value: object
) -> dict[str, int] | Error:
    commanders = [a for a in attackers if a.is_commander]

    def valid(target: object) -> bool:
        return isinstance(target, int) and not isinstance(target, bool) and 0 <= target < OPPONENTS

    if value is None:
        return {c.id: 0 for c in commanders}
    if isinstance(value, Mapping):
        targets = {c.id: 0 for c in commanders}
        for name, target in value.items():
            found = next((c for c in commanders if matches(deck, c, str(name))), None)
            if found is None or not valid(target):
                return Error(ErrorKind.BAD_COMMANDER_TARGET, subject=str(name))
            targets[found.id] = int(target)
        return targets
    if not valid(value):
        return Error(ErrorKind.BAD_COMMANDER_TARGET, subject=str(value))
    return {c.id: int(value) for c in commanders}  # type: ignore[call-overload]


# @spec CMBT-001, CMBT-002, CMBT-003, CMBT-004, CMBT-005, CMBT-006, CMBT-007, CMBT-008, CMBT-009
# @spec CMBT-010, CMBT-011, CMBT-012, CMBT-013, CMBT-014, CMBT-015, CMBT-016, CMBT-017
# @spec CMBT-018, CMBT-019, CMBT-020, CMBT-021, GAME-015, GAME-016, GAME-018
def attack(
    game: Game,
    deck: LoadedDeck,
    *,
    attackers: object,
    blocked: object = None,
    commander_target: object = None,
    damage: object = None,
    vigilance: object = None,
    haste: object = None,
    override: str | None = None,
) -> Result:
    """Declare an attack, moving to declare attackers first when the game is before it."""
    lists: dict[str, list[str]] = {}
    for argument, value in (
        ("attackers", attackers),
        ("blocked", blocked),
        ("vigilance", vigilance),
        ("haste", haste),
    ):
        names = _names(value, argument)
        if isinstance(names, Error):
            return Refusal.error(names)
        lists[argument] = names
    problems = Problems()
    step = game.step
    if step in _EARLY:
        problems.add(FailedCheck(CheckKind.ATTACK_TOO_EARLY, step=step))
    elif step not in _BEFORE_COMBAT + _DECLARING:
        problems.add(FailedCheck(CheckKind.COMBAT_OVER, step=step))
    changed = game.copy()
    walk = Walk()
    if step in _EARLY or step in _BEFORE_COMBAT:
        walk_to(changed, deck, Step.DECLARE_ATTACKERS, walk)
    elif step not in _DECLARING:
        return_to_declare_attackers(changed, deck, walk)
    tapped_before = set(changed.tapped_by_attacks)
    found = resolve(changed, deck, lists["attackers"], [Zone.BATTLEFIELD], Purpose.TAP)
    if isinstance(found, Error):
        return Refusal.error(_attacker_error(found))
    chosen, instances_chosen = found
    sub: dict[str, list[CardInstance]] = {}
    for argument in ("blocked", "vigilance", "haste"):
        among = _among(deck, chosen, lists[argument])
        if isinstance(among, Error):
            return Refusal.error(among)
        sub[argument] = among
    damage_by_id = _damage(deck, chosen, damage)
    if isinstance(damage_by_id, Error):
        return Refusal.error(damage_by_id)
    targets = _targets(deck, chosen, commander_target)
    if isinstance(targets, Error):
        return Refusal.error(targets)
    blocked_ids = {c.id for c in sub["blocked"]}
    hasty = {c.id for c in sub["haste"]}
    for card in chosen:
        name = face_name(deck, card)
        if not is_creature(deck, card):
            problems.add(FailedCheck(CheckKind.NOT_A_CREATURE, subject=name))
        if card.tapped and card.id not in tapped_before:
            problems.add(FailedCheck(CheckKind.ATTACKER_TAPPED, subject=name))
        if (
            card.entered_turn == changed.turn
            and card.id not in hasty
            and not has_haste(changed, deck, card)
        ):
            problems.add(FailedCheck(CheckKind.SUMMONING_SICK_ATTACKER, subject=name))
        if (
            is_creature(deck, card)
            and card.id not in blocked_ids
            and card.id not in damage_by_id
            and numeric_power(deck, card) is None
        ):
            problems.add(FailedCheck(CheckKind.POWER_NOT_A_NUMBER, subject=name))
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    watchful = {c.id for c in sub["vigilance"]}
    newly_tapped = []
    for card in chosen:
        if card.id in watchful or has_vigilance(changed, deck, card) or card.tapped:
            continue
        card.tapped = True
        newly_tapped.append(card)
    changed.declared_attack = (
        Attack(
            attackers=[c.id for c in chosen],
            blocked=sorted(blocked_ids, key=lambda i: int(i[1:])),
            damage=damage_by_id,
            commander_targets=targets,
        )
        if chosen
        else None
    )
    changed.tapped_by_attacks.extend(c.id for c in newly_tapped)
    events: list[Event] = []
    if walk.entered:
        events.append(walk.summary)
    if judged is not None:
        events.append(judged)
    events.extend(walk.events)
    events.extend(instances_chosen)
    summary = AttackDeclared(
        attackers=tuple(face_name(deck, c) for c in chosen),
        blocked=tuple(face_name(deck, c) for c in sub["blocked"]),
        commander_targets=tuple(
            (face_name(deck, c), targets[c.id]) for c in chosen if c.id in targets
        ),
        tapped=tuple(face_name(deck, c) for c in newly_tapped),
    )
    return Applied(changed, summary, tuple(events), tuple(walk.snapshots))
