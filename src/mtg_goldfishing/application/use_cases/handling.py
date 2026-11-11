"""What every use case shares: the ports, the call record, and the steps of a call about a game.

A call about an existing game holds the game's lock, loads the game and its deck, and hands
them to the tool's own step. Whatever that step decides, the call ends in `Call.finish`:
the call's saves, if any, and its call record go into one unit of work, holding the text
`Renderer` produced for the outcome. A call that fails unexpectedly is answered as a
failure inside the service, still with its call record when that can be added.
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
    SeatOfGame,
    StoredGame,
    UnitOfWork,
)
from mtg_goldfishing.application.use_cases.arguments import malformed, text, whole_number
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import Error, ErrorKind, Refused
from mtg_goldfishing.domain.game.calls import (
    accept_change,
    check_accepted,
    follow_change,
    resend_of,
)
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
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
    return Status.CHOICE if game.pending else Status.OK


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
        """The answer, or, if anything fails unexpectedly, an internal failure with its record.

        When even that record cannot be added, the internal failure is answered without it.
        """
        try:
            return answer()
        except Exception:
            _log.exception("the %s call failed inside the service", self.tool)
        failure = an_error(Error(ErrorKind.INTERNAL_FAILURE), self.game)
        try:
            return self.finish(failure)
        except Exception:
            _log.exception("the %s call's record of its failure could not be added", self.tool)
        return Answer(failure, self.ports.renderer.render(self.tool, failure).response)

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
    """A game as loaded, the version it was stored at, the calling seat, that seat's deck,
    and the game's summary as that seat sees it."""

    stored: StoredGame
    deck: LoadedDeck
    seat: SeatNumber
    summary: GameSummary

    @property
    def game(self) -> Game:
        return self.stored.game


Respond = Callable[[Call, Loaded], Answer]
"""A tool's own step, given the game it is called about."""


def find_seat(games: GameRepository, given: str) -> SeatOfGame | None:
    """The game and seat the id given as `game_id` names, or None when it names no seat."""
    seat_id = SeatId.read(given)
    return None if seat_id is None else games.find_seat(seat_id)


# @spec APP-014, APP-019, APP-053, APP-054, GAME-053
def answer_about_game(
    ports: Ports, tool: str, arguments: Mapping[str, object], respond: Respond
) -> Answer:
    """Find the game and seat the given id names, hold the game's lock, load the game, and
    answer through the tool's own step, acting as that seat.

    An id that names no seat of any game is an error and changes nothing. The call is
    recorded under the game the id names.
    """
    game_id = arguments.get("game_id")
    if not isinstance(game_id, str):
        call = Call(ports, tool, arguments, None)
        return call.guarded(lambda: call.finish(an_error(malformed("game_id"), None)))
    call = Call(ports, tool, arguments, game_id)

    def answer() -> Answer:
        found = find_seat(ports.games, game_id)
        if found is None:
            return call.finish(an_error(Error(ErrorKind.UNKNOWN_GAME, subject=game_id), None))
        call.game_id = found.game_id
        with ports.locks.hold(found.game_id):
            return call.guarded(lambda: _respond_about(call, found, respond))

    return call.guarded(answer)


def _respond_about(call: Call, found: SeatOfGame, respond: Respond) -> Answer:
    stored = call.ports.games.get(found.game_id)
    if stored is None:
        raise LookupError(f"a seat of game {found.game_id} is known, but the game is not kept")
    deck_id = stored.game.seat(found.seat).deck_id
    deck = call.ports.decks.get(deck_id)
    if deck is None:
        raise LookupError(f"game {found.game_id} is played with deck {deck_id}, not kept")
    call.game = summarize(stored.game, deck, found.seat)
    return respond(call, Loaded(stored, deck, found.seat, call.game))


Operation = Callable[[Game, LoadedDeck, SeatNumber], Applied | Refusal]
"""The domain operation a changing tool asks for, with the call's arguments already bound;
it is given the game, the calling seat's deck and the calling seat, which acts."""


def overridable(
    arguments: Mapping[str, object],
    operate: Callable[[Game, LoadedDeck, SeatNumber, str | None], Applied | Refusal],
) -> Operation:
    """An operation given the call's `override`, which must be text when present."""

    def operation(game: Game, deck: LoadedDeck, seat: SeatNumber) -> Applied | Refusal:
        override = text(arguments, "override")
        if isinstance(override, Error):
            return Refusal.error(override)
        return operate(game, deck, seat, override)

    return operation


# @spec APP-009, APP-017, APP-018, APP-021, APP-023, APP-057, REC-002, GAME-052, GAME-054
def change_game(
    ports: Ports, tool: str, arguments: Mapping[str, object], operation: Operation
) -> Answer:
    """Answer a call that changes a game.

    A resend of the calling seat's most recent change is answered with the original report
    and changes nothing, whatever the game's status. Any other call must be accepted in the
    game's status and must follow the game's change number. The domain operation is applied
    with the calling seat as the acting seat. An applied result is counted as the game's
    next change and saved with its log entry and snapshots in one unit of work; a refusal
    saves nothing about the game.
    """

    def respond(call: Call, loaded: Loaded) -> Answer:
        game, seat = loaded.game, loaded.seat
        after = whole_number(arguments, "after")
        resent = resend_of(game, seat, tool, arguments, None if isinstance(after, Error) else after)
        if resent is not None:
            return _answer_resend(call, loaded, resent)
        not_accepted = check_accepted(game, tool)
        if not_accepted is not None:
            return call.finish(an_error(not_accepted, loaded.summary))
        if isinstance(after, Error):
            return call.finish(an_error(after, loaded.summary))
        followed = follow_change(game, seat, tool, arguments, after)
        if isinstance(followed, Resent):
            return _answer_resend(call, loaded, followed)
        if isinstance(followed, Refusal):
            return call.finish(refused(followed, loaded.summary))
        result = operation(game, loaded.deck, seat)
        if isinstance(result, Refusal):
            return call.finish(refused(result, loaded.summary))
        return _save_change(call, loaded, accept_change(result, seat, tool, arguments))

    return answer_about_game(ports, tool, arguments, respond)


def _answer_resend(call: Call, loaded: Loaded, resent: Resent) -> Answer:
    """The original report again, with nothing saved but the call record."""
    status = status_after_change(resent.game)
    return call.finish(Outcome(status, resent.summary, resent.events, loaded.summary))


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
        summarize(changed, loaded.deck, loaded.seat),
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
