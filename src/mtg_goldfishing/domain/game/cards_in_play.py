"""What the game knows about a card instance: its card data, face in play and readings."""

from __future__ import annotations

from mtg_goldfishing.domain.cards import Card, Face, type_words
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import CardInstance, Game, TokenSpec
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import (
    NO_READING,
    Choice,
    FaceReading,
    Fixed,
    KeywordReading,
    ManaAbility,
)


def card_of(deck: LoadedDeck, card: CardInstance) -> Card | None:
    """The card data behind an instance; None for a token."""
    if card.is_token:
        return None
    if card.definition is not None:
        return card.definition
    deck_card = deck.card(card.name)
    return deck_card.card if deck_card else None


def face_of(deck: LoadedDeck, card: CardInstance) -> Face | None:
    """The face in play (or the first face, off the battlefield); None for a token."""
    data = card_of(deck, card)
    if data is None:
        return None
    return data.faces[card.face] if card.face < len(data.faces) else data.front


def names_of(deck: LoadedDeck, card: CardInstance) -> tuple[str, ...]:
    """Every name a call may use for an instance: its card name and its face names."""
    data = card_of(deck, card)
    if data is None:
        return (card.name,)
    return (data.name, *(face.name for face in data.faces))


def face_name(deck: LoadedDeck, card: CardInstance) -> str:
    face = face_of(deck, card)
    return face.name if face else card.name


def token_reading(spec: TokenSpec) -> FaceReading:
    if not spec.produces:
        return NO_READING
    produces: Fixed | Choice = (
        Fixed(spec.produces[0]) if len(spec.produces) == 1 else Choice(spec.produces)
    )
    ability = ManaAbility(produces=produces, sacrifices=spec.sacrifice_to_produce)
    return FaceReading(mana_abilities=(ability,))


def reading_of(deck: LoadedDeck, card: CardInstance) -> FaceReading:
    """The reading of the instance's face in play."""
    if card.token is not None:
        return token_reading(card.token)
    if card.reading is not None:
        return card.reading.face(card.face)
    deck_card = deck.card(card.name)
    return deck_card.reading.face(card.face) if deck_card else NO_READING


def type_line(deck: LoadedDeck, card: CardInstance) -> str:
    if card.token is not None:
        return card.token.types
    face = face_of(deck, card)
    return face.type_line if face else ""


def has_type(deck: LoadedDeck, card: CardInstance, word: str) -> bool:
    return word.lower() in type_words(type_line(deck, card))


def is_land(deck: LoadedDeck, card: CardInstance) -> bool:
    return has_type(deck, card, "land")


def is_creature(deck: LoadedDeck, card: CardInstance) -> bool:
    return has_type(deck, card, "creature")


def power(deck: LoadedDeck, card: CardInstance) -> str | None:
    if card.token is not None:
        return card.token.power
    face = face_of(deck, card)
    return face.power if face else None


def mana_cost(deck: LoadedDeck, card: CardInstance) -> ManaString:
    face = face_of(deck, card)
    return face.mana_cost if face else ManaString()


def _keyword(reading: FaceReading, keyword: str) -> KeywordReading:
    return reading.haste if keyword == "haste" else reading.vigilance


# @spec PAY-049, GAME-171
def has_keyword(
    game: Game,
    deck: LoadedDeck,
    card: CardInstance,
    keyword: str,
    decks: Decks | None = None,
) -> bool:
    """Haste or vigilance: the instance's own, or granted by a permanent its controller controls.

    The instance and every permanent that could grant the keyword are each read from their
    owner's deck (`decks`; omitted, every seat plays `deck`)."""
    every = decks or Decks.everyone_playing(game, deck)
    own_deck = every.of(card.owner)
    if _keyword(reading_of(own_deck, card), keyword).own:
        return True
    if not is_creature(own_deck, card):
        return False
    words = type_words(type_line(own_deck, card))
    for other in game.battlefield_of(card.controller):
        grant = _keyword(reading_of(every.of(other.owner), other), keyword).grant
        if grant is None:
            continue
        if other.id == card.id and not grant.includes_self:
            continue
        if grant.subtype is None or grant.subtype.lower() in words:
            return True
    return False


def has_haste(game: Game, deck: LoadedDeck, card: CardInstance, decks: Decks | None = None) -> bool:
    return has_keyword(game, deck, card, "haste", decks)


def has_vigilance(
    game: Game, deck: LoadedDeck, card: CardInstance, decks: Decks | None = None
) -> bool:
    return has_keyword(game, deck, card, "vigilance", decks)


def is_summoning_sick(
    game: Game, deck: LoadedDeck, card: CardInstance, decks: Decks | None = None
) -> bool:
    """A creature that entered the battlefield this turn and has no haste. `deck` is the
    creature's owner's; `decks` gives every seat's, for the permanents that may grant haste."""
    return (
        is_creature(deck, card)
        and card.entered_turn == game.turn
        and not has_haste(game, deck, card, decks)
    )
