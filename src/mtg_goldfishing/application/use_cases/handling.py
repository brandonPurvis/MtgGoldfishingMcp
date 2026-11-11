"""What every use case shares: the ports, the call record, and the steps of a call about a game.

A call about an existing game holds the game's lock, loads the game and every seat's deck,
and hands them to the tool's own step, acting as the seat the call's id names. Whatever
that step decides, the call ends in `Call.finish`: the call's saves, if any, and its call
record go into one unit of work, holding the text `Renderer` produced for the outcome. In a
contested game every answer but `get_log`'s carries the calling seat's digest, and no
record keeps an opposing seat's seat id. An applied change is announced once committed. A
call that fails unexpectedly is answered as a failure inside the service, still with its
call record when that can be added.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from mtg_goldfishing.application.outcome import Answer, DigestElement, Outcome, Status
from mtg_goldfishing.application.ports import (
    CardCatalog,
    Clock,
    DeckRepository,
    GameChanges,
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
from mtg_goldfishing.domain.events import Error, ErrorKind, Event, Refused
from mtg_goldfishing.domain.game.acting import may_call
from mtg_goldfishing.domain.game.calls import (
    accept_change,
    follow_change,
    resend_of,
)
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Applied, Refusal, Resent
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.game.summary import GameSummary, summarize
from mtg_goldfishing.domain.records.log import log_entry
from mtg_goldfishing.domain.records.model import CallRecord, ContestedEntry, LogEntry
from mtg_goldfishing.domain.records.redaction import (
    opposing_seat_ids,
    redacted,
    stored_arguments,
)

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
    changes: GameChanges


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


def status_after_change(game: Game, seat: SeatNumber) -> Status:
    """`CHOICE` when the changed game waits for a choice the calling seat must answer, else
    `OK`: a seat whose call asked another seat for a choice has nothing to choose."""
    waiting = game.waiting_choice
    return Status.CHOICE if waiting is not None and waiting.seat == seat else Status.OK


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
        self.seat: SeatNumber | None = None
        """The calling seat, once its contested game is found; a goldfish game names none."""
        self.seat_ids: tuple[str, ...] = ()
        """The opposing seats' seat ids of the call's game, which its records may not keep."""
        self.announcement: tuple[str, int] | None = None
        """The game and change number an applied change saved, to announce once committed."""

    def about(self, game: Game) -> None:
        """The call concerns this game: its records keep none of its opposing seat ids."""
        self.seat_ids = opposing_seat_ids(game) if game.contested else ()

    # @spec APP-010, APP-019, APP-026, APP-034, APP-058, APP-059, APP-060, APP-084
    def finish(self, outcome: Outcome, write: Write | None = None) -> Answer:
        """Save the call's writes and its call record in one unit of work, and answer.

        The outcome holds the calling seat of a contested game and, but for `get_log`, its
        digest, assembled before rendering. When `write` cannot save, its outcome is
        answered instead, in a unit of work of its own. A change `write` saved is announced
        once the unit of work has committed, and never otherwise.
        """
        if self.seat is not None:
            outcome = replace(outcome, seat=self.seat)
        unit_of_work = self.ports.unit_of_work
        unit_of_work.begin()
        try:
            instead = write() if write is not None else None
            if instead is None:
                outcome = self._with_digest(outcome)
                rendered = self.ports.renderer.render(self.tool, outcome)
                self.ports.records.add_call(self._record(outcome, rendered.record))
        except BaseException:
            self.announcement = None
            unit_of_work.rollback()
            raise
        if instead is not None:
            self.announcement = None
            unit_of_work.rollback()
            return self.finish(instead)
        try:
            unit_of_work.commit()
        except BaseException:
            self.announcement = None
            unit_of_work.rollback()
            raise
        if self.announcement is not None:
            self.ports.changes.announce(*self.announcement)
            self.announcement = None
        return Answer(outcome, rendered.response)

    # @spec APP-036, APP-037, APP-038, APP-039, APP-040, APP-079, APP-081
    def _with_digest(self, outcome: Outcome) -> Outcome:
        """The outcome with the calling seat's digest, in a contested game, but for `get_log`."""
        if self.seat is None or self.game_id is None or self.tool == GET_LOG:
            return outcome
        return replace(outcome, digest=digest(self.ports.records, self.game_id, self.seat))

    # @spec APP-020
    def guarded[T](self, attempt: Callable[[], T]) -> T | Answer:
        """The attempt's result, or, if anything fails unexpectedly, an internal failure with
        its record.

        When even that record cannot be added, the internal failure is answered without it.
        """
        try:
            return attempt()
        except Exception:
            _log.exception("the %s call failed inside the service", self.tool)
        failure = an_error(Error(ErrorKind.INTERNAL_FAILURE), self.game)
        try:
            return self.finish(failure)
        except Exception:
            _log.exception("the %s call's record of its failure could not be added", self.tool)
        return Answer(failure, self.ports.renderer.render(self.tool, failure).response)

    # @spec REC-052, REC-053, REC-057, REC-058, REC-059, REC-065
    def _record(self, outcome: Outcome, response: str) -> CallRecord:
        """The call record, keeping no opposing seat id of the call's game: a `game_id` that
        names one is kept as the game id, and any other occurrence is redacted."""
        arguments = copy.deepcopy(dict(self.arguments))
        return CallRecord(
            time=self.time,
            game_id=self.game_id,
            tool=self.tool,
            arguments=stored_arguments(arguments, self.game_id or "", self.seat_ids),
            status=outcome.status.value,
            response=redacted(response, self.seat_ids),
            is_override=carries_override(self.arguments),
            change=None if outcome.game is None else outcome.game.change,
            seat=self.seat,
        )


