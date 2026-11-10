"""Moving cards between zones, with the bookkeeping every move implies."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AssumptionKind,
    AssumptionMade,
    CardMoved,
    CardsDrawn,
    Event,
    NoticeKind,
    NoticeRaised,
)
from mtg_goldfishing.domain.game.cards_in_play import face_name, reading_of
from mtg_goldfishing.domain.game.model import CardInstance, Destination, Game, Zone


def _leave(game: Game, card: CardInstance) -> None:
    if card.zone is Zone.LIBRARY:
        game.take_from_library(card.id)
    if card.zone is Zone.BATTLEFIELD:
        card.tapped = False
        card.counters = {}
        card.face = 0


# @spec PLAY-046, PLAY-047, PLAY-048, PLAY-049, PLAY-052, PLAY-053, PLAY-054, GAME-020
def move(
    game: Game,
    deck: LoadedDeck,
    card: CardInstance,
    destination: Destination,
    *,
    commander_stays: bool = False,
) -> list[Event]:
    """Move a card to a destination.

    A commander bound for the graveyard or exile goes to the command zone instead unless
    `commander_stays`. A card leaving the battlefield loses its tapped state, counters and
    face; a token leaving it ceases to exist. A permanent arriving on the battlefield
    enters tapped when its reading says so, or always for `battlefield_tapped`.
    """
    from_zone = card.zone
    redirected = False
    if (
        card.is_commander
        and destination in (Destination.GRAVEYARD, Destination.EXILE)
        and not commander_stays
    ):
        destination = Destination.COMMAND
        redirected = True
    events: list[Event] = []
    if from_zone is Zone.BATTLEFIELD and destination.zone is Zone.BATTLEFIELD:
        if destination is Destination.BATTLEFIELD_TAPPED:
            card.tapped = True
        return [CardMoved(card.name, from_zone.value, destination.value)]
    _leave(game, card)
    if card.is_token and from_zone is Zone.BATTLEFIELD:
        game.remove_token(card)
        return [CardMoved(card.name, from_zone.value, destination.value, token_gone=True)]
    enters_tapped = False
    if destination.zone is Zone.BATTLEFIELD:
        reading = reading_of(deck, card).enters_tapped
        enters_tapped = reading.tapped
        events.extend(
            AssumptionMade(AssumptionKind.READING, face_name(deck, card), text)
            for text in reading.assumptions
        )
    game.put(card, destination, tapped=enters_tapped)
    events.insert(0, CardMoved(card.name, from_zone.value, destination.value, redirected))
    return events


def draw(game: Game, count: int) -> list[Event]:
    """Draw cards from the top of the library; too few cards raises the empty library notice."""
    drawn: list[str] = []
    events: list[Event] = []
    for _ in range(count):
        if not game.library:
            break
        card = game.instance(game.library.pop(0))
        card.zone = Zone.HAND
        drawn.append(card.name)
    events.append(CardsDrawn(tuple(drawn)))
    if len(drawn) < count:
        events.extend(raise_notice(game, NoticeKind.EMPTY_LIBRARY))
    return events


def raise_notice(game: Game, notice: NoticeKind) -> list[Event]:
    if notice in game.notices:
        return []
    game.notices.append(notice)
    return [NoticeRaised(notice)]
