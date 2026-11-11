"""The renderer: the one place response text is made, from a use case's outcome.

A text response is

    <digest lines, in a contested game>
    <STATUS> <one-line summary>
    <event lines, in a fixed order>
    <status line, for a response about an existing game>

In a contested game the response begins with one digest line for each change other seats
made since the calling seat's previous response, the event lines begin by saying what the
calling seat is asked to do when it is a seat to act, and the status line is the calling
seat's.

Each event type has one rendering here, and each kind of error and rule check one
wording in `refusal_lines`; no other code in the service builds response text.
"""

from __future__ import annotations

import json
from typing import assert_never

from mtg_goldfishing.adapters.mcp.listing_lines import (
    EVASION_WORDS,
    attackers_to_block,
    report_lines,
    state_lines,
)
from mtg_goldfishing.adapters.mcp.refusal_lines import (
    asked_to,
    check_text,
    error_text,
    refusal_lines,
    seats_asked,
)
from mtg_goldfishing.application.outcome import DigestElement, Outcome, Status
from mtg_goldfishing.application.ports import Rendered, Renderer
from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    AlreadyApplied,
    AlreadySo,
    AlreadySoKind,
    AskAnswered,
    AskedKind,
    AssumptionKind,
    AssumptionMade,
    AttackDeclared,
    AttackNotDeclared,
    AutomaticPass,
    BlocksDeclared,
    BlocksRequested,
    CardMoved,
    CardPlayed,
    CardsDiscarded,
    CardsDrawn,
    CardsRevealed,
    CastTriggerApplied,
    ChecksOverridden,
    ChoiceAsked,
    ChoiceResolved,
    ChoiceRevealedTo,
    CombatDamageDealt,
    CombatDamageToSeats,
    ContestedGameStarted,
    ControlChanged,
    CostPaid,
    CountersChanged,
    DamageAdded,
    DeckLoaded,
    EffectRecorded,
    EliminationCause,
    Event,
    ExpectationMismatched,
    GameEnded,
    GameHasEnded,
    GameStarted,
    HandKept,
    HiddenCardsDrawn,
    HiddenCardsMoved,
    HiddenHandKept,
    HiddenMulliganTaken,
    InstanceChosen,
    ItemCountered,
    ItemRemoved,
    ItemResolved,
    ItemStacked,
    LibraryShuffled,
    LifeChanged,
    LogExported,
    ManaAdded,
    MulliganTaken,
    NoBlocksDeclared,
    NothingRevealed,
    NoticeKind,
    NoticeRaised,
    Passed,
    Refused,
    ReminderIssued,
    ResolveAsked,
    RevealedCard,
    SeatDamaged,
    SeatEliminated,
    SeatOut,
    SeatToAct,
    SnapshotWritten,
    StateListed,
    StepsEntered,
    StillWaiting,
    StopReason,
    Tapped,
    TokensCreated,
    TrampleDamageStated,
    Untapped,
)
from mtg_goldfishing.domain.game.listing import StateListing
from mtg_goldfishing.domain.game.model import (
    COMMANDER_DAMAGE_TO_WIN,
    DAMAGE_TO_WIN,
    MAXIMUM_HAND,
    GameStatus,
)
from mtg_goldfishing.domain.game.mulligan import cards_to_bottom
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.summary import GameSummary, TableSummary
from mtg_goldfishing.domain.steps import Step

GET_LOG = "get_log"
NEW_GAME = "new_game"
"""A contested game's `new_game` answers whoever starts the game, who is asked nothing."""


class TextRenderer(Renderer):
    """Implements the `Renderer` port with the plain-text response format."""

    # @spec TOOL-014, TOOL-015, TOOL-016, TOOL-022, TOOL-024, TOOL-025, TOOL-026, REC-018, REC-024
    # @spec TOOL-040, TOOL-051, TOOL-056, TOOL-086
    def render(self, tool: str, outcome: Outcome) -> Rendered:
        summary = outcome.summary
        if tool == GET_LOG and outcome.status is Status.OK and isinstance(summary, LogExported):
            export = json.dumps(outcome.payload)
            note = (
                f"get_log export: {len(export)} characters, {summary.entries} entries,"
                f" {summary.snapshots} snapshots, {summary.calls} calls"
            )
            return Rendered(export, note)
        text = "\n".join(response_lines(tool, outcome))
        return Rendered(text, text)


