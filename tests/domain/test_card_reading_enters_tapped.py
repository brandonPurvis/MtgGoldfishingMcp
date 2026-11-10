"""The card reader's reading of whether a permanent enters tapped."""

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.reading.model import (
    ASSUMES_UNTAPPED_PREFIX,
    ENTERS_UNTAPPED,
    EntersTappedReading,
)
from mtg_goldfishing.domain.reading.reader import read_card
from tests.support.cards import a_card


def enters_tapped_of(card: Card) -> EntersTappedReading:
    return read_card(card).faces[0].enters_tapped


# @spec READ-041
def test_a_land_that_says_it_enters_tapped_enters_tapped() -> None:
    temple_of_plenty = a_card(
        "Temple of Plenty",
        "This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your "
        "library. You may put that card on the bottom.)\n{T}: Add {G} or {W}.",
        "Land",
    )
    assert enters_tapped_of(temple_of_plenty) == EntersTappedReading(tapped=True)


# @spec READ-041
def test_a_permanent_named_as_entering_the_battlefield_tapped_enters_tapped() -> None:
    card = a_card(
        "Old Wording Land",
        "Old Wording Land enters the battlefield tapped.\n{T}: Add {B}.",
        "Land",
    )
    assert enters_tapped_of(card) == EntersTappedReading(tapped=True)


# @spec READ-041
def test_a_creature_that_says_it_enters_tapped_enters_tapped() -> None:
    card = a_card("Sleepy Creature", "This creature enters tapped.", "Creature — Beast")
    assert enters_tapped_of(card) == EntersTappedReading(tapped=True)


# @spec READ-041
def test_entering_tapped_and_not_untapping_during_the_untap_step_enters_tapped() -> None:
    card = a_card(
        "Sleepy Land",
        "This land enters tapped and doesn't untap during your untap step.\n{T}: Add {C}{C}.",
        "Land",
    )
    assert enters_tapped_of(card) == EntersTappedReading(tapped=True)


# @spec READ-042
def test_entering_tapped_unless_a_condition_holds_is_read_as_untapped_with_the_condition() -> None:
    glacial_fortress = a_card(
        "Glacial Fortress",
        "This land enters tapped unless you control a Plains or an Island.\n{T}: Add {W} or {U}.",
        "Land",
    )
    assert enters_tapped_of(glacial_fortress) == EntersTappedReading(
        tapped=False,
        assumptions=(ASSUMES_UNTAPPED_PREFIX + "unless you control a Plains or an Island",),
    )


# @spec READ-042
def test_entering_tapped_unless_a_choice_is_made_is_read_as_untapped_with_the_choice() -> None:
    hallowed_fountain = a_card(
        "Hallowed Fountain",
        "({T}: Add {W} or {U}.)\nAs this land enters, you may pay 2 life. "
        "If you don't, it enters tapped.",
        "Land — Plains Island",
    )
    assert enters_tapped_of(hallowed_fountain) == EntersTappedReading(
        tapped=False,
        assumptions=(ASSUMES_UNTAPPED_PREFIX + "you may pay 2 life",),
    )


# @spec READ-043
def test_a_permanent_whose_text_says_nothing_about_entering_tapped_enters_untapped() -> None:
    sol_ring = a_card("Sol Ring", "{T}: Add {C}{C}.")
    assert enters_tapped_of(sol_ring) == ENTERS_UNTAPPED
