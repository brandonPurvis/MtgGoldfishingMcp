"""`attack`: declare attackers, and in a goldfish game which of them the imaginary opponents
block; in a contested game, which seat each attacker attacks, and, once blocks are known, the
trample damage each blocked attacker deals the seat it attacks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from mtg_goldfishing.domain.combat.damage import numeric_power
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AttackDeclared,
    AttackNotDeclared,
    CheckKind,
    Error,
    ErrorKind,
    Evasion,
    Event,
    FailedCheck,
    TrampleDamage,
    TrampleDamageStated,
)
from mtg_goldfishing.domain.game.cards_in_play import (
    face_name,
    has_haste,
    has_vigilance,
    is_creature,
)
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import (
    OPPONENTS,
    Attack,
    CardInstance,
    Game,
    WindowKind,
    Zone,
)
from mtg_goldfishing.domain.game.naming import Purpose, matches, resolve
from mtg_goldfishing.domain.game.results import Applied, Problems, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.stack.windows import go_on, open_window
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
    decks: Decks, attackers: Sequence[CardInstance], names: Sequence[str]
) -> list[CardInstance] | Error:
    """Resolve names to attackers; a name given twice means two different attackers."""
    chosen: list[CardInstance] = []
    for name in names:
        found = next(
            (
                a
                for a in attackers
                if matches(decks.of(a.owner), a, name) and all(a.id != c.id for c in chosen)
            ),
            None,
        )
        if found is None:
            return Error(ErrorKind.NOT_AN_ATTACKER, subject=name)
        chosen.append(found)
    return chosen


def _damage(
    decks: Decks, attackers: Sequence[CardInstance], value: object
) -> dict[str, int] | Error:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="damage")
    damage: dict[str, int] = {}
    for name, amount in value.items():
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            return Error(ErrorKind.MALFORMED_ARGUMENT, subject="damage")
        found = _among(decks, attackers, [str(name)])
        if isinstance(found, Error):
            return found
        damage[found[0].id] = amount
    return damage


def _target_seat(game: Game, seat: SeatNumber, value: object) -> SeatNumber | Error:
    """A seat an attacker attacks: another seat of the game, still in it."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="targets")
    target = SeatNumber(value)
    if target == seat:
        return Error(ErrorKind.TARGET_IS_YOU)
    if target not in {other.number for other in game.seats}:
        return Error(ErrorKind.NO_SUCH_SEAT, number=value)
    if not game.seat(target).in_game:
        return Error(ErrorKind.SEAT_OUT, number=value)
    return target


# @spec CMBT-030, CMBT-031, CMBT-032, CMBT-057, CMBT-058, CMBT-059, CMBT-076
def _seat_targets(
    game: Game, decks: Decks, seat: SeatNumber, attackers: Sequence[CardInstance], value: object
) -> dict[str, SeatNumber] | Error:
    """The seat each attacker attacks: one seat number for all, or a map from attacker to
    seat number; an attacker given none attacks the only opponent left, when there is one."""
    opponents = [other.number for other in game.seats if other.number != seat and other.in_game]
    if attackers and not opponents:
        return Error(ErrorKind.NO_OPPONENT_LEFT)
    targets: dict[str, SeatNumber] = {}
    if isinstance(value, Mapping):
        for name, number in value.items():
            found = _among(decks, attackers, [str(name)])
            if isinstance(found, Error):
                return found
            target = _target_seat(game, seat, number)
            if isinstance(target, Error):
                return target
            targets[found[0].id] = target
    elif value is not None:
        target = _target_seat(game, seat, value)
        if isinstance(target, Error):
            return target
        targets = {card.id: target for card in attackers}
    for card in attackers:
        if card.id in targets:
            continue
        if len(opponents) != 1:
            return Error(ErrorKind.NO_TARGET, subject=face_name(decks.of(card.owner), card))
        targets[card.id] = opponents[0]
    return targets