# @spec TOOL-035, TOOL-038, TOOL-039
def response_lines(tool: str, outcome: Outcome) -> list[str]:
    """Digest lines, status and summary, the summary's own detail, event lines, then the
    status line."""
    headline, *detail = summary_lines(outcome.summary, tool)
    lines = [digest_line(element) for element in outcome.digest or ()]
    lines.extend([f"{outcome.status.value} {headline}", *detail])
    if (
        outcome.game is not None
        and outcome.status is not Status.ERROR
        and tool != NEW_GAME
        and not isinstance(outcome.summary, SeatToAct)
    ):
        lines.extend(asked_lines(outcome.game))
    if isinstance(outcome.payload, StateListing):
        lines.extend(state_lines(outcome.payload))
    raised: list[tuple[NoticeKind, SeatNumber | None]] = []
    after = outcome.game.change if outcome.game else None
    for event in sorted(outcome.events, key=_place_in_order):
        if isinstance(event, NoticeRaised):
            raised.append((event.notice, event.seat))
        else:
            lines.extend(event_lines(event, tool, after))
    standing: list[tuple[NoticeKind, SeatNumber | None]] = []
    if outcome.game is not None:
        standing.extend((notice, None) for notice in outcome.game.notices)
        standing.extend(outcome.game.seat_notices)
    notices = list(dict.fromkeys((*raised, *standing)))
    lines.extend(notice_line(notice, seat) for notice, seat in notices)
    if outcome.game is not None:
        lines.append(status_line(outcome.game))
    return lines


def summary_lines(summary: Event, tool: str | None = None) -> list[str]:
    """The headline (first) and any lines that belong with it, such as a deck report."""
    lines = event_lines(summary, tool)
    return lines or ["Done."]


# ------------------------------------------------------------------------- the digest


# @spec TOOL-036, TOOL-037, TOOL-057, TOOL-064, TOOL-065
def digest_line(element: DigestElement) -> str:
    """One change another seat made: `S<seat> #<change>: ` and everything the change caused,
    as the outcome holds it, separated by `;`. Every seat is named by its number."""
    texts = [text for event in element.events for text in digest_texts(event)]
    return f"{element.seat} #{element.change}: " + "; ".join(texts)


def digest_texts(event: Event) -> list[str]:
    """An event as a digest line shows it: as its event line, without its closing stop,
    with the seat it concerns named where an event line would leave it to the reader."""
    match event:
        case CardsDrawn(seat=seat) if seat is not None:
            drawn = _listed(event.cards) if event.cards else "no cards"
            return [f"{seat} drew {drawn}"]
        case AdvanceStopped():
            return [f"stopped at {event.step.value} ({event.reason.value})"]
        case NoticeRaised():
            return [notice_line(event.notice, event.seat).removeprefix("Notice: ")]
        case _:
            return [line.rstrip(".") for line in event_lines(event)]


# ------------------------------------------------------------------------- the status line


# @spec TOOL-040, TOOL-061
def asked_lines(game: GameSummary) -> list[str]:
    """In a contested game, what the calling seat is asked to do, when it is a seat to act;
    asked about a stack item, its source and controller too."""
    table = game.table
    if table is None or table.asked is None or table.seat not in table.asked.seats:
        return []
    asked = table.asked
    about = ""
    if asked.kind is AskedKind.RESPOND and asked.item is not None:
        about = f": {asked.source} from {asked.controller}"
    return [f"You are asked to {asked_to(asked, yourself=True)}{about}."]


# @spec TOOL-017, TOOL-018, TOOL-019, TOOL-020, TOOL-021
def status_line(game: GameSummary) -> str:
    if game.table is not None:
        return contested_status_line(game, game.table)
    if game.step is None:
        line = f"Mulligan {game.mulligans} · Hand {game.hand} · #{game.change}"
    else:
        parts = [
            f"T{game.turn} {game.step.value}",
            f"Hand {game.hand}",
            f"Lands {game.lands} ({game.untapped_lands} untapped)",
            f"Pool {game.pool}",
            f"Life {game.life}",
            f"Dmg {game.damage_dealt}/{DAMAGE_TO_WIN}",
        ]
        commanders = sorted(game.commanders, key=lambda commander: commander.name)
        if commanders:
            damage = "|".join("/".join(str(n) for n in c.damage) for c in commanders)
            parts.append(f"Cmdr {damage}")
            parts.append(f"Tax {'|'.join(str(c.tax) for c in commanders)}")
        parts.append(f"#{game.change}")
        line = " · ".join(parts)
    if game.status is GameStatus.ENDED:
        line = f"Ended ({game.result}) · {line}"
    if game.status is GameStatus.PENDING_CHOICE:
        line += " · CHOICE pending"
    return line


