"""Mana sources: permanents the service knows can make mana, and what each makes now."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from mtg_goldfishing.domain.cards import type_words
from mtg_goldfishing.domain.deck.model import LoadedDeck
from mtg_goldfishing.domain.game.cards_in_play import (
    face_of,
    is_creature,
    is_land,
    is_summoning_sick,
    mana_cost,
    reading_of,
    type_line,
)
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import CardInstance, Game, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import COLORS, ManaString, Restriction, SymbolKind
from mtg_goldfishing.domain.payment.matching import Unit
from mtg_goldfishing.domain.reading.model import (
    AnyColor,
    AnyColorScope,
    CardsInGraveyardCount,
    CardsInHandCount,
    Choice,
    Count,
    Counted,
    CountersOnSelfCount,
    DevotionCount,
    Fixed,
    ManaAbility,
    PermanentsCount,
)

FREE_LAND, LIFE_LAND, OTHER_PERMANENT, CREATURE = 0, 1, 2, 3

Option = tuple[str, ...]


@dataclass(frozen=True)
class Source:
    """One mana ability of one permanent, with what it can make at this moment."""

    instance_id: str
    name: str
    number: int
    options: tuple[Option, ...]
    mana_cost: ManaString
    life: int
    sacrifices: bool
    other_cost: str | None
    restriction: Restriction | None
    rank: int

    @property
    def most_mana(self) -> int:
        return max((len(option) for option in self.options), default=0)

    @property
    def colors(self) -> frozenset[str]:
        return frozenset(kind for option in self.options for kind in option if kind in COLORS)

    @property
    def is_flexible(self) -> bool:
        """Every option is one mana, so the source is one unit of any of those kinds."""
        return all(len(option) == 1 for option in self.options)

    def unit_choices(self) -> list[list[Unit]]:
        """The ways this source's mana can be laid out as units."""
        if self.is_flexible:
            return [[frozenset(option[0] for option in self.options)]]
        return [[frozenset({kind}) for kind in option] for option in self.options]

    def group_key(self) -> tuple[object, ...]:
        """Sources with equal keys are interchangeable to the auto payment system."""
        return (
            self.name,
            self.options,
            self.mana_cost,
            self.life,
            self.restriction,
            self.rank,
        )


def _commander_identity(deck: LoadedDeck) -> tuple[str, ...]:
    colors: set[str] = set()
    for name in deck.commanders:
        deck_card = deck.card(name)
        if deck_card:
            colors.update(deck_card.card.color_identity)
    return tuple(color for color in COLORS if color in colors)


def _devotion(game: Game, decks: Decks, seat: SeatNumber, colors: tuple[str, ...]) -> int:
    total = 0
    for card in game.battlefield_of(seat):
        for symbol in mana_cost(decks.of(card.owner), card).symbols:
            if symbol.kind is not SymbolKind.GENERIC and set(symbol.colors) & set(colors):
                total += 1
    return total


# @spec PAY-011, PAY-051, PAY-054
def count(
    game: Game, deck: LoadedDeck, source: CardInstance, per: Count, decks: Decks | None = None
) -> int:
    """Evaluate a counted amount from the game's state now, as seen by the source's
    controller: its permanents, its devotion, its hand, its graveyard. Each counted card is
    read from its owner's deck (`decks`; omitted, every seat plays `deck`)."""
    every = decks or Decks.everyone_playing(game, deck)
    seat = source.controller
    match per:
        case PermanentsCount(match=word):
            return sum(
                1
                for card in game.battlefield_of(seat)
                if word.lower() in type_words(type_line(every.of(card.owner), card))
            )
        case DevotionCount(colors=colors):
            return _devotion(game, every, seat, colors)
        case CardsInHandCount():
            return len(game.hand_of(seat))
        case CardsInGraveyardCount(match=word):
            return sum(
                1
                for card in game.in_zone(Zone.GRAVEYARD, seat)
                if word is None or word.lower() in type_words(type_line(every.of(card.owner), card))
            )
        case CountersOnSelfCount(counter=counter):
            return source.counters.get(counter, 0)
    return 0


def _any_color_options(
    amount: int, among: AnyColorScope | tuple[str, ...], deck: LoadedDeck
) -> list[Option]:
    if isinstance(among, tuple):
        colors = among
    elif among is AnyColorScope.COMMANDER_IDENTITY:
        colors = _commander_identity(deck)
    else:
        colors = COLORS
    return [(color,) * amount for color in colors if amount > 0]


