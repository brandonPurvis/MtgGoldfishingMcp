"""What every use case shares: the ports, the call record, and the steps of a call about a game.

A call about an existing game holds the game's lock, loads the game and its deck, and hands
them to the tool's own step. Whatever that step decides, the call ends in `Call.finish`:
the call's saves, if any, and its call record go into one unit of work, holding the text
`Renderer` produced for the outcome. A call that fails unexpectedly is answered as a
failure inside the service, still with its call record.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from mtg_goldfishing.application.outcome import Answer, Outcome, Status
from mtg_goldfishing.application.ports import (
    CardCatalog,
    Clock,
    DeckRepository,
    GameLocks,
    GameRepository,
    IdSource,
    RecordStore,
    Renderer,
    StoredGame,
    UnitOfWork,
)
from mtg_goldfishing.application.use_cases.arguments import malformed, text, whole_number
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, Refused
from mtg_goldfishing.domain.game.calls import accept_change, check_accepted, follow_change
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent
from mtg_goldfishing.domain.game.summary import GameSummary, summarize
from mtg_goldfishing.domain.records.log import log_entry
from mtg_goldfishing.domain.records.model import CallRecord

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ports:
    """Everything a use case reaches the outside world through."""

    games: GameRepository
    decks: DeckRepository
    records: RecordStore
    unit_of_work: UnitOfWork
    catalog: CardCatalog
    locks: GameLocks
    ids: IdSource
    clock: Clock
    renderer: Renderer


Write = Callable[[], Outcome | None]
"""A call's saves, made inside its unit of work.

Returns None once everything is saved, or the outcome to answer instead when nothing could
be saved; the unit of work is then rolled back.
"""


# ---------------------------------------------------------------------------------- outcomes


def refused(refusal: Refusal, game: GameSummary | None) -> Outcome:
    """A refusal's outcome: `ERROR` when it holds an error, else `REJECTED`."""
    status = Status.ERROR if refusal.errors else Status.REJECTED
    return Outcome(status, Refused(refusal.errors, refusal.checks), (), game)


def an_error(error: Error, game: GameSummary | None) -> Outcome:
    return refused(Refusal.error(error), game)


def status_after_change(game: Game) -> Status:
    """`CHOICE` when the changed game waits for a choice, else `OK`."""
    return Status.OK if game.pending_choice is None else Status.CHOICE


def carries_override(arguments: Mapping[str, object]) -> bool:
    override = arguments.get("override")
    return isinstance(override, str) and bool(override)


# ---------------------------------------------------------------------------------- one call


class Call:
    """One tool call being answered. However it ends, it adds exactly one call record."""

    def __init__(
        self, ports: Ports, tool: str, arguments: Mapping[str, object], game_id: str | None
    ) -> None:
        self.ports = ports
        self.tool = tool
        self.arguments = arguments
        self.game_id = game_id
        self.time = ports.clock.now()
        self.game: GameSummary | None = None
        """The game as loaded, for an answer that must be given without the call's result."""

    # @spec APP-010, APP-019, APP-026
    def finish(self, outcome: Outcome, write: Write | None = None) -> Answer:
        """Save the call's writes and its call record in one unit of work, and answer.

        When `write` cannot save, its outcome is answered instead, in a unit of work of its own.
        """
        unit_of_work = self.ports.unit_of_work
        unit_of_work.begin()
        try:
            instead = write() if write is not None else None
            if instead is None:
                rendered = self.ports.renderer.render(self.tool, outcome)
                self.ports.records.add_call(self._record(outcome, rendered.record))
        except BaseException:
            unit_of_work.rollback()
            raise
        if instead is not None:
            unit_of_work.rollback()
            return self.finish(instead)
        try:
            unit_of_work.commit()
        except BaseException:
            unit_of_work.rollback()
            raise
        return Answer(outcome, rendered.response)

    # @spec APP-020
    def guarded(self, answer: Callable[[], Answer]) -> Answer:
        """The answer, or, if anything fails unexpectedly, an internal failure with its record."""
        try:
            return answer()
        except Exception:
            _log.exception("the %s call failed inside the service", self.tool)
            return self.finish(an_error(Error(ErrorKind.INTERNAL_FAILURE), self.game))

    def _record(self, outcome: Outcome, response: str) -> CallRecord:
        return CallRecord(
            time=self.time,
            game_id=self.game_id,
            tool=self.tool,
            arguments=copy.deepcopy(dict(self.arguments)),
            status=outcome.status.value,
            response=response,
            is_override=carries_override(self.arguments),
            change=None if outcome.game is None else outcome.game.change,
        )


# -------------------------------------------------------------------------- calls about a game


@dataclass(frozen=True)
class Loaded:
    """A game as loaded, the version it was stored at, its deck and its summary."""

    stored: StoredGame
    deck: LoadedDeck
    summary: GameSummary

    @property
    def game(self) -> Game:
        return self.stored.game