# @spec CMBT-054, CMBT-055, CMBT-056, CMBT-069, CMBT-072, CMBT-095
def _misplaced(
    game: Game, *, blocked: object, commander_target: object, targets: object, evasion: object
) -> Error | None:
    """What a game of the other kind takes, or an attack at a moment that has no meaning:
    a second declaration in one combat, or one after blockers are being declared."""
    if not game.contested:
        if targets is not None:
            return Error(ErrorKind.CONTESTED_ONLY, subject="targets")
        if evasion is not None:
            return Error(ErrorKind.CONTESTED_ONLY, subject="evasion")
        return None
    if blocked is not None:
        return Error(ErrorKind.GOLDFISH_ONLY, subject="blocked")
    if commander_target is not None:
        return Error(ErrorKind.GOLDFISH_ONLY, subject="commander_target")
    if game.step is Step.DECLARE_BLOCKERS:
        return Error(ErrorKind.ATTACK_AFTER_BLOCKERS)
    if game.declared_attack is not None:
        return Error(ErrorKind.ATTACK_DECLARED)
    return None


_EVASIONS = {evasion.value: evasion for evasion in Evasion}


def _evasions(value: object) -> list[Evasion] | None:
    """One evasion, or a non-empty list of distinct ones, as `evasion` names them."""
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names or len(set(map(str, names))) != len(names):
        return None
    found = [_EVASIONS.get(name) if isinstance(name, str) else None for name in names]
    return [evasion for evasion in found if evasion is not None] if all(found) else None