def options_of(
    game: Game,
    deck: LoadedDeck,
    card: CardInstance,
    ability: ManaAbility,
    decks: Decks | None = None,
) -> tuple[Option, ...]:
    """What an ability can make now, as a list of alternative outputs. The commander's color
    identity it may name is that of the commanders of the seat that controls the permanent
    (`decks`; omitted, every seat plays `deck`)."""
    every = decks or Decks.everyone_playing(game, deck)
    controller_deck = every.of(card.controller)
    produces = ability.produces
    options: list[Option]
    match produces:
        case Fixed(mana=mana):
            options = [mana.produced()] if mana.can_be_produced() else []
        case Choice(options=choices):
            options = [c.produced() for c in choices if c.can_be_produced()]
        case AnyColor(amount=amount, among=among):
            options = _any_color_options(amount, among, controller_deck)
        case Counted(per=per, mana=mana):
            times = count(game, deck, card, per, every)
            if isinstance(mana, AnyColor):
                options = _any_color_options(mana.amount * times, mana.among, controller_deck)
            else:
                options = [mana.produced() * times] if mana.can_be_produced() and times else []
    return tuple(option for option in options if option)


def _rank(deck: LoadedDeck, card: CardInstance, ability: ManaAbility) -> int:
    if is_land(deck, card):
        return LIFE_LAND if ability.life else FREE_LAND
    return CREATURE if is_creature(deck, card) else OTHER_PERMANENT


def sources_of(
    game: Game, deck: LoadedDeck, card: CardInstance, decks: Decks | None = None
) -> list[Source]:
    """Every mana ability of a permanent as a source, whatever its availability, the
    permanent read from its owner's deck (`decks`; omitted, every seat plays `deck`)."""
    every = decks or Decks.everyone_playing(game, deck)
    owner_deck = every.of(card.owner)
    found = []
    face = face_of(owner_deck, card)
    name = face.name if face else card.name
    for ability in reading_of(owner_deck, card).mana_abilities:
        options = options_of(game, deck, card, ability, every)
        found.append(
            Source(
                instance_id=card.id,
                name=name,
                number=card.number,
                options=options,
                mana_cost=ability.mana_cost,
                life=ability.life,
                sacrifices=ability.sacrifices,
                other_cost=ability.other_cost,
                restriction=ability.restriction,
                rank=_rank(owner_deck, card, ability),
            )
        )
    return found


# @spec PAY-010
def is_mana_source(deck: LoadedDeck, card: CardInstance) -> bool:
    return card.zone is Zone.BATTLEFIELD and reading_of(deck, card).is_mana_source


def usable_on_its_own(source: Source) -> bool:
    """Whether the auto payment system may ever use this source without being told."""
    return not source.sacrifices and source.other_cost is None and bool(source.options)


def by_permanent(sources: Iterable[Source]) -> list[tuple[Source, ...]]:
    """The sources grouped by permanent: the abilities through which each may pay, in order."""
    found: dict[str, list[Source]] = {}
    for source in sources:
        found.setdefault(source.instance_id, []).append(source)
    return [tuple(abilities) for abilities in found.values()]


def most_mana_of(sources: Iterable[Source]) -> int:
    """The most mana these sources could make, each permanent through one of its abilities."""
    return sum(max(s.most_mana for s in abilities) for abilities in by_permanent(sources))


def most_of_color(sources: Iterable[Source], color: str) -> int:
    """The most mana of one color these sources could make, one ability per permanent."""
    return sum(
        max((s.most_mana for s in abilities if color in s.colors), default=0)
        for abilities in by_permanent(sources)
    )


# @spec PAY-012, PAY-013, PAY-014, PAY-041, PAY-045, PAY-046, PAY-050, PAY-054
def available_sources(
    game: Game,
    deck: LoadedDeck,
    seat: SeatNumber,
    *,
    paying_for: str | None,
    ignore_tapped: bool = False,
    decks: Decks | None = None,
) -> list[Source]:
    """The paying seat's sources the auto payment system may use, best kind and lowest id
    first.

    Only permanents the seat controls are its sources. Every usable mana ability of a
    permanent is a source of its own; a payment uses at most one of them. `paying_for` is
    the type line of the card being paid for, or None for an effect. A source with a
    restriction is used only when the card qualifies. Each permanent is read from its owner's
    deck (`decks`; omitted, every seat plays `deck`).
    """
    every = decks or Decks.everyone_playing(game, deck)
    found: list[Source] = []
    for card in game.battlefield_of(seat):
        if card.tapped and not ignore_tapped:
            continue
        if is_summoning_sick(game, every.of(card.owner), card, every) and not ignore_tapped:
            continue
        for source in sources_of(game, deck, card, every):
            if not usable_on_its_own(source):
                continue
            if source.restriction is not None and not source.restriction.allows(paying_for):
                continue
            found.append(source)
    return sorted(found, key=lambda s: (s.rank, s.number))