def _commander_groups(game: GameSummary) -> list[str]:
    """`Cmdr` and `Tax`, a group per commander in name order separated by `|`."""
    commanders = sorted(game.commanders, key=lambda commander: commander.name)
    if not commanders:
        return []
    damage = "|".join("/".join(str(n) for n in c.damage) for c in commanders)
    return [f"Cmdr {damage}", f"Tax {'|'.join(str(c.tax) for c in commanders)}"]


def _act(table: TableSummary) -> str:
    """Who is to act, `you` for the calling seat, and the word for what it is asked."""
    asked = table.asked
    assert asked is not None
    who = " ".join("you" if seat == table.seat else str(seat) for seat in asked.seats)
    if asked.kind is AskedKind.KEEP:
        return f"Act {who}"
    word = asked.choice if asked.kind is AskedKind.CHOICE else asked.kind.value
    return f"Act {who} {word}"


def _standing(table: TableSummary) -> list[str]:
    """One `S<n> <life>` group per other seat, `out` for an eliminated one."""
    return [f"{o.seat} {'out' if o.eliminated else o.life}" for o in table.others]


# @spec TOOL-041, TOOL-042, TOOL-043, TOOL-044, TOOL-045, TOOL-047, TOOL-048, TOOL-049
# @spec TOOL-058, TOOL-059, TOOL-062
def contested_status_line(game: GameSummary, table: TableSummary) -> str:
    """The status line of a contested game as the calling seat sees it: its own figures,
    every other seat's life, and who is to act."""
    ended = game.status is GameStatus.ENDED
    if game.step is None:
        parts = [f"Mulligan {game.mulligans}", f"Hand {game.hand}"]
    else:
        active = f" ({table.active})" if table.active is not None else ""
        parts = [
            f"T{game.turn} {game.step.value}{active}",
            f"You {table.seat}",
            f"Hand {game.hand}",
            f"Lands {game.lands} ({game.untapped_lands} untapped)",
            f"Pool {game.pool}",
            f"Life {game.life}",
            *_standing(table),
            *_commander_groups(game),
        ]
        if table.stack and not ended:
            parts.append(f"Stack {table.stack}")
    if table.asked is not None and not ended:
        parts.append(_act(table))
    parts.append(f"#{game.change}")
    line = " · ".join(parts)
    if table.eliminated:
        line = f"Out · {line}"
    if ended:
        line = f"Ended ({game.result}) · {line}"
    return line


# ---------------------------------------------------------------------------- event order


def _place_in_order(event: Event) -> int:
    """Where an event's lines go among the event lines; events in one place keep their order."""
    match event:
        case AlreadyApplied():
            return 0
        case ChecksOverridden():
            return 1
        case StepsEntered():
            return 2
        case CostPaid():
            return 3
        case CastTriggerApplied():
            return 4
        case (
            CardMoved()
            | TokensCreated()
            | CardsDrawn()
            | CardsDiscarded()
            | Tapped()
            | Untapped()
            | ManaAdded()
            | CountersChanged()
            | LifeChanged()
            | SeatDamaged()
            | ControlChanged()
            | NoBlocksDeclared()
            | BlocksDeclared()
            | DamageAdded()
            | LibraryShuffled()
            | AlreadySo()
            | InstanceChosen()
            | ChoiceResolved()
            | AskAnswered()
            | AttackDeclared()
            | TrampleDamageStated()
            | SnapshotWritten()
            | DeckLoaded()
            | GameStarted()
            | ContestedGameStarted()
            | HiddenCardsDrawn()
            | HiddenCardsMoved()
            | MulliganTaken()
            | HiddenMulliganTaken()
            | HandKept()
            | HiddenHandKept()
            | CardPlayed()
            | EffectRecorded()
            | GameEnded()
            | StateListed()
            | LogExported()
            | Refused()
            | SeatToAct()
            | StillWaiting()
            | SeatOut()
            | GameHasEnded()
            | Passed()
            | AttackNotDeclared()
        ):
            return 5
        case (
            CardsRevealed()
            | ResolveAsked()
            | ChoiceRevealedTo()
            | ChoiceAsked()
            | BlocksRequested()
            | NothingRevealed()
        ):
            return 6
        case CombatDamageDealt() | CombatDamageToSeats():
            return 7
        case AssumptionMade():
            return 8
        case ReminderIssued():
            return 9
        case AdvanceStopped():
            return 10
        case ExpectationMismatched():
            return 11
        case ItemStacked():
            return 12
        case AutomaticPass():
            return 13
        case ItemResolved() | ItemCountered() | ItemRemoved():
            return 14
        case SeatEliminated():
            return 15
        case NoticeRaised():
            return 16
        case _:
            assert_never(event)