# ---------------------------------------------------------------------------------- digests

GET_LOG = "get_log"
"""The one call given no digest: its JSON is for a program, and it does not move a baseline."""


def _as_stored_for(made: ContestedEntry, seat: SeatNumber) -> tuple[Event, ...]:
    """An entry's events as the seat may see them, taken as stored: its own list in
    `private` when it has one, the `public` list otherwise."""
    return next((shown.events for shown in made.private if shown.seat == seat), made.public)


def _made_by_another(entry: LogEntry, seat: SeatNumber) -> ContestedEntry | None:
    made = entry.contested
    if made is None or made.seat is None or made.seat == seat:
        return None
    return made


def digest(records: RecordStore, game_id: str, seat: SeatNumber) -> tuple[DigestElement, ...]:
    """The changes other seats made since the seat's digest baseline, oldest first: every
    change since the game began when it has none. The entry of `new_game`, made by no seat,
    and the seat's own entries are in no digest."""
    baseline = records.digest_baseline(game_id, seat)
    elements: list[DigestElement] = []
    for entry in records.read(game_id, since=baseline).entries:
        made = _made_by_another(entry, seat)
        if made is not None and made.seat is not None:
            elements.append(DigestElement(made.seat, entry.seq, _as_stored_for(made, seat)))
    return tuple(elements)


# -------------------------------------------------------------------------- calls about a game


@dataclass(frozen=True)
class Loaded:
    """A game as loaded, the version it was stored at, the calling seat, every seat's deck,
    and the game's summary as the calling seat sees it."""

    stored: StoredGame
    decks: Decks
    seat: SeatNumber
    summary: GameSummary

    @property
    def game(self) -> Game:
        return self.stored.game

    @property
    def deck(self) -> LoadedDeck:
        """The calling seat's deck."""
        return self.decks.of(self.seat)


Respond = Callable[[Call, Loaded], Answer]
"""A tool's own step, given the game it is called about."""


def find_seat(games: GameRepository, given: str) -> SeatOfGame | None:
    """The game and seat the id given as `game_id` names, or None when it names no seat."""
    seat_id = SeatId.read(given)
    return None if seat_id is None else games.find_seat(seat_id)


# @spec APP-014, APP-019, APP-053, APP-054, GAME-053, REC-051
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
    return respond(call, load(call, found))


def load(call: Call, found: SeatOfGame) -> Loaded:
    """Load the game a seat of which the call's id names, with every seat's deck, as the
    call's game; in a contested game the call is that seat's."""
    stored = call.ports.games.get(found.game_id)
    if stored is None:
        raise LookupError(f"a seat of game {found.game_id} is known, but the game is not kept")
    if stored.game.contested:
        call.seat = found.seat
    call.about(stored.game)
    decks = decks_of(call.ports.decks, stored.game)
    call.game = summarize(stored.game, decks.of(found.seat), found.seat, decks=decks)
    return Loaded(stored, decks, found.seat, call.game)


def decks_of(repository: DeckRepository, game: Game) -> Decks:
    """Every seat's loaded deck; a game played with a deck that is not kept is a defect."""
    loaded: dict[str, LoadedDeck] = {}
    for seat in game.seats:
        if seat.deck_id not in loaded:
            deck = repository.get(seat.deck_id)
            if deck is None:
                raise LookupError(f"game {game.game_id} is played with deck {seat.deck_id}")
            loaded[seat.deck_id] = deck
    return Decks({seat.number: loaded[seat.deck_id] for seat in game.seats})


