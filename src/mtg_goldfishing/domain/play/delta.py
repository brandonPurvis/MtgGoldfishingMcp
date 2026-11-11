"""Applying a delta to a game, key by key in the fixed order, with the implied bookkeeping.

A delta is the acting seat's. In a contested game it may reach other seats' public cards,
their life, and the control of their permanents, and ask other seats for what they must
decide; it never reaches another seat's hand or library by name or id.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.events import (
    AlreadySo,
    AlreadySoKind,
    CardMoved,
    CardsDiscarded,
    CardsRevealed,
    ChoiceAsked,
    ControlChanged,
    CountersChanged,
    DamageAdded,
    Error,
    ErrorKind,
    Event,
    LifeChanged,
    ManaAdded,
    NothingRevealed,
    RevealedCard,
    SeatDamaged,
    Tapped,
    TokensCreated,
    Untapped,
)
from mtg_goldfishing.domain.game.cards_in_play import card_of, face_name, names_of
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import (
    CardInstance,
    Destination,
    Game,
    GameStatus,
    HandLook,
    PendingChoice,
    TokenSpec,
    Zone,
)
from mtg_goldfishing.domain.game.movement import draw, move
from mtg_goldfishing.domain.game.naming import Purpose, resolve
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.shuffling import shuffle_library
from mtg_goldfishing.domain.play.arguments import (
    AskEntry,
    ByDestination,
    CounterChange,
    Delta,
    Look,
    Search,
)

# Where `move` finds cards: the hand, then the public zones. Never the library.
MOVE_ZONES = (Zone.HAND, Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND)
_LIBRARY = (Destination.LIBRARY_TOP, Destination.LIBRARY_BOTTOM)
_NAMING_ERRORS = (ErrorKind.CARD_NOT_IN_ZONE, ErrorKind.NOT_IN_LIBRARY, ErrorKind.HIDDEN_ZONE)


def place_all(
    game: Game,
    deck: LoadedDeck,
    cards: Sequence[CardInstance],
    destination: Destination,
    *,
    commander_stays: bool = False,
    decks: Decks | None = None,
    arriving_under: SeatNumber | None = None,
) -> list[Event]:
    """Move cards to one destination; for the library, list order is top to bottom.

    Each card is read from its owner's deck (`decks`; omitted, every seat plays `deck`), and
    enters the battlefield under `arriving_under`, or its owner when none is named.
    """
    every = decks or Decks.everyone_playing(game, deck)
    ordered = list(reversed(cards)) if destination is Destination.LIBRARY_TOP else list(cards)
    events: list[Event] = []
    for card in ordered:
        events.extend(
            move(
                game,
                every.of(card.owner),
                card,
                destination,
                commander_stays=commander_stays,
                arriving_under=arriving_under,
            )
        )
    return events


def put_back(game: Game, cards: Sequence[CardInstance], destination: Destination) -> list[Event]:
    """Put cards already taken out of a library back on its top or bottom, top first."""
    ordered = list(reversed(cards)) if destination is Destination.LIBRARY_TOP else list(cards)
    for card in ordered:
        game.put(card, destination)
    return [
        CardMoved(
            card.name,
            Zone.LIBRARY.value,
            destination.value,
            owner=card.owner if game.contested else None,
        )
        for card in cards
    ]


def _through_ask(game: Game, found: object) -> object:
    """In a contested game, an error about a delta's names adds that other seats' hands and
    libraries are reached through `ask`."""
    if game.contested and isinstance(found, Error) and found.kind in _NAMING_ERRORS:
        return replace(found, through_ask=True)
    return found


def _resolved(
    game: Game,
    decks: Decks,
    seat: SeatNumber,
    entries: ByDestination,
    zones: Sequence[Zone],
) -> list[tuple[Destination, list[CardInstance]]] | Error:
    """Resolve every name of a `{destination: [name]}` map at once, so each is a different card."""
    names = [name for _, listed in entries for name in listed]
    found = resolve(game, decks.of(seat), seat, names, zones, decks=decks)
    if isinstance(found, Error):
        return found
    cards = iter(found[0])
    return [(destination, [next(cards) for _ in listed]) for destination, listed in entries]


def _untap(game: Game, decks: Decks, seat: SeatNumber, names: Sequence[str]) -> list[Event] | Error:
    found = resolve(
        game, decks.of(seat), seat, names, [Zone.BATTLEFIELD], purpose=Purpose.UNTAP, decks=decks
    )
    if isinstance(found, Error):
        return found
    events: list[Event] = list(found[1])
    untapped: list[str] = []
    for card in found[0]:
        name = face_name(decks.of(card.owner), card)
        if not card.tapped:
            events.append(AlreadySo(name, AlreadySoKind.ALREADY_UNTAPPED))
            continue
        card.tapped = False
        untapped.append(name)
    if untapped:
        events.insert(0, Untapped(tuple(untapped)))
    return events


def _tap(game: Game, decks: Decks, seat: SeatNumber, names: Sequence[str]) -> list[Event] | Error:
    found = resolve(
        game, decks.of(seat), seat, names, [Zone.BATTLEFIELD], purpose=Purpose.TAP, decks=decks
    )
    if isinstance(found, Error):
        return found
    events: list[Event] = list(found[1])
    tapped: list[str] = []
    for card in found[0]:
        name = face_name(decks.of(card.owner), card)
        if card.tapped:
            events.append(AlreadySo(name, AlreadySoKind.ALREADY_TAPPED))
            continue
        card.tapped = True
        tapped.append(name)
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
    game: Game, decks: Decks, seat: SeatNumber, changes: Sequence[CounterChange]
) -> list[Event] | Error:
    events: list[Event] = []
    for change in changes:
        found = resolve(game, decks.of(seat), seat, [change.card], [Zone.BATTLEFIELD], decks=decks)
        if isinstance(found, Error):
            return found
        events.extend(found[1])
        card = found[0][0]
        name = face_name(decks.of(card.owner), card)
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


# @spec PLAY-094, PLAY-117, PLAY-118, PLAY-124
def _control(game: Game, decks: Decks, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    """Each listed permanent comes under the control of the seat it is listed under, counting
    as newly arrived for it; one already under that seat's control is left as it is."""
    names = [name for _, listed in delta.control for name in listed]
    found = resolve(game, decks.of(seat), seat, names, [Zone.BATTLEFIELD], decks=decks)
    if isinstance(found, Error):
        return found
    events: list[Event] = list(found[1])
    cards = iter(found[0])
    for controller, listed in delta.control:
        for _ in listed:
            card = next(cards)
            name = face_name(decks.of(card.owner), card)
            if card.controller == controller:
                events.append(AlreadySo(name, AlreadySoKind.ALREADY_CONTROLLED))
                continue
            card.controller = controller
            card.entered_turn = game.turn
            events.append(ControlChanged(name, controller))
    return events