# --------------------------------------------------------------------- one rendering each


def _listed(names: tuple[str, ...]) -> str:
    return ", ".join(names)


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


_ZONE_NAMES = {
    "battlefield_tapped": "battlefield tapped",
    "library_top": "top of library",
    "library_bottom": "bottom of library",
    "command": "command zone",
    "outside": "outside the game",
}

_PLAYED_FROM = {
    "command": "the command zone",
    "outside": "outside the game",
}

_PLAYED_TO = {
    "hand": "the hand",
    "exile": "exile",
    "battlefield_tapped": "the battlefield tapped",
    "library_top": "the top of the library",
    "library_bottom": "the bottom of the library",
    "command": "the command zone",
}


def _zone(name: str) -> str:
    return _ZONE_NAMES.get(name, name)


def _steps(event: StepsEntered) -> list[str]:
    if not event.steps:
        return []
    named = [
        _untap(entered.turn, entered.seat) if entered.step is Step.UNTAP else entered.step.value
        for entered in event.steps
    ]
    return [" → ".join(named)]


def _untap(turn: int, seat: SeatNumber | None) -> str:
    """The untap that begins a turn: `T7 untap`, or in a contested game `S2 T7 untap`."""
    return (f"{seat} " if seat is not None else "") + f"T{turn} untap"


def _played(event: CardPlayed) -> str:
    verb = "Played" if event.is_land else "Cast"
    name = event.face if event.face == event.card else f"{event.face} ({event.card})"
    origin = (
        ""
        if event.from_zone == "hand"
        else " from " + _PLAYED_FROM.get(event.from_zone, f"the {event.from_zone}")
    )
    destination = f" to {_PLAYED_TO[event.to]}" if event.to in _PLAYED_TO else ""
    return f"{verb} {name}{origin}{destination}."


def _paid(event: CostPaid) -> str:
    cost = str(event.cost) or "{0}"
    if event.unpaid:
        return f"Not paid: {cost}, by override; nothing was tapped or spent."
    parts: list[str] = []
    if event.tapped:
        parts.append(f"tapped {_listed(event.tapped)}")
    if event.sacrificed:
        parts.append(f"sacrificed {_listed(event.sacrificed)}")
    if event.life:
        parts.append(f"paid {event.life} life")
    if event.from_pool:
        parts.append(f"used {event.from_pool} from the pool")
    if event.surplus:
        parts.append(f"{event.surplus} left in the pool")
    return f"Paid {cost}" + (f": {'; '.join(parts)}" if parts else "") + "."


def _moved(event: CardMoved) -> str:
    line = f"Moved {event.card}: {_zone(event.from_zone)} → {_zone(event.to)}"
    if event.commander_redirected:
        line += "; a commander goes to the command zone instead"
    if event.token_gone:
        line += "; the token ceased to exist"
    return line + "."


def _counters(event: CountersChanged) -> str:
    counters = _plural(abs(event.change), f"{event.kind} counter")
    if event.change >= 0:
        return f"Put {counters} on {event.card}; it has {event.now}."
    return f"Removed {counters} from {event.card}; it has {event.now}."


def _already_so(event: AlreadySo) -> str:
    match event.kind:
        case AlreadySoKind.ALREADY_TAPPED:
            return f"{event.card} was already tapped."
        case AlreadySoKind.ALREADY_UNTAPPED:
            return f"{event.card} was already untapped."
        case AlreadySoKind.COUNTER_AT_ZERO:
            return f"{event.card} had no {event.counter} counters to remove; it stays at 0."
        case AlreadySoKind.ALREADY_CONTROLLED:
            return f"{event.card} is already controlled by that seat."
        case _:
            assert_never(event.kind)


def _attacking_seats(targets: tuple[tuple[str, SeatNumber], ...]) -> str:
    """`S2 with Grizzly Bears; S3 with Shivan Dragon`: the attackers grouped by the seat they
    attack, the seats in the order first attacked."""
    by_seat: dict[SeatNumber, list[str]] = {}
    for attacker, seat in targets:
        by_seat.setdefault(seat, []).append(attacker)
    return "; ".join(f"{seat} with {', '.join(names)}" for seat, names in by_seat.items())


