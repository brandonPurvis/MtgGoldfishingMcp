"""The steps of a turn."""

from __future__ import annotations

from enum import Enum


class Step(Enum):
    """One of the twelve steps of a turn, in order."""

    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"
    MAIN1 = "main1"
    BEGIN_COMBAT = "begin_combat"
    DECLARE_ATTACKERS = "declare_attackers"
    DECLARE_BLOCKERS = "declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    END_COMBAT = "end_combat"
    MAIN2 = "main2"
    END = "end"
    CLEANUP = "cleanup"

    @property
    def index(self) -> int:
        return STEPS.index(self)

    @property
    def next(self) -> Step:
        """The step after this one; untap follows cleanup."""
        return STEPS[(self.index + 1) % len(STEPS)]

    @property
    def is_main(self) -> bool:
        return self in (Step.MAIN1, Step.MAIN2)

    @classmethod
    def named(cls, name: str) -> Step | None:
        try:
            return cls(name.strip().lower())
        except ValueError:
            return None


STEPS: tuple[Step, ...] = tuple(Step)