Respond = Callable[[Call, Loaded], Answer]
"""A tool's own step, given the game it is called about."""


# @spec APP-014, APP-019, GAME-053
def answer_about_game(
    ports: Ports, tool: str, arguments: Mapping[str, object], respond: Respond
) -> Answer:
    """Hold the game's lock, load the game, and answer through the tool's own step.

    A game id that names no game is an error and changes nothing.
    """
    game_id = arguments.get("game_id")
    if not isinstance(game_id, str):
        call = Call(ports, tool, arguments, None)
        return call.guarded(lambda: call.finish(an_error(malformed("game_id"), None)))
    call = Call(ports, tool, arguments, game_id)
    with ports.locks.hold(game_id):
        return call.guarded(lambda: _respond_about(call, game_id, respond))


def _respond_about(call: Call, game_id: str, respond: Respond) -> Answer:
    stored = call.ports.games.get(game_id)
    if stored is None:
        return call.finish(an_error(Error(ErrorKind.UNKNOWN_GAME, subject=game_id), None))
    deck = call.ports.decks.get(stored.game.deck_id)
    if deck is None:
        raise LookupError(f"game {game_id} is played with deck {stored.game.deck_id}, not kept")
    call.game = summarize(stored.game, deck)
    return respond(call, Loaded(stored, deck, call.game))


Operation = Callable[[Game, LoadedDeck], Applied | Refusal]
"""The domain operation a changing tool asks for, with the call's arguments already bound."""


def overridable(
    arguments: Mapping[str, object],
    operate: Callable[[Game, LoadedDeck, str | None], Applied | Refusal],
) -> Operation:
    """An operation given the call's `override`, which must be text when present."""

    def operation(game: Game, deck: LoadedDeck) -> Applied | Refusal:
        override = text(arguments, "override")
        if isinstance(override, Error):
            return Refusal.error(override)
        return operate(game, deck, override)

    return operation


# @spec APP-009, APP-017, APP-018, APP-021, APP-023, REC-002
def change_game(
    ports: Ports, tool: str, arguments: Mapping[str, object], operation: Operation
) -> Answer:
    """Answer a call that changes a game.

    The game must accept the tool in its status and the call must follow the game's change
    number. A resend is answered with the original report and changes nothing. An applied
    result is counted as the game's next change and saved with its log entry and snapshots
    in one unit of work; a refusal saves nothing about the game.
    """

    def respond(call: Call, loaded: Loaded) -> Answer:
        game = loaded.game
        not_accepted = check_accepted(game, tool)
        if not_accepted is not None:
            return call.finish(an_error(not_accepted, loaded.summary))
        after = whole_number(arguments, "after")
        if isinstance(after, Error):
            return call.finish(an_error(after, loaded.summary))
        followed = follow_change(game, tool, arguments, after)
        if isinstance(followed, Resent):
            status = status_after_change(followed.game)
            return call.finish(Outcome(status, followed.summary, followed.events, loaded.summary))
        if isinstance(followed, Refusal):
            return call.finish(refused(followed, loaded.summary))
        result = operation(game, loaded.deck)
        if isinstance(result, Refusal):
            return call.finish(refused(result, loaded.summary))
        return _save_change(call, loaded, accept_change(result, tool, arguments))

    return answer_about_game(ports, tool, arguments, respond)


def _save_change(call: Call, loaded: Loaded, applied: Applied) -> Answer:
    changed = applied.game
    entry = log_entry(
        tool=call.tool,
        arguments=call.arguments,
        before=loaded.game,
        after=changed,
        summary=applied.summary,
        events=applied.events,
    )
    outcome = Outcome(
        status_after_change(changed),
        applied.summary,
        applied.events,
        summarize(changed, loaded.deck),
    )

    def write() -> Outcome | None:
        if not call.ports.games.save(changed, version=loaded.stored.version):
            return an_error(Error(ErrorKind.CHANGED_UNDERNEATH), loaded.summary)
        call.ports.records.append_entry(changed.game_id, entry)
        for snapshot in applied.snapshots:
            call.ports.records.add_snapshot(changed.game_id, snapshot)
        return None

    return call.finish(outcome, write)


def answer_read_only(
    ports: Ports,
    tool: str,
    arguments: Mapping[str, object],
    read: Callable[[Call, Loaded], Outcome],
) -> Answer:
    """Answer a call that reads a game and changes nothing; its call record is its only save."""

    def respond(call: Call, loaded: Loaded) -> Answer:
        not_accepted = check_accepted(loaded.game, tool)
        if not_accepted is not None:
            return call.finish(an_error(not_accepted, loaded.summary))
        return call.finish(read(call, loaded))

    return answer_about_game(ports, tool, arguments, respond)
