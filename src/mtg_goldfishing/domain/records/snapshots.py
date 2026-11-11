"""Turn snapshots: the state of a game at the end of a turn."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.cards_in_play import face_name, is_land
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import OPPONENTS, Game, Seat, Zone
from mtg_goldfishing.domain.payment.potential import payable_in_principle
from mtg_goldfishing.domain.records.model import (
    ContestedSnapshot,
    HandCard,
    PermanentRecord,
    ReminderRecord,
    TurnSnapshot,
)


# @spec REC-011, REC-013, REC-016, REC-070, REC-045, REC-048, REC-049, REC-081
def take_snapshot(game: Game, deck: LoadedDeck, decks: Decks | None = None) -> TurnSnapshot | None:
    """The snapshot of the current turn, describing the active seat, whose deck is `deck`, or
    None if the table turn already has one or no turn has begun. Each permanent is read from
    its owner's deck (`decks`; omitted, every seat plays `deck`).

    In a contested game the snapshot's turn is the active seat's own turn count, and it is
    kept by table turn beside every seat's life and the unanswered reminders of every seat.
    """
    if game.turn < 1 or game.active is None or game.turn in game.snapshot_turns:
        return None
    every = decks or Decks.everyone_playing(game, deck)
    game.snapshot_turns.append(game.turn)
    described = game.active_seat
    seat = described.number
    battlefield = game.battlefield_of(seat)
    imaginary = game.imaginary
    return TurnSnapshot(
        turn=described.turns if game.contested else game.turn,
        hand=tuple(
            HandCard(card.name, payable_in_principle(game, deck, seat, card, every))
            for card in game.hand_of(seat)
        ),
        battlefield=tuple(
            PermanentRecord(
                face_name(every.of(c.owner), c), c.tapped, tuple(sorted(c.counters.items()))
            )
            for c in battlefield
        ),
        graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD, seat)),
        lands=sum(1 for card in battlefield if is_land(every.of(card.owner), card)),
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
        unanswered_reminders=_unanswered(game, described),
        written_by=game.change + 1,
        contested=_contested(game, described) if game.contested else None,
    )


# @spec REC-069
def _unanswered(game: Game, described: Seat) -> tuple[ReminderRecord, ...]:
    """A goldfish game's unanswered reminders of the turn; in a contested game every seat's
    unanswered reminders issued during this table turn, each naming its seat."""
    if not game.contested:
        return tuple(ReminderRecord(r.name, r.step) for r in described.reminders if not r.answered)
    return tuple(
        ReminderRecord(r.name, r.step, seat=seat.number)
        for seat in game.seats
        for r in seat.reminders
        if r.turn == game.turn and not r.answered
    )


# @spec REC-046, REC-047, REC-079
def _contested(game: Game, described: Seat) -> ContestedSnapshot:
    """The described seat, the table turn and round, every seat's life (an eliminated seat's
    as it left), the eliminated seats, and each of the described seat's commanders' combat
    damage to every other seat, zeros and eliminated seats included."""
    others = [seat for seat in game.seats if seat.number != described.number]
    return ContestedSnapshot(
        seat=described.number,
        table_turn=game.turn,
        round=game.round,
        lives=tuple((seat.number, seat.life) for seat in game.seats),
        eliminated=tuple(sorted(seat.number for seat in game.seats if seat.eliminated)),
        commander_damage=tuple(
            (
                commander.name,
                tuple(
                    (other.number, described.commander_damage_to(commander, other.number))
                    for other in others
                ),
            )
            for commander in game.commanders_of(described.number)
        ),
    )