def _attack(event: AttackDeclared) -> str:
    if not event.attackers:
        return "Declared no attack."
    if event.targets:
        line = f"Attacking {_attacking_seats(event.targets)}."
    else:
        line = f"Attacking with {_listed(event.attackers)}."
    if event.blocked:
        line += f" Blocked: {_listed(event.blocked)}."
    for commander, opponent in event.commander_targets:
        line += f" {commander} attacks opponent {opponent}."
    if event.tapped:
        line += f" Tapped {_listed(event.tapped)}."
    if event.evasion:
        stated = ", ".join(
            f"{attacker} ({', '.join(EVASION_WORDS[e] for e in evasions)})"
            for attacker, evasions in event.evasion
        )
        line += f" Evasion stated: {stated}."
    return line


def _trample(event: TrampleDamageStated) -> str:
    each = "; ".join(f"{entry.attacker} {entry.damage} to {entry.seat}" for entry in event.entries)
    return f"Trample damage: {each}." if event.entries else "Trample damage: none stated."


def _blocks_requested(event: BlocksRequested) -> str:
    """A `blocks` choice: the attackers it may block, with their instance ids and evasion when
    the event holds them."""
    if event.attacker_ids:
        cards = tuple(
            RevealedCard(instance_id, name)
            for name, instance_id in zip(event.attackers, event.attacker_ids, strict=True)
        )
        attackers = attackers_to_block(cards, event.evasion)
    else:
        attackers = _listed(event.attackers)
    return f"Choice {event.choice_id} (blocks) for {event.seat}: attacked by {attackers}."


def _combat_damage(event: CombatDamageDealt) -> list[str]:
    lines = [
        f"{hit.attacker} dealt {hit.damage} combat damage"
        + (f" to opponent {hit.commander_target}" if hit.commander_target is not None else "")
        + "."
        for hit in event.hits
    ]
    if not lines:
        lines.append("No combat damage: every attacker was blocked or has left the battlefield.")
    totals = f"Damage dealt {event.damage_total}/{DAMAGE_TO_WIN}"
    if event.commander_damage:
        each = ", ".join(
            f"{name} {'/'.join(str(n) for n in damage)}" for name, damage in event.commander_damage
        )
        totals += f"; commander damage {each}"
    return [*lines, totals + "."]


def _combat_damage_to_seats(event: CombatDamageToSeats) -> list[str]:
    lines = [
        f"{hit.attacker} dealt {hit.damage} combat damage to {hit.seat}." for hit in event.hits
    ]
    if not lines:
        lines.append("No combat damage: every attacker was blocked or has left the battlefield.")
    for damaged in event.seats:
        line = f"{damaged.seat} life now {damaged.life}"
        if damaged.commander_damage:
            each = ", ".join(f"{name} {damage}" for name, damage in damaged.commander_damage)
            line += f"; commander damage from {each}"
        lines.append(line + ".")
    return lines


def _blocks(event: BlocksDeclared) -> str:
    if not event.blocks:
        return f"{event.seat} declares no blocks."
    each = "; ".join(f"{block.blocker} blocks {block.attacker}" for block in event.blocks)
    return f"{event.seat} blocks: {each}."


def _eliminated(event: SeatEliminated) -> str:
    match event.cause:
        case EliminationCause.LIFE:
            return f"{event.seat} is eliminated: its life is 0 or less."
        case EliminationCause.COMMANDER_DAMAGE:
            return f"{event.seat} is eliminated: 21 or more combat damage from one commander."
        case EliminationCause.CONCEDE:
            return f"{event.seat} conceded and is eliminated."
        case _:
            assert_never(event.cause)


def _revealed_to(event: ChoiceRevealedTo) -> str:
    """The public form of a reveal: whose choice it is and, for a hand, whose hand."""
    if event.hand_of is not None:
        return f"{event.seat} looks at {event.hand_of}'s hand (CHOICE {event.kind})."
    return f"{event.seat} looks at cards for a pending choice (CHOICE {event.kind})."


def _asked(event: ChoiceAsked) -> str:
    text = event.text.strip()
    ending = "" if text.endswith((".", "!", "?")) else "."
    return f"Choice {event.choice_id} (ask) for {event.seat}: {text}{ending}"


# @spec TOOL-087
def _ask_answered(event: AskAnswered) -> str:
    """An answer to an `ask`, with its answer text in double quotes, written verbatim."""
    answered = f"{event.seat} answered choice {event.choice_id} (ask)"
    return f'{answered}: "{event.text}".' if event.text is not None else f"{answered}."