Operation = Callable[[Game, Decks, SeatNumber], Applied | Refusal]
"""The domain operation a changing tool asks for, with the call's arguments already bound;
it is given the game, every seat's deck and the calling seat, which acts."""


def overridable(
    arguments: Mapping[str, object],
    operate: Callable[[Game, Decks, SeatNumber, str | None], Applied | Refusal],
) -> Operation:
    """An operation given the call's `override`, which must be text when present."""

    def operation(game: Game, decks: Decks, seat: SeatNumber) -> Applied | Refusal:
        override = text(arguments, "override")
        if isinstance(override, Error):
            return Refusal.error(override)
        return operate(game, decks, seat, override)

    return operation


# @spec APP-009, APP-017, APP-018, APP-021, APP-023, APP-057, REC-002, GAME-052, GAME-054
# @spec APP-055, APP-056, APP-085, APP-086, GAME-078, GAME-118
def change_game(
    ports: Ports, tool: str, arguments: Mapping[str, object], operation: Operation
) -> Answer:
    """Answer a call that changes a game.

    A resend of the calling seat's most recent change is answered with the original report
    and changes nothing, whatever the game's state. Any other call must be one the game
    accepts from the calling seat now — by its status in a goldfish game, from the seat to
    act in a contested one — and must follow the game's change number. The domain operation
    is applied with the calling seat as the acting seat. An applied result is counted as the
    game's next change and saved with its log entry and snapshots in one unit of work; a
    refusal saves nothing about the game.
    """

    def respond(call: Call, loaded: Loaded) -> Answer:
        game, seat = loaded.game, loaded.seat
        after = whole_number(arguments, "after")
        resent = resend_of(game, seat, tool, arguments, None if isinstance(after, Error) else after)
        if resent is not None:
            return _answer_resend(call, loaded, resent)
        not_accepted = may_call(game, seat, tool)
        if not_accepted is not None:
            return call.finish(an_error(not_accepted, loaded.summary))
        if isinstance(after, Error):
            return call.finish(an_error(after, loaded.summary))
        followed = follow_change(game, seat, tool, arguments, after)
        if isinstance(followed, Resent):
            return _answer_resend(call, loaded, followed)
        if isinstance(followed, Refusal):
            return call.finish(refused(followed, loaded.summary))
        result = operation(game, loaded.decks, seat)
        if isinstance(result, Refusal):
            return call.finish(refused(result, loaded.summary))
        return _save_change(call, loaded, accept_change(result, seat, tool, arguments))

    return answer_about_game(ports, tool, arguments, respond)


# @spec APP-082, APP-083
def _answer_resend(call: Call, loaded: Loaded, resent: Resent) -> Answer:
    """The original report again, as the calling seat may see it, with nothing saved but
    the call record."""
    status = status_after_change(resent.game, loaded.seat)
    summary, events = _seen(loaded.seat, resent.summary, resent.events)
    return call.finish(Outcome(status, summary, events, loaded.summary))


def _seen(
    seat: SeatNumber, summary: Event, events: tuple[Event, ...]
) -> tuple[Event, tuple[Event, ...]]:
    """A call's summary and events as the calling seat may see them."""
    (shown, *rest) = as_seen_by((summary, *events), seat)
    return shown, tuple(rest)


def _save_change(call: Call, loaded: Loaded, applied: Applied) -> Answer:
    changed = applied.game
    entry = log_entry(
        tool=call.tool,
        arguments=call.arguments,
        before=loaded.game,
        after=changed,
        summary=applied.summary,
        events=applied.events,
        seat=loaded.seat,
    )
    summary, events = _seen(loaded.seat, applied.summary, applied.events)
    outcome = Outcome(
        status_after_change(changed, loaded.seat),
        summary,
        events,
        summarize(changed, loaded.deck, loaded.seat, decks=loaded.decks),
    )

    def write() -> Outcome | None:
        if not call.ports.games.save(changed, version=loaded.stored.version):
            return an_error(Error(ErrorKind.CHANGED_UNDERNEATH), loaded.summary)
        call.ports.records.append_entry(changed.game_id, entry)
        for snapshot in applied.snapshots:
            call.ports.records.add_snapshot(changed.game_id, snapshot)
        call.announcement = (changed.game_id, changed.change)
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
        not_accepted = may_call(loaded.game, loaded.seat, tool)
        if not_accepted is not None:
            return call.finish(an_error(not_accepted, loaded.summary))
        return call.finish(read(call, loaded))

    return answer_about_game(ports, tool, arguments, respond)
