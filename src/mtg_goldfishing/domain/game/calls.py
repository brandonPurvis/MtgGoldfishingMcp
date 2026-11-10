"""Which tools a game accepts in each status, and the change number."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.domain.events import AlreadyApplied, Error, ErrorKind
from mtg_goldfishing.domain.game.model import Game, GameStatus, LastChange, arguments_without_after
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent

GAME_TOOLS = (
    "mulligan",
    "get_state",
    "play",
    "effect",
    "choose",
    "attack",
    "advance",
    "end_game",
    "get_log",
)

ACCEPTED: dict[GameStatus, tuple[str, ...]] = {
    GameStatus.MULLIGAN: ("mulligan", "get_state", "end_game", "get_log"),
    GameStatus.ACTIVE: tuple(t for t in GAME_TOOLS if t not in ("mulligan", "choose")),
    GameStatus.PENDING_CHOICE: ("get_state", "choose", "end_game", "get_log"),
    GameStatus.ENDED: ("get_state", "get_log"),
}


# @spec GAME-048, GAME-049, GAME-050, GAME-051, GAME-052
def check_accepted(game: Game, tool: str) -> Error | None:
    """An error naming the status and the tools it accepts, or None if the tool is accepted."""
    accepted = ACCEPTED[game.status]
    if tool in accepted:
        return None
    return Error(
        ErrorKind.NOT_ACCEPTED_IN_STATUS, subject=tool, zone=game.status.value, names=accepted
    )


# @spec GAME-036, GAME-054
def resend_of(
    game: Game, tool: str, arguments: Mapping[str, object], after: int | None
) -> Resent | None:
    """The most recent change's original report when the call resends it, else None.

    A resend is recognised whatever the game's status, so it is asked before the status is.
    """
    last = game.last_change
    if (
        after is not None
        and after == game.change - 1
        and last is not None
        and last.tool == tool
        and last.arguments == arguments_without_after(arguments)
    ):
        return Resent(game, last.summary, (*last.events, AlreadyApplied(game.change)))
    return None


# @spec GAME-035, GAME-036, GAME-037
def follow_change(
    game: Game, tool: str, arguments: Mapping[str, object], after: int | None
) -> Resent | Refusal | None:
    """Whether a changing call follows the game's change number.

    None means apply the call. A resend of the most recent change is answered with that
    change's original report; any other stale `after` is an error.
    """
    if after is None or after == game.change:
        return None
    resent = resend_of(game, tool, arguments, after)
    if resent is not None:
        return resent
    return Refusal.error(Error(ErrorKind.STALE_CHANGE, number=game.change))


# @spec GAME-033
def accept_change(applied: Applied, tool: str, arguments: Mapping[str, object]) -> Applied:
    """Count an applied call as the game's next change and remember it."""
    game = applied.game
    game.change += 1
    game.last_change = LastChange(
        tool, arguments_without_after(arguments), applied.summary, applied.events
    )
    return applied
