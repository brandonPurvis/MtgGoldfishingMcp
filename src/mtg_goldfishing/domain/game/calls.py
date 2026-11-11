"""Which tools a game accepts in each status, and the change number."""

from __future__ import annotations

from collections.abc import Mapping

from mtg_goldfishing.domain.events import AlreadyApplied, Error, ErrorKind
from mtg_goldfishing.domain.game.asking import follow_asked_since
from mtg_goldfishing.domain.game.model import Game, GameStatus, LastChange, arguments_without_after
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent
from mtg_goldfishing.domain.game.seats import SeatNumber

SERVICE_TOOLS = (
    "load_deck",
    "new_game",
    "mulligan",
    "get_state",
    "play",
    "effect",
    "choose",
    "attack",
    "advance",
    "pass",
    "wait",
    "end_game",
    "get_log",
)
"""Every tool of the service, in the order the service lists them."""

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


# @spec GAME-036, GAME-054, GAME-126
def resend_of(
    game: Game,
    seat: SeatNumber,
    tool: str,
    arguments: Mapping[str, object],
    after: int | None,
) -> Resent | None:
    """The calling seat's most recent change's original report when the call resends it.

    A call resends that change when its tool and arguments other than `after` are the same
    and its `after` is one less than that change's number. A resend is recognised whatever
    the game's status, so it is asked before the status is. None when it is no resend.
    """
    last = game.seat(seat).last_change
    if (
        after is not None
        and last is not None
        and after == last.change - 1
        and last.tool == tool
        and last.arguments == arguments_without_after(arguments)
    ):
        return Resent(game, last.summary, (*last.events, AlreadyApplied(last.change)))
    return None


# @spec GAME-035, GAME-036, GAME-037, GAME-127
def follow_change(
    game: Game,
    seat: SeatNumber,
    tool: str,
    arguments: Mapping[str, object],
    after: int | None,
) -> Resent | Refusal | None:
    """Whether a changing call follows the game's change number.

    None means apply the call. A resend of the calling seat's most recent change is answered
    with that change's original report; any other stale `after` is an error.
    """
    if after is None or after == game.change:
        return None
    resent = resend_of(game, seat, tool, arguments, after)
    if resent is not None:
        return resent
    return Refusal.error(Error(ErrorKind.STALE_CHANGE, number=game.change))


# @spec GAME-033, GAME-180, GAME-182
def accept_change(
    applied: Applied,
    seat: SeatNumber,
    tool: str,
    arguments: Mapping[str, object],
    *,
    before: Game | None = None,
) -> Applied:
    """Count an applied call as the game's next change, whichever seat made it, remember it
    as the calling seat's most recent change, and keep the change since which the seats to
    act have been asked. `before` is the game the call was applied to; None for the call
    that creates the game."""
    game = applied.game
    game.change += 1
    game.seat(seat).last_change = LastChange(
        tool, arguments_without_after(arguments), applied.summary, applied.events, game.change
    )
    follow_asked_since(before, game)
    return applied