# @spec CMBT-080, CMBT-093, CMBT-094
def _evasion(
    decks: Decks, attackers: Sequence[CardInstance], value: object
) -> dict[str, list[Evasion]] | Error:
    """The evasion the attacking seat lists for each attacker, beyond what the game reads."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="evasion")
    listed: dict[str, list[Evasion]] = {}
    for name, given in value.items():
        evasions = _evasions(given)
        if evasions is None:
            return Error(ErrorKind.MALFORMED_ARGUMENT, subject="evasion")
        found = _among(decks, attackers, [str(name)])
        if isinstance(found, Error):
            return found
        listed[found[0].id] = evasions
    return listed


_DECLARATION = ("attackers", "targets", "damage", "vigilance", "haste", "evasion")
"""The arguments of a declaration, none of which an `attack` stating trample damage takes."""


def _trample_entries(
    game: Game, decks: Decks, value: object
) -> list[tuple[CardInstance, int]] | Error:
    """Each attacker of the declared attack a `trample` map names, with its amount."""
    attack = game.declared_attack
    assert attack is not None
    if not isinstance(value, Mapping):
        return Error(ErrorKind.MALFORMED_ARGUMENT, subject="trample")
    attackers = [card for card in map(game.find, attack.attackers) if card is not None]
    entries: list[tuple[CardInstance, int]] = []
    for name, amount in value.items():
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            return Error(ErrorKind.MALFORMED_ARGUMENT, subject="trample")
        found = _among(decks, attackers, [str(name)])
        if isinstance(found, Error):
            return found
        card = found[0]
        if card.id not in attack.blocked:
            return Error(ErrorKind.NOT_BLOCKED, subject=face_name(decks.of(card.owner), card))
        entries.append((card, amount))
    return entries


# @spec CMBT-069, CMBT-072, CMBT-098, CMBT-099, CMBT-100, CMBT-101, CMBT-102, CMBT-103
# @spec CMBT-104, CMBT-105, CMBT-106, CMBT-107, CMBT-108
def _state_trample(
    game: Game, decks: Decks, trample: object, given: Mapping[str, object]
) -> Result:
    """The attacking seat states the trample damage of blocked attackers, once every blocks
    choice of the combat is answered: each entry replaces that attacker's earlier statement,
    and 0 takes it back. Nothing is declared or tapped, no window opens and the game stays in
    declare blockers. The amounts are not checked against power, toughness or readings."""
    if not game.contested:
        return Refusal.error(Error(ErrorKind.CONTESTED_ONLY, subject="trample"))
    alongside = next((name for name in _DECLARATION if given.get(name) is not None), None)
    if alongside is not None:
        return Refusal.error(Error(ErrorKind.TRAMPLE_ALONE, subject=alongside))
    for name in ("blocked", "commander_target"):
        if given.get(name) is not None:
            return Refusal.error(Error(ErrorKind.GOLDFISH_ONLY, subject=name))
    attack = game.declared_attack
    if (
        game.step is not Step.DECLARE_BLOCKERS
        or attack is None
        or any(choice.kind == "blocks" for choice in game.pending)
    ):
        return Refusal.error(Error(ErrorKind.TRAMPLE_NOT_NOW))
    entries = _trample_entries(game, decks, trample)
    if isinstance(entries, Error):
        return Refusal.error(entries)
    changed = game.copy()
    stated = changed.declared_attack
    assert stated is not None
    for card, amount in entries:
        if amount:
            stated.trample[card.id] = amount
        else:
            stated.trample.pop(card.id, None)
    summary = TrampleDamageStated(
        tuple(
            TrampleDamage(
                face_name(decks.of(card.owner), card),
                card.id,
                amount,
                SeatNumber(stated.targets[card.id]),
            )
            for card, amount in entries
        )
    )
    return Applied(changed, summary, ())


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


# @spec CMBT-073, CMBT-078
def _not_declared(
    changed: Game, walk: Walk, problems: Problems, override: str | None
) -> Applied | Refusal:
    """An attack that stopped on its way to declare attackers, where a seat other than the
    active seat is reminded: nothing is declared or tapped, unless the move itself fails a
    timing check that is not overridden."""
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    events: list[Event] = [walk.summary]
    if judged is not None:
        events.append(judged)
    events.extend(walk.events)
    assert changed.step is not None
    return Applied(changed, AttackNotDeclared(changed.step), tuple(events), tuple(walk.snapshots))


# @spec CMBT-001, CMBT-002, CMBT-003, CMBT-004, CMBT-005, CMBT-006, CMBT-007, CMBT-008, CMBT-009
# @spec CMBT-010, CMBT-011, CMBT-012, CMBT-013, CMBT-014, CMBT-015, CMBT-016, CMBT-017
# @spec CMBT-018, CMBT-019, CMBT-020, CMBT-021, GAME-015, GAME-016, GAME-018, APP-031
# @spec CMBT-053, CMBT-060, CMBT-068, CMBT-070, CMBT-071, STACK-036
# @spec CMBT-079, CMBT-080, CMBT-096
def attack(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    attackers: object = None,
    blocked: object = None,
    commander_target: object = None,
    damage: object = None,
    vigilance: object = None,
    haste: object = None,
    override: str | None = None,
    targets: object = None,
    decks: Decks | None = None,
    evasion: object = None,
    trample: object = None,
) -> Result:
    """The active seat declares an attack, moving to declare attackers first when the game
    is before it. In a contested game each attacker attacks a seat, and a seat attacks only
    with creatures it controls, once each combat; once blocks are known, an `attack` giving
    `trample` alone states blocked attackers' trample damage instead. `decks` gives each
    seat's deck; omitted, every seat plays `deck`."""
    every = decks or Decks.everyone_playing(game, deck)
    if trample is not None:
        given = {
            "attackers": attackers,
            "targets": targets,
            "damage": damage,
            "vigilance": vigilance,
            "haste": haste,
            "evasion": evasion,
            "blocked": blocked,
            "commander_target": commander_target,
        }
        return _state_trample(game, every, trample, given)
    if attackers is None:
        return Refusal.error(Error(ErrorKind.ATTACKERS_NEEDED))
    misplaced = _misplaced(
        game,
        blocked=blocked,
        commander_target=commander_target,
        targets=targets,
        evasion=evasion,
    )
    if misplaced is not None:
        return Refusal.error(misplaced)
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
        reached = walk_to(changed, every, Step.DECLARE_ATTACKERS, walk)
        if not reached:
            return _not_declared(changed, walk, problems, override)
    elif step not in _DECLARING:
        return_to_declare_attackers(changed, deck, walk, every)
    tapped_before = set(changed.tapped_by_attacks)
    found = resolve(
        changed,
        deck,
        seat,
        lists["attackers"],
        [Zone.BATTLEFIELD],
        purpose=Purpose.TAP,
        decks=every,
    )

    if isinstance(found, Error):
        return Refusal.error(_attacker_error(found))
    chosen, instances_chosen = found

    def deck_of(card: CardInstance) -> LoadedDeck:
        return every.of(card.owner)

    not_controlled = next((c for c in chosen if c.controller != seat), None)
    if not_controlled is not None:
        return Refusal.error(
            Error(
                ErrorKind.NOT_YOUR_ATTACKER,
                subject=face_name(deck_of(not_controlled), not_controlled),
            )
        )
    sub: dict[str, list[CardInstance]] = {}
    for argument in ("blocked", "vigilance", "haste"):
        among = _among(every, chosen, lists[argument])
        if isinstance(among, Error):
            return Refusal.error(among)
        sub[argument] = among
    damage_by_id = _damage(every, chosen, damage)
    if isinstance(damage_by_id, Error):
        return Refusal.error(damage_by_id)
    evasion_by_id = _evasion(every, chosen, evasion)
    if isinstance(evasion_by_id, Error):
        return Refusal.error(evasion_by_id)
    commander_targets: dict[str, int] = {}
    seat_targets: dict[str, SeatNumber] = {}
    if changed.contested:
        aimed = _seat_targets(changed, every, seat, chosen, targets)
        if isinstance(aimed, Error):
            return Refusal.error(aimed)
        seat_targets = aimed
    else:
        aimed_at = _targets(deck, chosen, commander_target)
        if isinstance(aimed_at, Error):
            return Refusal.error(aimed_at)
        commander_targets = aimed_at
    blocked_ids = {c.id for c in sub["blocked"]}
    hasty = {c.id for c in sub["haste"]}
    for card in chosen:
        name = face_name(deck_of(card), card)
        if not is_creature(deck_of(card), card):
            problems.add(FailedCheck(CheckKind.NOT_A_CREATURE, subject=name))
        if card.tapped and card.id not in tapped_before:
            problems.add(FailedCheck(CheckKind.ATTACKER_TAPPED, subject=name))
        if (
            card.entered_turn == changed.turn
            and card.id not in hasty
            and not has_haste(changed, deck_of(card), card, every)
        ):
            problems.add(FailedCheck(CheckKind.SUMMONING_SICK_ATTACKER, subject=name))
        if (
            is_creature(deck_of(card), card)
            and card.id not in blocked_ids
            and card.id not in damage_by_id
            and numeric_power(deck_of(card), card) is None
        ):
            problems.add(FailedCheck(CheckKind.POWER_NOT_A_NUMBER, subject=name))
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    watchful = {c.id for c in sub["vigilance"]}
    newly_tapped = []
    for card in chosen:
        if card.id in watchful or has_vigilance(changed, deck_of(card), card, every) or card.tapped:
            continue
        card.tapped = True
        newly_tapped.append(card)
    changed.declared_attack = (
        Attack(
            attackers=[c.id for c in chosen],
            blocked=sorted(blocked_ids, key=lambda i: int(i[1:])),
            damage=damage_by_id,
            commander_targets=commander_targets,
            targets={card_id: target.value for card_id, target in seat_targets.items()},
            evasion=evasion_by_id,
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
    if changed.contested and chosen:
        open_window(changed, WindowKind.ATTACK)
        events.extend(go_on(changed, every))
    summary = AttackDeclared(
        attackers=tuple(face_name(deck_of(c), c) for c in chosen),
        blocked=tuple(face_name(deck_of(c), c) for c in sub["blocked"]),
        commander_targets=tuple(
            (face_name(deck_of(c), c), commander_targets[c.id])
            for c in chosen
            if c.id in commander_targets
        ),
        tapped=tuple(face_name(deck_of(c), c) for c in newly_tapped),
        targets=tuple(
            (face_name(deck_of(c), c), seat_targets[c.id]) for c in chosen if c.id in seat_targets
        ),
        evasion=tuple(
            (face_name(deck_of(c), c), tuple(evasion_by_id[c.id]))
            for c in chosen
            if c.id in evasion_by_id
        ),
    )
    return Applied(changed, summary, tuple(events), tuple(walk.snapshots))
