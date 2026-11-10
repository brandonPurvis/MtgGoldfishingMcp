"""`new_game`: a game on a loaded deck, shuffled and dealt."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, GameStarted
from mtg_goldfishing.domain.game.model import (
    OPENING_HAND,
    OPPONENTS,
    CardInstance,
    Game,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.game.shuffling import shuffle_library


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


# @spec GAME-001, GAME-002, GAME-003, GAME-005, GAME-006, GAME-007, GAME-008, GAME-009
def new_game(
    deck: LoadedDeck | None,
    *,
    deck_id: str,
    game_id: str,
    seed: int,
    turn_limit: object = None,
    draw_first_turn: object = None,
) -> Result:
    """Create a game: commanders to the command zone, the rest shuffled, seven dealt.

    Instance ids go to commanders first, then the other cards, each group ordered by
    lower-cased name with copies adjacent; the library starts in that order.
    """
    if deck is None:
        return Refusal.error(Error(ErrorKind.UNKNOWN_DECK, subject=deck_id))
    if turn_limit is not None and not _is_positive_int(turn_limit):
        return Refusal.error(Error(ErrorKind.BAD_TURN_LIMIT, subject=str(turn_limit)))
    if draw_first_turn is not None and not isinstance(draw_first_turn, bool):
        return Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="draw_first_turn"))
    game = Game(
        game_id=game_id,
        deck_id=deck.deck_id,
        seed=seed,
        turn_limit=turn_limit if isinstance(turn_limit, int) else None,
        draw_first_turn=draw_first_turn if isinstance(draw_first_turn, bool) else True,
    )
    for name in sorted(deck.commanders, key=str.lower):
        commander = CardInstance(game.new_instance_id(), name, Zone.COMMAND, is_commander=True)
        game.cards.append(commander)
        game.commander_casts[commander.id] = 0
        game.commander_damage[commander.id] = [0] * OPPONENTS
    for entry in sorted(deck.entries, key=lambda e: e.name.lower()):
        for _ in range(entry.count):
            card = CardInstance(game.new_instance_id(), entry.name, Zone.LIBRARY)
            game.cards.append(card)
            game.library.append(card.id)
    shuffle_library(game)
    draw(game, OPENING_HAND)
    hand = tuple(card.name for card in game.hand)
    return Applied(game, GameStarted(game_id, seed, hand))
