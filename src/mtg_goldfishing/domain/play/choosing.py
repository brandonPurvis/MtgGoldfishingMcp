"""`choose`: finish a `look` or `search` by saying where each revealed card goes."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    CardMoved,
    ChoiceResolved,
    Error,
    ErrorKind,
    Event,
    Placement,
)
from mtg_goldfishing.domain.game.model import CardInstance, Destination, Game, GameStatus
from mtg_goldfishing.domain.game.naming import matches
from mtg_goldfishing.domain.game.notices import examine_end_conditions
from mtg_goldfishing.domain.game.results import Applied, Refusal, Result
from mtg_goldfishing.domain.play.arguments import read_rest_order, read_selections
from mtg_goldfishing.domain.play.delta import place_all, take_shuffle_place


def _among(
    deck: LoadedDeck,
    candidates: Sequence[CardInstance],
    names: Sequence[str],
    taken: list[CardInstance],
) -> list[CardInstance] | Error:
    """Resolve names among revealed cards, each to a different card, in reveal order."""
    found: list[CardInstance] = []
    for name in names:
        matching = [card for card in candidates if matches(deck, card, name)]
        if not matching:
            return Error(ErrorKind.NOT_REVEALED, subject=name)
        free = [card for card in matching if all(card.id != t.id for t in taken)]
        if not free:
            return Error(
                ErrorKind.TOO_FEW_MATCHING,
                subject=name,
                number=len(matching),
                expected=sum(1 for n in names if n.strip().casefold() == name.strip().casefold()),
            )
        taken.append(free[0])
        found.append(free[0])
    return found


def _placements(events: Sequence[Event]) -> tuple[Placement, ...]:
    return tuple(Placement(e.card, e.to) for e in events if isinstance(e, CardMoved))


# @spec PLAY-001, PLAY-051, PLAY-052, PLAY-062, PLAY-063, PLAY-064, PLAY-065, PLAY-066
# @spec PLAY-067
def choose(
    game: Game,
    deck: LoadedDeck,
    *,
    choice_id: object,
    selections: object,
    rest_order: object = None,
) -> Result:
    """Place each selected revealed card; for a look, the rest go to the look's destination.

    For a library list, list order is top to bottom. Cards selected to the top of the library
    go above any of a look's rest that also go to the top. After a search the library is
    shuffled before any selected card is put on its top or bottom.
    """
    pending = game.pending_choice
    if pending is None or not isinstance(choice_id, str) or choice_id.strip() != pending.choice_id:
        return Refusal.error(Error(ErrorKind.WRONG_CHOICE, subject=str(choice_id)))
    chosen = read_selections(selections)
    if isinstance(chosen, Error):
        return Refusal.error(chosen)
    order = read_rest_order(rest_order)
    if isinstance(order, Error):
        return Refusal.error(order)

    changed = game.copy()
    revealed = [changed.instance(instance_id) for instance_id in pending.revealed]
    taken: list[CardInstance] = []
    selected: list[tuple[Destination, list[CardInstance]]] = []
    for destination, names in chosen:
        found = _among(deck, revealed, names, taken)
        if isinstance(found, Error):
            return Refusal.error(found)
        selected.append((destination, found))
    unselected = [card for card in revealed if all(card.id != t.id for t in taken)]

    events: list[Event] = []
    if pending.rest is None:
        events.extend(take_shuffle_place(changed, deck, selected))
    else:
        ordered = _among(deck, unselected, order, [])
        if isinstance(ordered, Error):
            return Refusal.error(ordered)
        named = {card.id for card in ordered}
        rest = ordered + [card for card in unselected if card.id not in named]
        events.extend(place_all(changed, deck, rest, pending.rest))
        for destination, cards in selected:
            events.extend(place_all(changed, deck, cards, destination))
    changed.pending_choice = None
    changed.status = GameStatus.ACTIVE
    reported = [e for e in events if not isinstance(e, CardMoved) or e.commander_redirected]
    reported.extend(examine_end_conditions(changed))
    return Applied(changed, ChoiceResolved(_placements(events)), tuple(reported))
