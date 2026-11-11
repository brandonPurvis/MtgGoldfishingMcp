"""Evasion on blocks in a contested game: what evasion the game holds for an attacker, and the
rule checks a block fails when the attacker's evasion forbids it.

| Attacker has     | A blocker may block it only if it has |
|------------------|---------------------------------------|
| flying           | flying or reach                       |
| horsemanship     | horsemanship                          |
| can't be blocked | (no blocker may)                      |

An attacker has an evasion of its own, granted by a permanent its controller controls, or
listed for it in the declaring `attack`'s `evasion`; a blocker has flying, reach or
horsemanship of its own or granted by a permanent the answering seat controls. Each card is
read as the game reads a card instance, as it stands at the moment of asking.
"""

from __future__ import annotations

from mtg_goldfishing.domain.events import CheckKind, Evasion, FailedCheck, HeldEvasion
from mtg_goldfishing.domain.game.cards_in_play import face_name, keyword_held
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import CardInstance, Game

EVASION_ORDER = (Evasion.FLYING, Evasion.HORSEMANSHIP, Evasion.CANT_BE_BLOCKED)
"""The order evasions are checked and shown in."""

_READING_OF = {
    Evasion.FLYING: "flying",
    Evasion.HORSEMANSHIP: "horsemanship",
    Evasion.CANT_BE_BLOCKED: "cant_be_blocked",
}
_ANSWERED_BY = {
    Evasion.FLYING: ("flying", "reach"),
    Evasion.HORSEMANSHIP: ("horsemanship",),
    Evasion.CANT_BE_BLOCKED: (),
}


# @spec CMBT-080, CMBT-081, CMBT-087, CMBT-089
def held_evasion(game: Game, decks: Decks, attacker: CardInstance) -> tuple[HeldEvasion, ...]:
    """The evasion the game holds for an attacker of the declared attack, in the order
    flying, horsemanship, can't be blocked, each once: read (with the reading's assumptions),
    listed in the declaring `attack`'s `evasion`, or both."""
    attack = game.declared_attack
    listed = set(attack.evasion.get(attacker.id, ())) if attack is not None else set()
    held: list[HeldEvasion] = []
    for evasion in EVASION_ORDER:
        reading = keyword_held(
            game, decks.of(attacker.owner), attacker, _READING_OF[evasion], decks
        )
        if reading is None and evasion not in listed:
            continue
        held.append(
            HeldEvasion(
                evasion,
                read=reading is not None,
                listed=evasion in listed,
                assumptions=reading.assumptions if reading is not None else (),
            )
        )
    return tuple(held)


def _may_answer(game: Game, decks: Decks, blocker: CardInstance, evasion: Evasion) -> bool:
    """Whether a blocker has a keyword that lets it block an attacker with this evasion."""
    return any(
        keyword_held(game, decks.of(blocker.owner), blocker, keyword, decks) is not None
        for keyword in _ANSWERED_BY[evasion]
    )


# @spec CMBT-083, CMBT-084, CMBT-085, CMBT-086, CMBT-088, CMBT-090
def evasion_checks(
    game: Game, decks: Decks, blocker: CardInstance, attacker: CardInstance
) -> list[FailedCheck]:
    """A failed rule check for each evasion of the attacker that forbids this blocker to
    block it, naming the blocker, the attacker and the evasion with where it is held from."""
    return [
        FailedCheck(
            CheckKind.EVASION_FORBIDS_BLOCK,
            subject=face_name(decks.of(blocker.owner), blocker),
            attacker=face_name(decks.of(attacker.owner), attacker),
            evasion=held,
        )
        for held in held_evasion(game, decks, attacker)
        if not _may_answer(game, decks, blocker, held.evasion)
    ]