def _move(game: Game, decks: Decks, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    resolved = _resolved(game, decks, seat, delta.move, MOVE_ZONES)
    if isinstance(resolved, Error):
        return resolved
    events: list[Event] = []
    for destination, cards in resolved:
        events.extend(
            place_all(
                game,
                decks.of(seat),
                cards,
                destination,
                commander_stays=delta.commander_stays,
                decks=decks,
                arriving_under=seat,
            )
        )
    return events


def _discard(game: Game, decks: Decks, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    deck = decks.of(seat)
    found = resolve(game, deck, seat, delta.discard, [Zone.HAND], decks=decks)
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


def _fetch(game: Game, decks: Decks, seat: SeatNumber, delta: Delta) -> list[Event] | Error:
    resolved = _resolved(game, decks, seat, delta.fetch, [Zone.LIBRARY])
    if isinstance(resolved, Error):
        if resolved.kind is ErrorKind.CARD_NOT_IN_ZONE:
            return Error(ErrorKind.NOT_IN_LIBRARY, subject=resolved.subject)
        return resolved
    return take_shuffle_place(
        game, decks.of(seat), seat, resolved, commander_stays=delta.commander_stays
    )


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
    hand_of: SeatNumber | None = None,
) -> list[Event]:
    """A pending choice for `seat` that reveals `cards` to it alone."""
    choice_id = game.new_choice_id()
    game.pending.append(
        PendingChoice(
            choice_id,
            seat,
            source,
            kind,
            [c.id for c in cards],
            rest,
            from_bottom,
            asked_by=seat if hand_of is not None else None,
            hand_of=hand_of,
        )
    )
    game.status = GameStatus.PENDING_CHOICE
    shown_to = seat if game.contested else None
    revealed = tuple(_revealed(c) for c in cards)
    return [CardsRevealed(choice_id, kind, revealed, shown_to, hand_of)]


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


def _life(game: Game, seat: SeatNumber, delta: Delta) -> list[Event]:
    """A number changes the acting seat's life; a map, each named seat's."""
    changes = list(delta.life_by_seat)
    if delta.life:
        changes.insert(0, (seat, delta.life))
    events: list[Event] = []
    for changed, amount in changes:
        if not amount:
            continue
        target = game.seat(changed)
        target.life += amount
        events.append(LifeChanged(amount, target.life, changed if game.contested else None))
    return events


# @spec PLAY-092, PLAY-093
def _damage(game: Game, delta: Delta) -> list[Event]:
    """Noncombat damage: pooled against a goldfish game's imaginary opponents, or taken from
    each named seat's life; never commander damage."""
    events: list[Event] = []
    for damaged, amount in delta.damage_by_seat:
        target = game.seat(damaged)
        target.life -= amount
        events.append(SeatDamaged(damaged, amount, target.life))
    if delta.damage:
        imaginary = game.imaginary_opponents
        imaginary.damage_dealt += delta.damage
        events.append(DamageAdded(delta.damage, imaginary.damage_dealt))
    return events


def _asked_seats(game: Game, seat: SeatNumber, entry: AskEntry) -> list[SeatNumber]:
    """The seats one `ask` entry names, in turn order from the seat after the acting seat,
    so that the acting seat itself comes last."""
    in_turn_order = [other.number for other in game.others_from(seat)] + [seat]
    if entry.opponents:
        return [n for n in in_turn_order if n != seat and game.seat(n).in_game]
    return [n for n in in_turn_order if n in entry.seats]


# @spec PLAY-097, PLAY-098, PLAY-120
def _ask(game: Game, seat: SeatNumber, delta: Delta, source: str) -> list[Event]:
    """One `ask` pending choice for each seat each entry names, entry by entry."""
    events: list[Event] = []
    for entry in delta.ask:
        for asked in _asked_seats(game, seat, entry):
            choice_id = game.new_choice_id()
            game.pending.append(
                PendingChoice(
                    choice_id, asked, source, "ask", [], None, asked_by=seat, text=entry.text
                )
            )
            events.append(ChoiceAsked(choice_id, asked, seat, entry.text))
    if events:
        game.status = GameStatus.PENDING_CHOICE
    return events


def open_hand_look(game: Game, look: HandLook) -> list[Event]:
    """Reveal a seat's hand, as it is now, to the looking seat, for a `hand` pending choice."""
    hand = game.hand_of(look.hand_of)
    if not hand:
        return [NothingRevealed("hand")]
    return _pend(game, look.seat, look.source, "hand", hand, rest=None, hand_of=look.hand_of)


# @spec PLAY-102, PLAY-104, PLAY-116
def _look_at_hand(game: Game, seat: SeatNumber, hand_of: SeatNumber, source: str) -> list[Event]:
    """A look at another seat's hand; while asks are waiting, it waits for their answers."""
    look = HandLook(seat, hand_of, source)
    if game.pending:
        game.hand_looks.append(look)
        return []
    return open_hand_look(game, look)


# @spec PLAY-077, PLAY-128
def _check_seats(game: Game, seat: SeatNumber, delta: Delta) -> Error | None:
    """Every seat the delta names must be in the game and still in it; a look at a hand
    names another seat."""
    numbers = {other.number for other in game.seats}
    for named in delta.seats_named:
        if named not in numbers:
            return Error(ErrorKind.NO_SUCH_SEAT, number=named.value)
        if not game.seat(named).in_game:
            return Error(ErrorKind.SEAT_OUT, number=named.value)
    if delta.look_at_hand == seat:
        return Error(ErrorKind.LOOK_AT_OWN_HAND)
    return None


# @spec PLAY-033, PLAY-034, PLAY-035, PLAY-036, PLAY-037, PLAY-038, PLAY-039, PLAY-040
# @spec PLAY-041, PLAY-042, PLAY-043, PLAY-044, PLAY-045, PLAY-050, PLAY-056, PLAY-058
# @spec PLAY-059, PLAY-060, PLAY-006, GAME-019, GAME-061, PAY-044, PLAY-085, PLAY-087
# @spec PLAY-091, PLAY-095, PLAY-079, PLAY-114, PLAY-115
def apply_delta(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    delta: Delta,
    *,
    source: str,
    decks: Decks | None = None,
) -> list[Event] | Error:
    """Apply the acting seat's delta, in the fixed key order, whatever order it was written in.

    Mana goes to the acting seat's pool, a life number is its own, and draws, shuffles,
    looks and searches are of its own library; damage goes to a goldfish game's imaginary
    opponents, or to the seats a contested game's names. Names are read from each card's
    owner's deck (`decks`; omitted, every seat plays `deck`). An error stops the
    application; the caller then discards the game it was applied to. `ask`, then
    `look_at_hand`, `look` and `search` come last and leave pending choices.
    """
    every = decks or Decks.everyone_playing(game, deck)
    named = _check_seats(game, seat, delta)
    if named is not None:
        return named
    events: list[Event] = []
    steps: tuple[Callable[[], object], ...] = (
        lambda: _untap(game, every, seat, delta.untap) if delta.untap else [],
        lambda: _through_ask(game, _tap(game, every, seat, delta.tap)) if delta.tap else [],
        lambda: _mana(game, seat, delta),
        lambda: _tokens(game, seat, delta.tokens),
        lambda: _counters(game, every, seat, delta.counters),
        lambda: _control(game, every, seat, delta) if delta.control else [],
        lambda: _through_ask(game, _move(game, every, seat, delta)) if delta.move else [],
        lambda: _through_ask(game, _discard(game, every, seat, delta)) if delta.discard else [],
        lambda: _through_ask(game, _fetch(game, every, seat, delta)) if delta.fetch else [],
        lambda: draw(game, seat, delta.draw) if delta.draw else [],
        lambda: _life(game, seat, delta),
        lambda: _damage(game, delta),
        lambda: [shuffle_library(game, seat)] if delta.shuffle else [],
        lambda: _ask(game, seat, delta, source) if delta.ask else [],
        lambda: (
            _look_at_hand(game, seat, delta.look_at_hand, source)
            if delta.look_at_hand is not None
            else []
        ),
        lambda: _look(game, seat, delta.look, source) if delta.look else [],
        lambda: _search(game, every.of(seat), seat, delta.search, source) if delta.search else [],
    )
    for step in steps:
        done = step()
        if isinstance(done, Error):
            return done
        assert isinstance(done, list)
        events.extend(done)
    return events


def _mana(game: Game, seat: SeatNumber, delta: Delta) -> list[Event]:
    if not delta.mana:
        return []
    making = game.seat(seat)
    making.mana_pool = making.mana_pool.add(delta.mana)
    return [ManaAdded(str(delta.mana))]
