"""The deck checks: Commander's construction rules, judged from card data."""

from __future__ import annotations

import re
from collections.abc import Sequence

from mtg_goldfishing.domain.cards import Card, CardSource
from mtg_goldfishing.domain.events import CheckKind, FailedCheck

DECK_SIZE = 100

_ANY_NUMBER = re.compile(r"\ba deck can have any number of cards named\b", re.IGNORECASE)
_STATED_NUMBER = re.compile(r"\ba deck can have up to (?P<number>\w+) cards named\b", re.IGNORECASE)
_CAN_BE_YOUR_COMMANDER = re.compile(r"\bcan be your commander\b", re.IGNORECASE)
_NUMBER_WORDS = {
    word: number
    for number, word in enumerate(
        (
            *("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
            *("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen"),
            *("seventeen", "eighteen", "nineteen", "twenty"),
        )
    )
}


def _rules_text(card: Card) -> str:
    return "\n".join(face.oracle_text for face in card.faces)


def copies_allowed(card: Card) -> int | None:
    """How many copies of a card a deck may hold; None when any number is allowed."""
    if any(face.has_type("basic") for face in card.faces):
        return None
    text = _rules_text(card)
    if _ANY_NUMBER.search(text):
        return None
    stated = _STATED_NUMBER.search(text)
    if stated is not None:
        word = stated["number"].lower()
        number = int(word) if word.isdigit() else _NUMBER_WORDS.get(word)
        if number is not None:
            return number
    return 1


def can_be_a_commander(card: Card) -> bool:
    """A legendary creature, or a card whose rules text says it can be your commander."""
    front = card.front
    is_legendary_creature = front.has_type("legendary") and front.is_creature
    return is_legendary_creature or bool(_CAN_BE_YOUR_COMMANDER.search(_rules_text(card)))


# @spec DECK-021, DECK-022, DECK-023, DECK-024, DECK-025, DECK-026
def check_deck(
    commanders: Sequence[Card], cards: Sequence[tuple[Card, int]]
) -> tuple[FailedCheck, ...]:
    """Every deck check the deck fails.

    `cards` holds each distinct card of the deck, commanders included, with its number of
    copies. Singleton failures are one per card; color identity and legality failures
    each name every card concerned; commander eligibility names every ineligible commander.
    """
    failed: list[FailedCheck] = []
    size = sum(copies for _, copies in cards)
    if size != DECK_SIZE:
        failed.append(FailedCheck(CheckKind.DECK_SIZE, number=size, expected=DECK_SIZE))
    for card, copies in cards:
        allowed = copies_allowed(card)
        if allowed is not None and copies > allowed:
            failed.append(
                FailedCheck(CheckKind.SINGLETON, subject=card.name, number=copies, expected=allowed)
            )
    identity = {color for commander in commanders for color in commander.color_identity}
    off_color = tuple(card.name for card, _ in cards if not set(card.color_identity) <= identity)
    if off_color:
        failed.append(FailedCheck(CheckKind.COLOR_IDENTITY, names=off_color))
    illegal = tuple(
        card.name
        for card, _ in cards
        if not card.commander_legal and card.source is not CardSource.DEFINITION
    )
    if illegal:
        failed.append(FailedCheck(CheckKind.LEGALITY, names=illegal))
    ineligible = tuple(card.name for card in commanders if not can_be_a_commander(card))
    if ineligible:
        failed.append(FailedCheck(CheckKind.COMMANDER_ELIGIBILITY, names=ineligible))
    return tuple(failed)
