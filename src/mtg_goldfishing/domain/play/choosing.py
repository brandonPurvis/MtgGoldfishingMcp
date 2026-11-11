"""`choose`: answer the pending choice the game waits on.

A look or a search is finished by saying where each revealed card goes; a look at another
seat's hand by saying which of its cards go where; an `ask` by the answering seat's own
delta, applied at once; blocks by naming each blocker and the attacker it blocks. Each kind
is answered with its own arguments only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AskAnswered,
    BlockDeclared,
    BlocksDeclared,
    CardMoved,
    CheckKind,
    ChecksOverridden,
    ChoiceResolved,
    Error,
    ErrorKind,
    Event,
    FailedCheck,
    Placement,
)
from mtg_goldfishing.domain.game.cards_in_play import face_name, is_creature
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.elimination import check_eliminations
from mtg_goldfishing.domain.game.model import (
    CardInstance,
    Destination,
    Game,
    GameStatus,
    PendingChoice,
    Zone,
)
from mtg_goldfishing.domain.game.naming import matches, resolve
from mtg_goldfishing.domain.game.notices import examine_end_conditions
from mtg_goldfishing.domain.game.results import Applied, Problems, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.play.arguments import (
    Delta,
    read_blocks,
    read_delta,
    read_rest_order,
    read_selections,
)
from mtg_goldfishing.domain.play.delta import apply_delta, place_all, take_shuffle_place
from mtg_goldfishing.domain.play.settling import settle

ANSWERED_WITH: dict[str, tuple[str, ...]] = {
    "look": ("selections", "rest_order"),
    "search": ("selections",),
    "hand": ("selections", "delta"),
    "ask": ("delta",),
    "blocks": ("blocks",),
}
"""The arguments each kind of pending choice is answered with."""


def _among(
    decks: Decks,
    candidates: Sequence[CardInstance],
    names: Sequence[str],
    taken: list[CardInstance],
) -> list[CardInstance] | Error:
    """Resolve names among revealed cards, each to a different card, in reveal order; each
    card's names are read from its owner's deck."""
    found: list[CardInstance] = []
    for name in names:
        matching = [card for card in candidates if matches(decks.of(card.owner), card, name)]
        if not matching:
            return Error(ErrorKind.NOT_REVEALED, subject=name)
        free = [card for card in matching if all(card.id != t.id for t in taken)]
        if not free:
            return Error(
                ErrorKind.TOO_FEW_MATCHING,
                subject=name,
                number=len(matching),
                expected=sum(1 for n in names if n.strip().casefold() == name.strip().casefold()),
            )
        taken.append(free[0])
        found.append(free[0])
    return found


def _placements(events: Sequence[Event]) -> tuple[Placement, ...]:
    """Where each revealed card went; in a contested game also whose it is and where from."""
    return tuple(
        Placement(e.card, e.to)
        if e.owner is None
        else Placement(e.card, e.to, e.owner, e.from_zone)
        for e in events
        if isinstance(e, CardMoved)
    )


def _shown(events: Sequence[Event]) -> list[Event]:
    """What a placement reports besides the placements: commanders redirected."""
    return [e for e in events if not isinstance(e, CardMoved) or e.commander_redirected]


Selected = list[tuple[Destination, list[CardInstance]]]


def _selected(
    decks: Decks, revealed: Sequence[CardInstance], selections: object
) -> tuple[Selected, list[CardInstance]] | Error:
    """The revealed cards selected to each destination, and those left unselected."""
    chosen = read_selections(selections)
    if isinstance(chosen, Error):
        return chosen
    taken: list[CardInstance] = []
    selected: Selected = []
    for destination, names in chosen:
        found = _among(decks, revealed, names, taken)
        if isinstance(found, Error):
            return found
        selected.append((destination, found))
    return selected, [card for card in revealed if all(card.id != t.id for t in taken)]


# @spec PLAY-062, PLAY-063, PLAY-064, PLAY-065, PLAY-067
def _answer_look(
    changed: Game, decks: Decks, pending: PendingChoice, selections: object, rest_order: object
) -> Applied | Error:
    deck = decks.of(pending.seat)
    revealed = [changed.instance(instance_id) for instance_id in pending.revealed]
    picked = _selected(decks, revealed, selections)
    if isinstance(picked, Error):
        return picked
    selected, unselected = picked
    events: list[Event] = []
    if pending.rest is None:
        events.extend(take_shuffle_place(changed, deck, pending.seat, selected))
    else:
        order = read_rest_order(rest_order)
        if isinstance(order, Error):
            return order
        ordered = _among(decks, unselected, order, [])
        if isinstance(ordered, Error):
            return ordered
        named = {card.id for card in ordered}
        unnamed = [card for card in unselected if card.id not in named]
        if pending.from_bottom and pending.rest is Destination.LIBRARY_BOTTOM:
            unnamed.reverse()
        events.extend(place_all(changed, deck, ordered + unnamed, pending.rest))
        for destination, cards in selected:
            events.extend(place_all(changed, deck, cards, destination))
    return Applied(changed, ChoiceResolved(_placements(events)), tuple(_shown(events)))


def _controllers(
    decks: Decks, delta: Delta, onto_battlefield: Sequence[CardInstance]
) -> dict[str, SeatNumber] | Error:
    """The seat each card selected to the battlefield enters under, by a hand answer's
    `control`; the delta may hold nothing else and name no other card."""
    alone = Delta(control=delta.control)
    others = [f.name for f in fields(Delta) if getattr(delta, f.name) != getattr(alone, f.name)]
    if others:
        return Error(ErrorKind.HAND_ANSWER_DELTA, subject=others[0])
    controllers: dict[str, SeatNumber] = {}
    for seat, names in delta.control:
        for name in names:
            found = next(
                (
                    card
                    for card in onto_battlefield
                    if matches(decks.of(card.owner), card, name) and card.id not in controllers
                ),
                None,
            )
            if found is None:
                return Error(ErrorKind.HAND_ANSWER_DELTA, subject=name)
            controllers[found.id] = seat
    return controllers


# @spec PLAY-103, PLAY-111, PLAY-112, PLAY-113, GAME-155
def _answer_hand(
    changed: Game, decks: Decks, pending: PendingChoice, selections: object, delta: object
) -> Applied | Error:
    """Selected cards go to their owners' zones; a card put onto the battlefield enters under
    its owner unless the answer's `control` names another seat; the rest stay in the hand."""
    revealed = [changed.instance(instance_id) for instance_id in pending.revealed]
    picked = _selected(decks, revealed, selections)
    if isinstance(picked, Error):
        return picked
    selected, _ = picked
    read = read_delta(delta, contested=True)
    if isinstance(read, Error):
        return read
    onto = [
        card
        for destination, cards in selected
        if destination.zone is Zone.BATTLEFIELD
        for card in cards
    ]
    controllers = _controllers(decks, read, onto)
    if isinstance(controllers, Error):
        return controllers
    events: list[Event] = []
    for destination, cards in selected:
        for card in cards:
            events.extend(
                place_all(
                    changed,
                    decks.of(card.owner),
                    [card],
                    destination,
                    decks=decks,
                    arriving_under=controllers.get(card.id),
                )
            )
    return Applied(changed, ChoiceResolved(_placements(events)), tuple(_shown(events)))


