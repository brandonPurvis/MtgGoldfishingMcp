"""The renderer: the one place response text is made, from a use case's outcome.

A text response is

    <STATUS> <one-line summary>
    <event lines, in a fixed order>
    <status line, for a response about an existing game>

Each event type has one rendering here, and each kind of error and rule check one
wording in `refusal_lines`; no other code in the service builds response text.
"""

from __future__ import annotations

import json
from typing import assert_never

from mtg_goldfishing.adapters.mcp.listing_lines import report_lines, state_lines
from mtg_goldfishing.adapters.mcp.refusal_lines import check_text, refusal_lines
from mtg_goldfishing.application.outcome import Outcome, Status
from mtg_goldfishing.application.ports import Rendered, Renderer
from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    AlreadyApplied,
    AlreadySo,
    AlreadySoKind,
    AssumptionKind,
    AssumptionMade,
    AttackDeclared,
    CardMoved,
    CardPlayed,
    CardsDiscarded,
    CardsDrawn,
    CardsRevealed,
    ChecksOverridden,
    ChoiceResolved,
    CombatDamageDealt,
    CostPaid,
    CountersChanged,
    DamageAdded,
    DeckLoaded,
    EffectRecorded,
    Event,
    ExpectationMismatched,
    GameEnded,
    GameStarted,
    HandKept,
    InstanceChosen,
    LibraryShuffled,
    LifeChanged,
    LogExported,
    ManaAdded,
    MulliganTaken,
    NothingRevealed,
    NoticeKind,
    NoticeRaised,
    Refused,
    ReminderIssued,
    SnapshotWritten,
    StateListed,
    StepsEntered,
    StopReason,
    Tapped,
    TokensCreated,
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
from mtg_goldfishing.domain.game.summary import GameSummary
from mtg_goldfishing.domain.steps import Step

GET_LOG = "get_log"


class TextRenderer(Renderer):
    """Implements the `Renderer` port with the plain-text response format."""

    # @spec TOOL-014, TOOL-015, TOOL-016, TOOL-022, TOOL-024, TOOL-025, TOOL-026, REC-018, REC-024
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


def response_lines(tool: str, outcome: Outcome) -> list[str]:
    """Status and summary, the summary's own detail, event lines, then the status line."""
    headline, *detail = summary_lines(outcome.summary, tool)
    lines = [f"{outcome.status.value} {headline}", *detail]
    if isinstance(outcome.payload, StateListing):
        lines.extend(state_lines(outcome.payload))
    raised: list[NoticeKind] = []
    after = outcome.game.change if outcome.game else None
    for event in sorted(outcome.events, key=_place_in_order):
        if isinstance(event, NoticeRaised):
            raised.append(event.notice)
        else:
            lines.extend(event_lines(event, tool, after))
    standing = outcome.game.notices if outcome.game else ()
    notices = list(dict.fromkeys((*raised, *standing)))
    lines.extend(notice_line(notice) for notice in notices)
    if outcome.game is not None:
        lines.append(status_line(outcome.game))
    return lines


def summary_lines(summary: Event, tool: str | None = None) -> list[str]:
    """The headline (first) and any lines that belong with it, such as a deck report."""
    lines = event_lines(summary, tool)
    return lines or ["Done."]


# ------------------------------------------------------------------------- the status line


# @spec TOOL-017, TOOL-018, TOOL-019, TOOL-020, TOOL-021
def status_line(game: GameSummary) -> str:
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
            | DamageAdded()
            | LibraryShuffled()
            | AlreadySo()
            | InstanceChosen()
            | ChoiceResolved()
            | AttackDeclared()
            | SnapshotWritten()
            | DeckLoaded()
            | GameStarted()
            | MulliganTaken()
            | HandKept()
            | CardPlayed()
            | EffectRecorded()
            | GameEnded()
            | StateListed()
            | LogExported()
            | Refused()
        ):
            return 4
        case CardsRevealed() | NothingRevealed():
            return 5
        case CombatDamageDealt():
            return 6
        case AssumptionMade():
            return 7
        case ReminderIssued():
            return 8
        case AdvanceStopped():
            return 9
        case ExpectationMismatched():
            return 10
        case NoticeRaised():
            return 11
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
        f"T{entered.turn} {entered.step.value}"
        if entered.step is Step.UNTAP
        else entered.step.value
        for entered in event.steps
    ]
    return [" → ".join(named)]


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
        case _:
            assert_never(event.kind)


def _attack(event: AttackDeclared) -> str:
    if not event.attackers:
        return "Declared no attack."
    line = f"Attacking with {_listed(event.attackers)}."
    if event.blocked:
        line += f" Blocked: {_listed(event.blocked)}."
    for commander, opponent in event.commander_targets:
        line += f" {commander} attacks opponent {opponent}."
    if event.tapped:
        line += f" Tapped {_listed(event.tapped)}."
    return line


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
    return f"Reminder ({event.step.value}): {', '.join(named)}"


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
        case _:
            assert_never(event.reason)


def _number_word(number: int) -> str:
    words = {7: "seven"}
    return words.get(number, str(number))


def notice_line(notice: NoticeKind) -> str:
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
            return [f"Life {event.change:+d}, now {event.now}."]
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
        case _:
            assert_never(event)
