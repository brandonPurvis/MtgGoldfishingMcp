"""The reference values the storage speed check times: a full deck and a busy contested game.

Each is about the size of what a real call reads: a loaded deck of 100 cards with every
card's data and readings, and a four-seat game partway through, with permanents, hands,
graveyards, libraries and a spell on the stack.
"""

from __future__ import annotations

from dataclasses import replace

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.model import Game
from tests.support.builders import GameBuilder, a_deck, a_game
from tests.support.library import LIBRARY

COMMANDERS = (
    "Atraxa, Praetors' Voice",
    "Kenrith, the Returned King",
    "Thrasios, Triton Hero",
    "Tymna the Weaver",
)
BASICS = ("Forest", "Island", "Mountain", "Plains", "Swamp", "Wastes")
NONBASICS = tuple(sorted(name for name in LIBRARY if name not in COMMANDERS + BASICS))
PERMANENTS = (
    "Sol Ring",
    "Arcane Signet",
    "Command Tower",
    "Llanowar Elves",
    "Serra Angel",
    "Phyrexian Arena",
    "Howling Mine",
    "Forest",
    "Island",
    "Plains",
)
HAND = ("Counterspell", "Lightning Bolt", "Cultivate", "Ponder", "Shivan Dragon")
GRAVEYARD = ("Rampant Growth", "Fireball", "Dismember")


def a_reference_deck() -> LoadedDeck:
    """A loaded deck of 100 cards: a commander, every other library card once, and basics."""
    names = list(NONBASICS)
    names += [BASICS[index % len(BASICS)] for index in range(99 - len(names))]
    return replace(a_deck(*names, commanders=(COMMANDERS[0],)), deck_id="dreference")


def a_reference_contested_game() -> Game:
    """A four-seat game in its fifth turn, with a spell on the stack and a window open."""
    builder: GameBuilder = a_game()
    for number, commander in enumerate(COMMANDERS, start=1):
        if number > 1:
            builder = builder.and_an_opposing_seat()
        library = [NONBASICS[(number + index) % len(NONBASICS)] for index in range(70)]
        builder = (
            builder.with_commander(commander)
            .with_battlefield(*PERMANENTS, entered_turn=2)
            .with_hand(*HAND)
            .with_graveyard(*GRAVEYARD)
            .with_library(*library)
            .with_life(40 - 3 * number)
        )
    builder = builder.with_spell_on_stack("Wind Drake", controller=4).with_window(
        "stack", asking=2, passed=(1,)
    )
    return builder.with_turns_taken(4).build().game
