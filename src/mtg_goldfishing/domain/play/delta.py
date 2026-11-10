"""Applying a delta to a game, key by key in the fixed order, with the implied bookkeeping."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AlreadySo,
    AlreadySoKind,
    CardMoved,
    CardsDiscarded,
    CardsRevealed,
    CountersChanged,
    DamageAdded,
    Error,
    ErrorKind,
    Event,
    LifeChanged,
    ManaAdded,
    NothingRevealed,
    RevealedCard,
    Tapped,
    TokensCreated,
    Untapped,
)
from mtg_goldfishing.domain.game.cards_in_play import card_of, face_name, names_of
from mtg_goldfishing.domain.game.model import (
    CardInstance,
    Destination,
    Game,
    GameStatus,
    PendingChoice,
    TokenSpec,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw, move
from mtg_goldfishing.domain.game.naming import Purpose, resolve
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.shuffling import shuffle_library
from mtg_goldfishing.domain.play.arguments import ByDestination, CounterChange, Delta, Look, Search

# Where `move` finds cards: the hand, then the public zones. Never the library.
MOVE_ZONES = (Zone.HAND, Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND)
_LIBRARY = (Destination.LIBRARY_TOP, Destination.LIBRARY_BOTTOM)


def place_all(
    game: Game,
    deck: LoadedDeck,
    cards: Sequence[CardInstance],
    destination: Destination,
    *,
    commander_stays: bool = False,
) -> list[Event]:
    """Move cards to one destination; for the library, list order is top to bottom."""
    ordered = list(reversed(cards)) if destination is Destination.LIBRARY_TOP else list(cards)
    events: list[Event] = []
    for card in ordered:
        events.extend(move(game, deck, card, destination, commander_stays=commander_stays))
    return events


def put_back(game: Game, cards: Sequence[CardInstance], destination: Destination) -> list[Event]:
    """Put cards already taken out of a library back on its top or bottom, top first."""
    ordered = list(reversed(cards)) if destination is Destination.LIBRARY_TOP else list(cards)
    for card in ordered:
        game.put(card, destination)
    return [CardMoved(card.name, Zone.LIBRARY.value, destination.value) for card in cards]


def _resolved(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    entries: ByDestination,
    zones: Sequence[Zone],
) -> list[tuple[Destination, list[CardInstance]]] | Error:
    """Resolve every name of a `{destination: [name]}` map at once, so each is a different card."""
    names = [name for _, listed in entries for name in listed]
    found = resolve(game, deck, seat, names, zones)
    if isinstance(found, Error):
        return found
    cards = iter(found[0])
    return [(destination, [next(cards) for _ in listed]) for destination, listed in entries]


def _untap(
    game: Game, deck: LoadedDeck, seat: SeatNumber, names: Sequence[str]
) -> list[Event] | Error:
    found = resolve(game, deck, seat, names, [Zone.BATTLEFIELD], purpose=Purpose.UNTAP)
    if isinstance(found, Error):
        return found
    events: list[Event] = list(found[1])
    untapped: list[str] = []
    for card in found[0]:
        if not card.tapped:
            events.append(AlreadySo(face_name(deck, card), AlreadySoKind.ALREADY_UNTAPPED))
            continue
        card.tapped = False
        untapped.append(face_name(deck, card))
    if untapped:
        events.insert(0, Untapped(tuple(untapped)))
    return events


def _tap(
    game: Game, deck: LoadedDeck, seat: SeatNumber, names: Sequence[str]
) -> list[Event] | Error:
    found = resolve(game, deck, seat, names, [Zone.BATTLEFIELD], purpose=Purpose.TAP)
    if isinstance(found, Error):
        return found
    events: list[Event] = list(found[1])
    tapped: list[str] = []
    for card in found[0]:
        if card.tapped:
            events.append(AlreadySo(face_name(deck, card), AlreadySoKind.ALREADY_TAPPED))
            continue
        card.tapped = True
        tapped.append(face_name(deck, card))
    if tapped:
        events.insert(0, Tapped(tuple(tapped)))
    return events


# @spec PLAY-086
def _tokens(game: Game, seat: SeatNumber, specs: Sequence[TokenSpec]) -> list[Event]:
    """Create tokens, owned and controlled by the seat whose delta creates them."""
    events: list[Event] = []
    for spec in specs:
        for _ in range(spec.count):
            token = CardInstance(
                id=game.new_instance_id(),
                name=spec.name,
                zone=Zone.BATTLEFIELD,
                owner=seat,
                controller=seat,
                is_token=True,
                token=spec,
            )
            game.cards.append(token)
            game.put(token, Destination.BATTLEFIELD, tapped=spec.tapped)
        events.append(TokensCreated(spec.name, spec.count))
    return events


def _counters(
    game: Game, deck: LoadedDeck, seat: SeatNumber, changes: Sequence[CounterChange]
) -> list[Event] | Error:
    events: list[Event] = []
    for change in changes:
        found = resolve(game, deck, seat, [change.card], [Zone.BATTLEFIELD])
        if isinstance(found, Error):
            return found
        events.extend(found[1])
        card = found[0][0]
        name = face_name(deck, card)
        for kind, amount in change.changes:
            before = card.counters.get(kind, 0)
            after = before + amount
            if after < 0:
                events.append(AlreadySo(name, AlreadySoKind.COUNTER_AT_ZERO, kind))
                after = 0
            if after == 0:
                card.counters.pop(kind, None)
            else:
                card.counters[kind] = after
            if after != before:
                events.append(CountersChanged(name, kind, after - before, after))
    return events


def _move(game: Game, deck: LoadedDeck, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    resolved = _resolved(game, deck, seat, delta.move, MOVE_ZONES)
    if isinstance(resolved, Error):
        return resolved
    events: list[Event] = []
    for destination, cards in resolved:
        events.extend(
            place_all(game, deck, cards, destination, commander_stays=delta.commander_stays)
        )
    return events


def _discard(game: Game, deck: LoadedDeck, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    found = resolve(game, deck, seat, delta.discard, [Zone.HAND])
    if isinstance(found, Error):
        return found
    events: list[Event] = [*found[1], CardsDiscarded(tuple(c.name for c in found[0]))]
    for card in found[0]:
        moved = move(game, deck, card, Destination.GRAVEYARD, commander_stays=delta.commander_stays)
        events.extend(e for e in moved if not isinstance(e, CardMoved) or e.commander_redirected)
    return events


def take_shuffle_place(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    placements: Sequence[tuple[Destination, list[CardInstance]]],
    *,
    commander_stays: bool = False,
) -> list[Event]:
    """Move cards from a seat's library: those leaving the library first, then shuffle that
    library, then put back the cards bound for its top or bottom, so they are placed after
    the shuffle."""
    events: list[Event] = []
    for destination, cards in placements:
        if destination not in _LIBRARY:
            events.extend(
                place_all(game, deck, cards, destination, commander_stays=commander_stays)
            )
    for destination, cards in placements:
        if destination in _LIBRARY:
            for card in cards:
                game.take_from_library(card)
    events.append(shuffle_library(game, seat))
    for destination, cards in placements:
        if destination in _LIBRARY:
            events.extend(put_back(game, cards, destination))
    return events


def _fetch(game: Game, deck: LoadedDeck, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    resolved = _resolved(game, deck, seat, delta.fetch, [Zone.LIBRARY])
    if isinstance(resolved, Error):
        if resolved.kind is ErrorKind.CARD_NOT_IN_ZONE:
            return Error(ErrorKind.NOT_IN_LIBRARY, subject=resolved.subject)
        return resolved
    return take_shuffle_place(game, deck, seat, resolved, commander_stays=delta.commander_stays)


def _revealed(card: CardInstance) -> RevealedCard:
    return RevealedCard(card.id, card.name)


# @spec GAME-120
def _pend(
    game: Game,
    seat: SeatNumber,
    source: str,
    kind: str,
    cards: Sequence[CardInstance],
    *,
    rest: Destination | None,
    from_bottom: bool = False,
) -> list[Event]:
    choice_id = game.new_choice_id()
    game.pending.append(
        PendingChoice(choice_id, seat, source, kind, [c.id for c in cards], rest, from_bottom)
    )
    game.status = GameStatus.PENDING_CHOICE
    return [CardsRevealed(choice_id, kind, tuple(_revealed(c) for c in cards))]


def _look(game: Game, seat: SeatNumber, look: Look, source: str) -> list[Event]:
    library = game.seat(seat).library
    ids = list(reversed(library[-look.n :])) if look.from_bottom else library[: look.n]
    if not ids:
        return [NothingRevealed("look")]
    return _pend(
        game,
        seat,
        source,
        "look",
        [game.instance(i) for i in ids],
        rest=look.rest,
        from_bottom=look.from_bottom,
    )


def _matches_filter(deck: LoadedDeck, card: CardInstance, text: str) -> bool:
    wanted = text.casefold()
    data = card_of(deck, card)
    type_lines = [face.type_line for face in data.faces] if data else []
    return any(wanted in candidate.casefold() for candidate in (*names_of(deck, card), *type_lines))


def _search(
    game: Game, deck: LoadedDeck, seat: SeatNumber, search: Search, source: str
) -> list[Event]:
    cards = [
        card
        for card in game.in_zone(Zone.LIBRARY, seat)
        if search.filter is None or _matches_filter(deck, card, search.filter)
    ]
    if not cards:
        return [shuffle_library(game, seat), NothingRevealed("search")]
    cards.sort(key=lambda c: (c.name.casefold(), c.number))
    return _pend(game, seat, source, "search", cards, rest=None)


# @spec PLAY-033, PLAY-034, PLAY-035, PLAY-036, PLAY-037, PLAY-038, PLAY-039, PLAY-040
# @spec PLAY-041, PLAY-042, PLAY-043, PLAY-044, PLAY-045, PLAY-050, PLAY-056, PLAY-058
# @spec PLAY-059, PLAY-060, PLAY-006, GAME-019, GAME-061, PAY-044
def apply_delta(
    game: Game, deck: LoadedDeck, seat: SeatNumber, delta: Delta, *, source: str
) -> list[Event] | Error:
    """Apply the acting seat's delta, in the fixed key order, whatever order it was written in.

    Mana goes to the acting seat's pool, life changes are its own, and draws, shuffles,
    looks and searches are of its own library; damage goes to a goldfish game's imaginary
    opponents. An error stops the application; the caller then discards the game it was
    applied to. `look` and `search` come last and leave a pending choice when they reveal
    anything.
    """
    events: list[Event] = []
    steps = (
        lambda: _untap(game, deck, seat, delta.untap) if delta.untap else [],
        lambda: _tap(game, deck, seat, delta.tap) if delta.tap else [],
        lambda: _mana(game, seat, delta),
        lambda: _tokens(game, seat, delta.tokens),
        lambda: _counters(game, deck, seat, delta.counters),
        lambda: _move(game, deck, seat, delta) if delta.move else [],
        lambda: _discard(game, deck, seat, delta) if delta.discard else [],
        lambda: _fetch(game, deck, seat, delta) if delta.fetch else [],
        lambda: draw(game, seat, delta.draw) if delta.draw else [],
        lambda: _life(game, seat, delta),
        lambda: _damage(game, delta),
        lambda: [shuffle_library(game, seat)] if delta.shuffle else [],
        lambda: _look(game, seat, delta.look, source) if delta.look else [],
        lambda: _search(game, deck, seat, delta.search, source) if delta.search else [],
    )
    for step in steps:
        done = step()
        if isinstance(done, Error):
            return done
        events.extend(done)
    return events


def _mana(game: Game, seat: SeatNumber, delta: Delta) -> list[Event]:
    if not delta.mana:
        return []
    making = game.seat(seat)
    making.mana_pool = making.mana_pool.add(delta.mana)
    return [ManaAdded(str(delta.mana))]


def _life(game: Game, seat: SeatNumber, delta: Delta) -> list[Event]:
    if not delta.life:
        return []
    changing = game.seat(seat)
    changing.life += delta.life
    return [LifeChanged(delta.life, changing.life)]


def _damage(game: Game, delta: Delta) -> list[Event]:
    if not delta.damage:
        return []
    imaginary = game.imaginary_opponents
    imaginary.damage_dealt += delta.damage
    return [DamageAdded(delta.damage, imaginary.damage_dealt)]
