"""`pass`: the seat a response window is asking does not respond; or a seat other than the
active seat, waited on for its reminders, does not record the triggers now."""

from __future__ import annotations

from dataclasses import replace

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import AskedKind, Error, ErrorKind, Event, Passed
from mtg_goldfishing.domain.game.acting import seats_to_act
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import Game
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.waiting import waiting_reminders
from mtg_goldfishing.domain.play.settling import settle


def _pass_on_reminders(game: Game, seat: SeatNumber) -> Passed:
    """The seat passes on every reminder of the step it has not answered."""
    for waiting_seat, reminders in waiting_reminders(game):
        if waiting_seat == seat:
            for reminder in reminders:
                reminder.passed = True
    return Passed(seat, reminder=True, step=game.step)


def _pass_in_window(game: Game, seat: SeatNumber) -> Passed:
    """The seat the window asks passes; the window counts it as having passed in succession."""
    window = game.window
    assert window is not None, "a seat asked to respond is asked in an open window"
    game.window = replace(window, asking=None, passed=(*window.passed, seat))
    newest = game.stack[-1] if game.stack else None
    return Passed(seat, newest.id if newest is not None else None, window.kind.value)


# @spec STACK-050, STACK-051, TURN-064, STACK-014, STACK-041
def pass_(game: Game, deck: LoadedDeck, seat: SeatNumber, *, decks: Decks | None = None) -> Result:
    """The calling seat passes: it does not respond when a window asks it, or passes on its
    reminders when the game waits on it for them. The window's asking then goes on: the next
    seat is asked, the top item resolves, or the window closes. `decks` gives each seat's
    deck; omitted, every seat plays `deck`."""
    every = decks or Decks.everyone_playing(game, deck)
    asked = seats_to_act(game)
    if asked is None or seat not in asked.seats:
        return Refusal.error(Error(ErrorKind.NOT_YOUR_CALL, subject="pass", asked=asked))
    changed = game.copy()
    summary: Passed
    if asked.kind is AskedKind.TRIGGER:
        summary = _pass_on_reminders(changed, seat)
    elif asked.kind is AskedKind.RESPOND:
        summary = _pass_in_window(changed, seat)
    elif asked.kind is AskedKind.CHOICE:
        return Refusal.error(Error(ErrorKind.ANSWER_WITH_CHOOSE, subject="pass", asked=asked))
    else:
        return Refusal.error(Error(ErrorKind.NOTHING_TO_PASS, subject="pass"))
    walk = settle(changed, every)
    events: list[Event] = list(walk.events)
    if walk.entered:
        events.insert(0, walk.summary)
    return Applied(changed, summary, tuple(events), tuple(walk.snapshots))
