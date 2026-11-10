"""What an operation on a game returns: an applied result or a refusal."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mtg_goldfishing.domain.events import ChecksOverridden, Error, Event, FailedCheck
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.records.model import TurnSnapshot


@dataclass(frozen=True)
class Applied:
    """The changed game, the headline event and everything else worth telling, in order.

    `snapshots` holds any turn snapshot written while the call was applied.
    """

    game: Game
    summary: Event
    events: tuple[Event, ...] = ()
    snapshots: tuple[TurnSnapshot, ...] = ()


@dataclass(frozen=True)
class Resent:
    """A resend of the most recent change: its original report, and nothing applied."""

    game: Game
    summary: Event
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Refusal:
    """Errors or failed rule checks. The game passed in is untouched."""

    errors: tuple[Error, ...] = ()
    checks: tuple[FailedCheck, ...] = ()

    @classmethod
    def error(cls, error: Error) -> Refusal:
        return cls(errors=(error,))


Result = Applied | Refusal


@dataclass
class Problems:
    """Collects the errors and failed checks found while checking a call."""

    errors: list[Error] = field(default_factory=list)
    checks: list[FailedCheck] = field(default_factory=list)

    def add(self, problem: Error | FailedCheck | Refusal | None) -> None:
        if isinstance(problem, Error):
            self.errors.append(problem)
        elif isinstance(problem, FailedCheck):
            self.checks.append(problem)
        elif isinstance(problem, Refusal):
            self.errors.extend(problem.errors)
            self.checks.extend(problem.checks)

    def extend(self, problems: Sequence[Error | FailedCheck]) -> None:
        for problem in problems:
            self.add(problem)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def judge(self, override: str | None) -> Refusal | ChecksOverridden | None:
        """Errors refuse whatever the override; failed checks refuse unless overridden.

        Returns the refusal, the record of overridden checks, or None when all is well.
        """
        if self.errors:
            return Refusal(tuple(self.errors), tuple(self.checks))
        if not self.checks:
            return None
        if override:
            return ChecksOverridden(tuple(self.checks), override)
        return Refusal(checks=tuple(self.checks))