def _assumption(event: AssumptionMade) -> str:
    match event.kind:
        case AssumptionKind.X_IS_ZERO:
            return f"Assumed: X = 0 for {event.card}." if event.card else "Assumed: X = 0."
        case AssumptionKind.NO_MANA_COST:
            return f"Assumed: {event.card} has no mana cost, so it cost nothing."
        case AssumptionKind.SNOW_AS_GENERIC:
            return "Assumed: {S} paid as generic mana, since snow sources are not tracked."
        case AssumptionKind.READING:
            return f"Assumed for {event.card}: {event.text}."
        case _:
            assert_never(event.kind)


def _reminder(event: ReminderIssued) -> str:
    named = [name if count == 1 else f"{name} ×{count}" for name, count in event.cards]
    seat = f" for {event.seat}" if event.seat is not None else ""
    return f"Reminder ({event.step.value}){seat}: {', '.join(named)}"


def _contested_start(event: ContestedGameStarted) -> list[str]:
    seats = [
        f"{seat.number} {seat.seat_id}: deck {seat.deck_id}, life {seat.life}"
        + (", the tested seat" if seat.tested else "")
        + "."
        for seat in event.seats
    ]
    return [
        f"Started contested game {event.game_id} with seed {event.seed}. Seats in turn order:",
        *seats,
        "Each seat passes its own seat id as game_id.",
    ]


# @spec TURN-046, TURN-057
def _stopped(event: AdvanceStopped, after: int | None) -> str:
    """Why the advance stopped, and the call to send next, with the change number to pass."""
    to = f'to="{event.to.value}"' if event.to is not None else ""
    following = f"after={after}" if after is not None else ""
    match event.reason:
        case StopReason.REMINDER:
            arguments = ", ".join(part for part in (to, following) if part)
            return (
                f"Stopped at {event.step.value} for the reminder."
                f" Send advance({arguments}) again to continue."
            )
        case StopReason.DISCARD:
            count = event.discard_count
            discard = f"discard=[{_plural(count, 'card')} from hand]"
            arguments = ", ".join(part for part in (to, discard, following) if part)
            return (
                f"Stopped at {event.step.value}: the hand is over {_number_word(MAXIMUM_HAND)}"
                f" cards, so {count} must be discarded in cleanup. Send advance({arguments})"
                " to continue, or add override if the hand has no maximum size."
            )
        case StopReason.BLOCKS:
            again = f"advance({to})" if to else "advance"
            return (
                f"Stopped at {event.step.value}: the attacked seats declare blockers first."
                f" Once they have, send {again} again, with the change number then shown as"
                " after."
            )
        case StopReason.END_WINDOW:
            again = f"advance({to})" if to else "advance"
            return (
                f"Stopped at {event.step.value}: the other seats are being asked whether they"
                f" respond; {event.seat} is asked now. Once the window closes, send {again}"
                " again, with the change number then shown as after."
            )
        case _:
            assert_never(event.reason)


def _window_words(item: str | None, window: str | None) -> str:
    """What a pass was made on: a stack item, the attack, or the end step."""
    if item is not None:
        return f"on {item}"
    return "in the end step" if window == "end" else "on the attack"


# @spec STACK-047, TOOL-040
def _automatic_pass(event: AutomaticPass) -> str:
    where = _window_words(event.item, event.window)
    return f"{event.seat} passed automatically {where}: no untapped permanents."


def _passed(event: Passed) -> str:
    if event.reminder:
        step = event.step.value if event.step is not None else "step"
        return f"{event.seat} passed on its {step} reminders."
    return f"{event.seat} passed {_window_words(event.item, event.window)}."


def _resolve_asked(event: ResolveAsked) -> str:
    held = json.dumps(event.delta, separators=(", ", ": "))
    to = event.to or "its default destination"
    line = (
        f"Choice {event.choice_id} (resolve) for {event.seat}: {event.item} {event.source}"
        f" holds delta {held} and goes to {to}."
    )
    if event.error is not None:
        line += f" It cannot resolve as held: {error_text(event.error)}"
    else:
        line += " Something resolved above it since it was put on the stack."
    return (
        line + f' Confirm it with choose(choice_id="{event.choice_id}"), or say what it does now'
        " with restate."
    )


def _not_declared(event: AttackNotDeclared) -> str:
    return (
        f"Attack not declared: stopped at {event.step.value} for another seat's reminder;"
        " nothing was declared or tapped. Send attack again once your seat is asked to take"
        " its turn, with the change number then shown as after."
    )