# @spec PLAY-099, PLAY-100, PLAY-101, PLAY-121, PLAY-122
def _answer_ask(
    changed: Game, decks: Decks, seat: SeatNumber, pending: PendingChoice, delta: object
) -> Applied | Error:
    """The answering seat's own delta, applied at once as that seat's; it may not create a
    pending choice, and is never judged against what was asked."""
    read = read_delta(delta, contested=True)
    if isinstance(read, Error):
        return read
    if read.creates_choices:
        return Error(ErrorKind.ANSWER_MAY_NOT_REVEAL, subject=read.creates_choices[0])
    applied = apply_delta(changed, decks.of(seat), seat, read, source=pending.source, decks=decks)
    if isinstance(applied, Error):
        return applied
    return Applied(changed, AskAnswered(pending.choice_id, seat), tuple(applied))


def _blocker_error(error: Error) -> Error:
    if error.kind is ErrorKind.CARD_NOT_IN_ZONE:
        return Error(ErrorKind.NOT_YOUR_BLOCKER, subject=error.subject)
    return error


# @spec CMBT-039, CMBT-040, CMBT-041, CMBT-042, CMBT-043, CMBT-044, CMBT-045, CMBT-046
# @spec CMBT-049
def _answer_blocks(
    changed: Game,
    decks: Decks,
    seat: SeatNumber,
    pending: PendingChoice,
    blocks: object,
    *,
    override: str | None,
) -> Applied | Refusal | Error:
    """Each blocker, among the creatures the answering seat controls, blocks an attacker
    attacking that seat; several may block one attacker. A tapped blocker, or one that is
    not a creature, fails a rule check."""
    pairs = read_blocks(blocks)
    if isinstance(pairs, Error):
        return pairs
    found = resolve(
        changed,
        decks.of(seat),
        seat,
        [blocker for blocker, _ in pairs],
        [Zone.BATTLEFIELD],
        decks=decks,
        own_only=True,
    )
    if isinstance(found, Error):
        return _blocker_error(found)
    blockers = found[0]
    attackers = [changed.instance(instance_id) for instance_id in pending.attackers]
    problems = Problems()
    declared: list[tuple[CardInstance, CardInstance]] = []
    for blocker, (_, name) in zip(blockers, pairs, strict=True):
        attacker = next(
            (card for card in attackers if matches(decks.of(card.owner), card, name)), None
        )
        if attacker is None:
            return Error(ErrorKind.NOT_ATTACKING_YOU, subject=name)
        shown = face_name(decks.of(blocker.owner), blocker)
        if blocker.tapped:
            problems.add(FailedCheck(CheckKind.BLOCKER_TAPPED, subject=shown))
        if not is_creature(decks.of(blocker.owner), blocker):
            problems.add(FailedCheck(CheckKind.BLOCKER_NOT_A_CREATURE, subject=shown))
        declared.append((blocker, attacker))
    judged = problems.judge(override)
    if isinstance(judged, Refusal):
        return judged
    attack = changed.declared_attack
    if attack is not None:
        for blocker, attacker in declared:
            attack.blocks[blocker.id] = attacker.id
            if attacker.id not in attack.blocked:
                attack.blocked.append(attacker.id)
        attack.blocked.sort(key=lambda instance_id: int(instance_id[1:]))
    summary = BlocksDeclared(
        seat,
        tuple(
            BlockDeclared(
                face_name(decks.of(blocker.owner), blocker),
                face_name(decks.of(attacker.owner), attacker),
                blocker.id,
                attacker.id,
            )
            for blocker, attacker in declared
        ),
    )
    events: tuple[Event, ...] = (judged,) if isinstance(judged, ChecksOverridden) else ()
    return Applied(changed, summary, events)


