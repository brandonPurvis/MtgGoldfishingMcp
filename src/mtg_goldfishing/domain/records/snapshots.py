"""Turn snapshots: the state of a game at the end of a turn."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.cards_in_play import face_name, is_land
from mtg_goldfishing.domain.game.model import Game, Zone
from mtg_goldfishing.domain.payment.potential import payable_in_principle
from mtg_goldfishing.domain.records.model import (
    HandCard,
    PermanentRecord,
    ReminderRecord,
    TurnSnapshot,
)


# @spec REC-011, REC-013, REC-016
def take_snapshot(game: Game, deck: LoadedDeck) -> TurnSnapshot | None:
    """The snapshot of the current turn, or None if the turn already has one."""
    if game.turn < 1 or game.turn in game.snapshot_turns:
        return None
    game.snapshot_turns.append(game.turn)
    battlefield = game.battlefield
    return TurnSnapshot(
        turn=game.turn,
        hand=tuple(
            HandCard(card.name, payable_in_principle(game, deck, card)) for card in game.hand
        ),
        battlefield=tuple(
            PermanentRecord(face_name(deck, c), c.tapped, tuple(sorted(c.counters.items())))
            for c in battlefield
        ),
        graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD)),
        lands=sum(1 for card in battlefield if is_land(deck, card)),
        mana_available=game.turn_stats.mana_available,
        mana_spent=game.turn_stats.mana_spent,
        land_drop_made=game.land_drops_used > 0,
        life=game.life,
        damage_dealt=game.damage_dealt,
        commander_damage=tuple(
            (c.name, tuple(game.commander_damage.get(c.id, [0, 0, 0]))) for c in game.commanders
        ),
        unanswered_reminders=tuple(
            ReminderRecord(r.name, r.step) for r in game.reminders if not r.answered
        ),
        written_by=game.change + 1,
    )
