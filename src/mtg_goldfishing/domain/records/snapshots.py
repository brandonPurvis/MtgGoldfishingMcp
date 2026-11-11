"""Turn snapshots: the state of a game at the end of a turn."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.cards_in_play import face_name, is_land
from mtg_goldfishing.domain.game.model import OPPONENTS, Game, Zone
from mtg_goldfishing.domain.payment.potential import payable_in_principle
from mtg_goldfishing.domain.records.model import (
    HandCard,
    PermanentRecord,
    ReminderRecord,
    TurnSnapshot,
)


# @spec REC-011, REC-013, REC-016, REC-070
def take_snapshot(game: Game, deck: LoadedDeck) -> TurnSnapshot | None:
    """The snapshot of the current turn, describing the active seat, or None if the turn
    already has one or no turn has begun."""
    if game.turn < 1 or game.active is None or game.turn in game.snapshot_turns:
        return None
    game.snapshot_turns.append(game.turn)
    described = game.active_seat
    seat = described.number
    battlefield = game.battlefield_of(seat)
    imaginary = game.imaginary
    return TurnSnapshot(
        turn=game.turn,
        hand=tuple(
            HandCard(card.name, payable_in_principle(game, deck, seat, card))
            for card in game.hand_of(seat)
        ),
        battlefield=tuple(
            PermanentRecord(face_name(deck, c), c.tapped, tuple(sorted(c.counters.items())))
            for c in battlefield
        ),
        graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD, seat)),
        lands=sum(1 for card in battlefield if is_land(deck, card)),
        mana_available=described.turn_stats.mana_available,
        mana_spent=described.turn_stats.mana_spent,
        land_drop_made=described.land_drops_used > 0,
        life=described.life,
        damage_dealt=imaginary.damage_dealt if imaginary else 0,
        commander_damage=tuple(
            (c.name, tuple(imaginary.commander_damage.get(c.id, [0] * OPPONENTS)))
            for c in game.commanders_of(seat)
        )
        if imaginary
        else (),
        unanswered_reminders=tuple(
            ReminderRecord(r.name, r.step) for r in described.reminders if not r.answered
        ),
        written_by=game.change + 1,
    )
