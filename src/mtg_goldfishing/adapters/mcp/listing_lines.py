"""The wording of what the service has read and listed: get_state's zones and load_deck's report."""

from __future__ import annotations

from typing import assert_never

from mtg_goldfishing.domain.events import DeckReport
from mtg_goldfishing.domain.game.listing import (
    CommanderListing,
    PermanentListing,
    SeatListing,
    StateListing,
)
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import (
    ASSUMES_UNTAPPED_PREFIX,
    AnyColor,
    AnyColorScope,
    CardsInGraveyardCount,
    CardsInHandCount,
    Choice,
    Count,
    Counted,
    CountersOnSelfCount,
    DevotionCount,
    Fixed,
    ManaAbility,
    PermanentsCount,
    Produces,
)


def _symbols(colors: tuple[str, ...]) -> str:
    return "".join("{" + color + "}" for color in colors)


def _any_color(produced: AnyColor) -> str:
    amount = "one mana" if produced.amount == 1 else f"{produced.amount} mana"
    among = produced.among
    if isinstance(among, tuple):
        return f"{amount} of one color among {_symbols(among)}"
    match among:
        case AnyColorScope.ANY:
            return (
                f"{amount} of any color" if produced.amount == 1 else f"{amount} of any one color"
            )
        case AnyColorScope.COMMANDER_IDENTITY:
            return f"{amount} of one color in the commanders' color identity"
        case _:
            assert_never(among)


def _each(count: Count) -> str:
    match count:
        case PermanentsCount(match=kind):
            return f"{kind} you control"
        case DevotionCount(colors=colors):
            return f"point of devotion to {_symbols(colors)}"
        case CardsInHandCount():
            return "card in your hand"
        case CardsInGraveyardCount(match=kind):
            return f"{kind} card in your graveyard" if kind else "card in your graveyard"
        case CountersOnSelfCount(counter=counter):
            return f"{counter} counter on it"
        case _:
            assert_never(count)


def _produces(produced: Produces) -> str:
    match produced:
        case Fixed(mana=mana):
            return str(mana)
        case Choice(options=options):
            return " or ".join(str(option) for option in options)
        case AnyColor():
            return _any_color(produced)
        case Counted(per=per, mana=mana):
            each = str(mana) if isinstance(mana, ManaString) else _any_color(mana)
            return f"{each} for each {_each(per)}"
        case _:
            assert_never(produced)


def ability_text(ability: ManaAbility) -> str:
    """A mana ability as read: its costs, the mana it makes, and anything assumed."""
    costs: list[str] = []
    if ability.mana_cost:
        costs.append(str(ability.mana_cost))
    if ability.taps:
        costs.append("{T}")
    if ability.life:
        costs.append(f"pay {ability.life} life")
    if ability.sacrifices:
        costs.append("sacrifice it")
    if ability.other_cost:
        costs.append(ability.other_cost)
    text = (", ".join(costs) + ": " if costs else "") + _produces(ability.produces)
    if ability.restriction is not None:
        text += f" ({ability.restriction.text.rstrip('.')})"
    if ability.assumptions:
        text += f" ({'; '.join(ability.assumptions)})"
    return text


def _names(names: tuple[str, ...]) -> str:
    return ", ".join(names) if names else "none"


def _times(count: int) -> str:
    return "1 time" if count == 1 else f"{count} times"


def _permanent(permanent: PermanentListing) -> str:
    details: list[str] = []
    if permanent.tapped:
        details.append("tapped")
    if permanent.counters:
        details.append("counters " + ", ".join(f"{n} {kind}" for kind, n in permanent.counters))
    if permanent.mana:
        details.append("mana " + " / ".join(ability_text(a) for a in permanent.mana))
    if permanent.haste:
        details.append("haste")
    if permanent.vigilance:
        details.append("vigilance")
    steps = [step.value for step in permanent.triggers]
    steps.extend(f"{step.value} (opp)" for step in permanent.opponent_triggers)
    if steps:
        details.append("trigger in " + ", ".join(steps))
    described = f": {'; '.join(details)}" if details else ""
    owner = f" (owner {permanent.owner})" if permanent.owner is not None else ""
    return f"  {permanent.instance_id} {permanent.name}{owner}{described}"


def _payments(listing: StateListing) -> list[str]:
    if listing.payments is None:
        return []
    paid = [
        f"{payment.cost} ({payment.mana_spent} mana"
        + (f", {payment.life} life" if payment.life else "")
        + ")"
        for payment in listing.payments
    ]
    return [f"Payments this turn: {', '.join(paid) if paid else 'none'}"]


def _commander_damage(commander: CommanderListing, others: list[SeatNumber]) -> str:
    damage = " / ".join(f"{seat} {n}" for seat, n in zip(others, commander.damage, strict=True))
    return f"Commander {commander.name}: cast {_times(commander.casts)}, damage {damage}"


