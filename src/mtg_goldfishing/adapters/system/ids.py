"""Game ids and seeds from the operating system's source of secure randomness."""

from __future__ import annotations

import secrets
import string

from mtg_goldfishing.application.ports import IdSource

GAME_ID_ALPHABET = string.ascii_lowercase + string.digits
GAME_ID_LENGTH = 10
SEED_LIMIT = 2**63
"""Seeds are drawn from 1 up to, but not including, this."""


# @spec GAME-004, GAME-006, GAME-077
class RandomIdSource(IdSource):
    """Ten random lower-case letters or digits for a game id or a seat id; a random positive
    seed."""

    def new_game_id(self) -> str:
        return "".join(secrets.choice(GAME_ID_ALPHABET) for _ in range(GAME_ID_LENGTH))

    def new_seat_id(self) -> str:
        return self.new_game_id()

    def new_seed(self) -> int:
        return 1 + secrets.randbelow(SEED_LIMIT - 1)
