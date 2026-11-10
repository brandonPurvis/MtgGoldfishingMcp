"""How a seat is named: its seat number in turn order and its unguessable seat id."""

from __future__ import annotations

from dataclasses import dataclass


# @spec APP-032
@dataclass(frozen=True, order=True)
class SeatNumber:
    """A seat's place in turn order, from 1; calls and responses name seats by it."""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool) or self.value < 1:
            raise ValueError(f"a seat number is a whole number from 1, not {self.value!r}")

    def __str__(self) -> str:
        return f"S{self.value}"


# @spec APP-032
@dataclass(frozen=True)
class SeatId:
    """The unguessable id naming one seat of one game; the tested seat's is the game id."""

    value: str

    def __post_init__(self) -> None:
        text = self.value
        if not isinstance(text, str) or not text or any(c.isspace() for c in text):
            raise ValueError(f"a seat id is text without spaces, not {text!r}")

    @classmethod
    def read(cls, text: object) -> SeatId | None:
        """The seat id a call gave, or None when what it gave cannot be one."""
        if not isinstance(text, str):
            return None
        try:
            return cls(text)
        except ValueError:
            return None

    def __str__(self) -> str:
        return self.value