def _seat_lines(each: SeatListing, calling: SeatNumber, everyone: list[SeatNumber]) -> list[str]:
    """One seat as any seat may see it: its standing, then its public zones."""
    you = " (you)" if each.seat == calling else ""
    out = " · Out" if each.eliminated else ""
    lines = [
        f"{each.seat}{you} · Life {each.life} · Hand {each.hand_size}"
        f" · Library {each.library_size}{out}",
        f"Battlefield ({len(each.battlefield)}):" + ("" if each.battlefield else " none"),
        *(_permanent(permanent) for permanent in each.battlefield),
        f"Graveyard ({len(each.graveyard)}): {_names(each.graveyard)}",
        f"Command zone ({len(each.command)}): {_names(each.command)}",
    ]
    if each.exile is not None:
        lines.append(f"Exile ({len(each.exile)}): {_names(each.exile)}")
    others = [seat for seat in everyone if seat != each.seat]
    lines.extend(_commander_damage(commander, others) for commander in each.commanders or ())
    return lines


# @spec TOOL-051, TOOL-066, GAME-122
def contested_state_lines(listing: StateListing, seats: tuple[SeatListing, ...]) -> list[str]:
    """A contested game's listing: the calling seat's hand, then every seat in turn order."""
    calling = listing.seat
    assert calling is not None, "a contested game's listing names its calling seat"
    everyone = [each.seat for each in seats]
    lines = [f"Hand ({len(listing.hand)}): {_names(listing.hand)}"]
    for each in seats:
        lines.extend(_seat_lines(each, calling, everyone))
    if listing.stack:
        items = "; ".join(f"{i.item} {i.source} from {i.controller}" for i in listing.stack)
        lines.append(f"Stack ({len(listing.stack)}): {items}")
    if listing.window is not None:
        asking = f"asking {listing.window.asking}" if listing.window.asking else "waiting"
        lines.append(f"Response window ({listing.window.kind}): {asking}")
    return [*lines, *_payments(listing)]


def state_lines(listing: StateListing) -> list[str]:
    """get_state's listing. The library's contents are never part of it."""
    if listing.seats is not None:
        return contested_state_lines(listing, listing.seats)
    lines = [
        f"Hand ({len(listing.hand)}): {_names(listing.hand)}",
        f"Battlefield ({len(listing.battlefield)}):" + ("" if listing.battlefield else " none"),
        *(_permanent(permanent) for permanent in listing.battlefield),
        f"Graveyard ({len(listing.graveyard)}): {_names(listing.graveyard)}",
        f"Command zone ({len(listing.command)}): {_names(listing.command)}",
    ]
    if listing.exile is not None:
        lines.append(f"Exile ({len(listing.exile)}): {_names(listing.exile)}")
    if listing.library_size is not None:
        size = listing.library_size
        lines.append(f"Library: {size} card" + ("" if size == 1 else "s"))
    for commander in listing.commanders or ():
        damage = "/".join(str(n) for n in commander.damage)
        lines.append(f"Commander {commander.name}: cast {_times(commander.casts)}, damage {damage}")
    return [*lines, *_payments(listing)]


def _untapped_condition(text: str) -> str:
    return text.removeprefix(ASSUMES_UNTAPPED_PREFIX)


def report_lines(report: DeckReport) -> list[str]:
    """load_deck's report on definitions and readings: one line for each part not empty."""
    parts: list[tuple[str, list[str]]] = [
        ("Definitions applied", list(report.definitions_applied)),
        (
            "Mana read with assumptions",
            [
                f"{r.card} ({'; '.join(r.ability.assumptions)})"
                for r in report.read_with_assumptions
            ],
        ),
        ("Mana not read", list(dict.fromkeys(u.card for u in report.unread))),
        (
            "Not used by the auto payment system on its own (name them in pay)",
            [_why_not_automatic(r.card, r.ability) for r in report.not_used_on_their_own],
        ),
        (
            "Grants haste or vigilance",
            [f"{k.card} ({k.keyword})" for k in report.granting_haste_or_vigilance],
        ),
        ("Enters tapped", [e.card for e in report.enters_tapped]),
        (
            "Assumed to enter untapped",
            [
                f"{e.card} ({'; '.join(_untapped_condition(a) for a in e.reading.assumptions)})"
                for e in report.assumed_untapped
            ],
        ),
        (
            "Keywords read with assumptions",
            [
                f"{k.card} ({k.keyword}: {'; '.join(k.reading.assumptions)})"
                for k in report.keywords_with_assumptions
            ],
        ),
        ("Not refreshed (cached data kept)", list(report.not_refreshed)),
    ]
    return [f"{title}: {', '.join(items)}" for title, items in parts if items]


def _why_not_automatic(card: str, ability: ManaAbility) -> str:
    reasons = (["sacrificed"] if ability.sacrifices else []) + (
        [ability.other_cost] if ability.other_cost else []
    )
    return f"{card} ({'; '.join(reasons)})" if reasons else card
