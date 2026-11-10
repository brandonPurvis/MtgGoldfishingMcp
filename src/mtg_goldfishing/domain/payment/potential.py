"""What the agent's mana sources could do in principle, for turn statistics and snapshots."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.cards_in_play import face_of, is_land
from mtg_goldfishing.domain.game.model import CardInstance, Game
from mtg_goldfishing.domain.payment.auto import can_pay_with
from mtg_goldfishing.domain.payment.matching import Requirement
from mtg_goldfishing.domain.payment.sources import available_sources


# @spec REC-015
def mana_available(game: Game, deck: LoadedDeck) -> int:
    """The most mana the sources the auto payment system may use on their own could make."""
    sources = available_sources(game, deck, paying_for=None, ignore_tapped=True)
    return sum(source.most_mana for source in sources)


# @spec REC-014
def payable_in_principle(game: Game, deck: LoadedDeck, card: CardInstance) -> bool:
    """Whether a card's first face, X as 0, could be paid with every usable source untapped."""
    if is_land(deck, card):
        return True
    face = face_of(deck, card)
    if face is None:
        return False
    sources = available_sources(game, deck, paying_for=face.type_line, ignore_tapped=True)
    requirement = Requirement.of(face.mana_cost.with_x(0), phyrexian_life=0)
    return can_pay_with(requirement, [], sources, life_budget=max(0, game.life - 1))
