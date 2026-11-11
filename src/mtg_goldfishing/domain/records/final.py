"""Every seat's state at the end of a contested game, recorded in the outcome of the tested
seat's `end_game` entry as `final`."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.game.cards_in_play import face_name
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game, Seat, Zone
from mtg_goldfishing.domain.records.model import PermanentRecord, SeatFinal


# @spec REC-097, REC-098, REC-099, REC-100, REC-103
def final_state(game: Game, decks: Decks) -> tuple[SeatFinal, ...]:
    """Every seat of the game, eliminated seats included, in ascending seat number, as the
    game now stands.

    Cards are named and listed as a turn snapshot of the seat names and lists them, each
    permanent read from its owner's deck. A card on the stack is in no zone listed. An
    eliminated seat owns no cards any more, so its zones are empty.
    """
    return tuple(
        SeatFinal(
            seat=seat.number,
            life=seat.life,
            eliminated=seat.eliminated,
            hand=tuple(card.name for card in game.hand_of(seat.number)),
            battlefield=tuple(
                PermanentRecord(
                    face_name(decks.of(c.owner), c), c.tapped, tuple(sorted(c.counters.items()))
                )
                for c in game.battlefield_of(seat.number)
            ),
            graveyard=tuple(card.name for card in game.in_zone(Zone.GRAVEYARD, seat.number)),
            commander_damage_taken=tuple(
                (other.number, _damage_dealt(game, decks, other, seat))
                for other in sorted(game.seats, key=lambda s: s.number.value)
                if other.number != seat.number
            ),
        )
        for seat in sorted(game.seats, key=lambda s: s.number.value)
    )


def _damage_dealt(
    game: Game, decks: Decks, dealer: Seat, taker: Seat
) -> tuple[tuple[str, int], ...]:
    """The combat damage each commander of the dealer's deck has dealt the taker, by card
    name in name order, zeros included."""
    return tuple(
        sorted(
            (
                (name, dealer.commander_damage.get(instance_id, {}).get(str(taker.number.value), 0))
                for instance_id, name in _commanders(game, decks, dealer)
            ),
            key=lambda named: named[0].casefold(),
        )
    )


def _commanders(game: Game, decks: Decks, seat: Seat) -> Sequence[tuple[str, str]]:
    """Each commander of the seat's deck, by instance id and card name.

    A commander still in the game is read from its instance. The cards of an eliminated seat
    have left the game, so the instance ids its commanders were given remain (they were
    given in the name order of its deck's commanders) and the names are read from its deck.
    """
    held = {c.id: c.name for c in game.cards if c.is_commander and c.owner == seat.number}
    named = set(held.values())
    left_ids = [instance_id for instance_id in seat.commander_casts if instance_id not in held]
    left_names = [
        name
        for name in sorted(decks.of(seat.number).commanders, key=str.lower)
        if name not in named
    ]
    return [*held.items(), *zip(left_ids, left_names, strict=False)]
