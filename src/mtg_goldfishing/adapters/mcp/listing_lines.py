"""The wording of what the service has read and listed: get_state's zones and load_deck's report."""

from __future__ import annotations

from typing import assert_never

from mtg_goldfishing.domain.events import DeckReport
from mtg_goldfishing.domain.game.listing import PermanentListing, StateListing
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
    if permanent.triggers:
        details.append("trigger in " + ", ".join(step.value for step in permanent.triggers))
    described = f": {'; '.join(details)}" if details else ""
    return f"  {permanent.instance_id} {permanent.name}{described}"


def state_lines(listing: StateListing) -> list[str]:
    """get_state's listing. The library's contents are never part of it."""
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
    if listing.payments is not None:
        paid = [
            f"{payment.cost} ({payment.mana_spent} mana"
            + (f", {payment.life} life" if payment.life else "")
            + ")"
            for payment in listing.payments
        ]
        lines.append(f"Payments this turn: {', '.join(paid) if paid else 'none'}")
    return lines


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