_INTO_HIDDEN = {
    "hand": "into its hand",
    "library": "into its library",
    "library_top": "on top of its library",
    "library_bottom": "on the bottom of its library",
}


# @spec TOOL-063
def _still_waiting(event: StillWaiting) -> str:
    """A wait that timed out: who the game is still waiting on, and what they are asked."""
    asked = event.asked
    if asked is None or not asked.seats:
        return "Still waiting: the game is waiting on no seat."
    return f"Still waiting: {seats_asked(asked)} asked to {asked_to(asked, yourself=False)}."


def _number_word(number: int) -> str:
    words = {7: "seven"}
    return words.get(number, str(number))


# @spec GAME-145
def notice_line(notice: NoticeKind, seat: SeatNumber | None = None) -> str:
    """A notice; one that is a seat's own names the seat."""
    if seat is not None and notice is NoticeKind.EMPTY_LIBRARY:
        return f"Notice: {seat}'s library ran out: a draw found too few cards"
    match notice:
        case NoticeKind.DAMAGE:
            return f"Notice: {DAMAGE_TO_WIN} damage reached"
        case NoticeKind.COMMANDER_DAMAGE:
            return (
                f"Notice: {COMMANDER_DAMAGE_TO_WIN} commander damage reached against every opponent"
            )
        case NoticeKind.TURN_LIMIT:
            return "Notice: turn limit reached"
        case NoticeKind.LIFE:
            return "Notice: life is 0 or less"
        case NoticeKind.EMPTY_LIBRARY:
            return "Notice: a draw found too few cards in the library"
        case NoticeKind.TESTED_SEAT_ELIMINATED:
            return "Notice: the tested seat has been eliminated"
        case NoticeKind.OPPONENTS_ELIMINATED:
            return "Notice: every opposing seat has been eliminated"
        case _:
            assert_never(notice)


def _deck_loaded(event: DeckLoaded) -> list[str]:
    commanders = (
        f"commander {event.commanders[0]}"
        if len(event.commanders) == 1
        else f"commanders {' and '.join(event.commanders)}"
    )
    facts = f"{event.card_count} cards, {commanders}."
    headline = (
        f"Deck {event.deck_id} was already loaded: {facts}"
        if event.already_loaded
        else f"Loaded deck {event.deck_id}: {facts}"
    )
    return [headline, *report_lines(event.report)]


