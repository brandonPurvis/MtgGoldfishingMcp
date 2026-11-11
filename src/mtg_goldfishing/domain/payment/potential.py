"""What a seat's mana sources could do in principle, for turn statistics and snapshots."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.cards_in_play import face_of, is_land
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import CardInstance, Game
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.payment.auto import can_pay_with
from mtg_goldfishing.domain.payment.matching import Requirement
from mtg_goldfishing.domain.payment.sources import available_sources, most_mana_of


# @spec REC-015
def mana_available(
    game: Game, deck: LoadedDeck, seat: SeatNumber, decks: Decks | None = None
) -> int:
    """The most mana the seat's sources the auto payment system may use on their own could
    make, each read from its owner's deck (`decks`; omitted, every seat plays `deck`)."""
    sources = available_sources(game, deck, seat, paying_for=None, ignore_tapped=True, decks=decks)
    return most_mana_of(sources)


# @spec REC-014
def payable_in_principle(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    card: CardInstance,
    decks: Decks | None = None,
) -> bool:
    """Whether a card's first face, X as 0, could be paid by the seat with every usable source
    untapped, each source read from its owner's deck (`decks`; omitted, every seat plays
    `deck`). `deck` is the card's owner's."""
    if is_land(deck, card):
        return True
    face = face_of(deck, card)
    if face is None:
        return False
    sources = available_sources(
        game, deck, seat, paying_for=face.type_line, ignore_tapped=True, decks=decks
    )
    requirement = Requirement.of(face.mana_cost.with_x(0), phyrexian_life=0)
    life_budget = max(0, game.seat(seat).life - 1)
    return can_pay_with(requirement, [], sources, life_budget=life_budget)