# @spec PLAY-001, PLAY-051, PLAY-052, PLAY-066, PLAY-105, PLAY-106, PLAY-107, APP-031
# @spec CMBT-048, GAME-128
def choose(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    choice_id: object,
    selections: object = None,
    rest_order: object = None,
    delta: object = None,
    blocks: object = None,
    override: str | None = None,
    decks: Decks | None = None,
) -> Result:
    """Answer the oldest waiting pending choice, as the seat it is addressed to.

    A look's or search's selected cards are placed, a look's rest going to its destination;
    a hand's selected cards go to their owners' zones; an `ask` is answered with the
    answering seat's own delta; blocks are recorded on the declared attack. Then every seat
    is checked for elimination, a look at a hand that waited for answers opens, and the game
    waits on the next choice, if any. `decks` gives each seat's deck; omitted, every seat
    plays `deck`.
    """
    every = decks or Decks.everyone_playing(game, deck)
    pending = game.waiting_choice
    if (
        pending is None
        or pending.seat != seat
        or not isinstance(choice_id, str)
        or choice_id.strip() != pending.choice_id
    ):
        return Refusal.error(Error(ErrorKind.WRONG_CHOICE, subject=str(choice_id)))
    given = {
        "selections": selections,
        "rest_order": rest_order,
        "delta": delta,
        "blocks": blocks,
    }
    allowed = ANSWERED_WITH[pending.kind]
    wrong = next(
        (name for name, value in given.items() if value is not None and name not in allowed), None
    )
    if wrong is not None:
        return Refusal.error(
            Error(ErrorKind.WRONG_ANSWER, subject=wrong, zone=pending.kind, names=allowed)
        )

    changed = game.copy()
    answered: Applied | Refusal | Error
    match pending.kind:
        case "look" | "search":
            answered = _answer_look(changed, every, pending, selections, rest_order)
        case "hand":
            answered = _answer_hand(changed, every, pending, selections, delta)
        case "ask":
            answered = _answer_ask(changed, every, seat, pending, delta)
        case _:
            answered = _answer_blocks(changed, every, seat, pending, blocks, override=override)
    if isinstance(answered, Error):
        return Refusal.error(answered)
    if isinstance(answered, Refusal):
        return answered
    changed.pending.pop(0)
    changed.status = GameStatus.PENDING_CHOICE if changed.pending else GameStatus.ACTIVE
    reported = list(answered.events)
    reported.extend(examine_end_conditions(changed))
    reported.extend(check_eliminations(changed))
    walk = settle(changed, every)
    if walk.entered:
        reported.append(walk.summary)
    reported.extend(walk.events)
    return Applied(changed, answered.summary, tuple(reported), tuple(walk.snapshots))