def event_lines(event: Event, tool: str | None = None, after: int | None = None) -> list[str]:
    """The one rendering of each event type.

    `tool` words what an override would do; `after` is the game's change number, for an
    event that says what call to send next.
    """
    match event:
        case StepsEntered():
            return _steps(event)
        case DeckLoaded():
            return _deck_loaded(event)
        case GameStarted():
            return [
                f"Started game {event.game_id} with seed {event.seed}. Hand: {_listed(event.hand)}."
            ]
        case ContestedGameStarted():
            return _contested_start(event)
        case MulliganTaken():
            bottom = _plural(cards_to_bottom(event.mulligans), "card")
            return [
                f"Took mulligan {event.mulligans}. Hand: {_listed(event.hand)}."
                f" Keeping now puts {bottom} on the bottom."
            ]
        case HandKept():
            bottomed = f" Bottomed {_listed(event.bottomed)}." if event.bottomed else ""
            return [f"Kept the hand: {_listed(event.hand)}.{bottomed}"]
        case CardPlayed():
            return [_played(event)]
        case EffectRecorded():
            return [f"Effect from {event.source} recorded."]
        case CostPaid():
            return [_paid(event)]
        case CardMoved():
            return [_moved(event)]
        case TokensCreated():
            return [f"Created {_plural(event.count, f'{event.name} token')}."]
        case CardsDrawn():
            return [f"Drew {_listed(event.cards)}." if event.cards else "Drew no cards."]
        case HiddenCardsDrawn():
            drawn = "a card" if event.count == 1 else f"{event.count} cards"
            return [f"{event.seat} drew {drawn}."]
        case HiddenCardsMoved():
            moved = "a card" if event.count == 1 else f"{event.count} cards"
            return [f"{event.seat} put {moved} {_INTO_HIDDEN.get(event.to, 'away')}."]
        case HiddenMulliganTaken():
            return [f"{event.seat} took a mulligan ({event.mulligans} taken)."]
        case HiddenHandKept():
            return [f"{event.seat} kept {event.kept}, bottomed {event.bottomed}."]
        case SeatToAct():
            return [f"You are asked to {asked_to(event.asked, yourself=True)}."]
        case StillWaiting():
            return [_still_waiting(event)]
        case SeatOut():
            return [f"{event.seat} is out of the game; nothing more is asked of it."]
        case GameHasEnded():
            return ["The game has ended."]
        case CardsDiscarded():
            return [f"Discarded {_listed(event.cards)}."]
        case Tapped():
            return [f"Tapped {_listed(event.cards)}."]
        case Untapped():
            return [f"Untapped {_listed(event.cards)}."]
        case ManaAdded():
            return [f"Added {event.mana} to the pool."]
        case CountersChanged():
            return [_counters(event)]
        case LifeChanged():
            whose = f"{event.seat} life" if event.seat is not None else "Life"
            return [f"{whose} {event.change:+d}, now {event.now}."]
        case SeatDamaged():
            return [f"{event.seat} took {event.amount} damage; life now {event.life}."]
        case ControlChanged():
            return [f"{event.seat} now controls {event.card}."]
        case DamageAdded():
            return [f"Damage {event.amount:+d}, now {event.total}/{DAMAGE_TO_WIN}."]
        case LibraryShuffled():
            return ["Shuffled the library."]
        case AlreadySo():
            return [_already_so(event)]
        case InstanceChosen():
            return [f"Chose {event.instance_id} for {event.name}; the matching cards differ."]
        case CardsRevealed():
            cards = ", ".join(f"{card.name} ({card.instance_id})" for card in event.cards)
            return [
                f"Choice {event.choice_id} ({event.kind}) revealed: {cards}."
                f' Say where they go with choose(choice_id="{event.choice_id}").'
            ]
        case AskAnswered():
            return [_ask_answered(event)]
        case CastTriggerApplied():
            return [f"Cast trigger: {event.source}."]
        case ChoiceRevealedTo():
            return [_revealed_to(event)]
        case ChoiceAsked():
            return [_asked(event)]
        case BlocksRequested():
            return [_blocks_requested(event)]
        case TrampleDamageStated():
            return [_trample(event)]
        case NoBlocksDeclared():
            return [f"{event.seat} has no untapped creature: no blocks declared."]
        case BlocksDeclared():
            return [_blocks(event)]
        case CombatDamageToSeats():
            return _combat_damage_to_seats(event)
        case SeatEliminated():
            return [_eliminated(event)]
        case NothingRevealed():
            return [f"The {event.kind} revealed no cards, so no choice is pending."]
        case ChoiceResolved():
            placed = ", ".join(f"{p.card} → {_zone(p.to)}" for p in event.placements)
            return [f"Placed the revealed cards: {placed}." if placed else "Placed no cards."]
        case AttackDeclared():
            return [_attack(event)]
        case CombatDamageDealt():
            return _combat_damage(event)
        case AssumptionMade():
            return [_assumption(event)]
        case ReminderIssued():
            return [_reminder(event)]
        case AdvanceStopped():
            return [_stopped(event, after)]
        case ExpectationMismatched():
            return [f"Warning: {event.key} is {event.actual}, expected {event.expected}"]
        case NoticeRaised():
            return [notice_line(event.notice)]
        case ChecksOverridden():
            checks = " ".join(check_text(check) for check in event.checks)
            return [f"Overridden ({event.reason}): {checks}"]
        case GameEnded():
            return [f"Game ended: {event.result}."]
        case AlreadyApplied():
            return [f"Already applied as change #{event.change}; nothing was applied again."]
        case SnapshotWritten():
            return [f"Snapshot written for turn {event.turn}."]
        case StateListed():
            return [f"State, {event.detail} detail."]
        case LogExported():
            return [
                f"Exported the log: {_plural(event.entries, 'entry', 'entries')},"
                f" {_plural(event.snapshots, 'snapshot')}, {_plural(event.calls, 'call')}."
            ]
        case Refused():
            return refusal_lines(event, tool)
        case AttackNotDeclared():
            return [_not_declared(event)]
        case ItemStacked():
            return [f"Put {event.item} on the stack: {event.source} from {event.controller}."]
        case Passed():
            return [_passed(event)]
        case AutomaticPass():
            return [_automatic_pass(event)]
        case ItemResolved():
            return [f"{event.item} resolved: {event.source} from {event.controller}."]
        case ItemCountered():
            return [f"{event.item} was countered: {event.source} from {event.controller}."]
        case ItemRemoved():
            return [
                f"{event.item} left the stack unresolved: {event.source} from {event.controller}."
            ]
        case ResolveAsked():
            return [_resolve_asked(event)]
        case _:
            assert_never(event)
