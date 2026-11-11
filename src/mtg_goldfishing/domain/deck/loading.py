"""`load_deck`: resolve a deck list's cards, apply definitions, check the deck, derive its id.

The use case reads the call's arguments with `read_deck_request`, looks up the request's
`names_to_look_up` through the card catalog, and hands the answers to `load_deck`, which
decides everything else. Nothing here performs I/O or changes what it is given.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from mtg_goldfishing.domain.cards import Card, CardLookup, CardSource, LookupStatus, same_name
from mtg_goldfishing.domain.deck.checks import check_deck
from mtg_goldfishing.domain.deck.deck_list import parse_deck_list
from mtg_goldfishing.domain.deck.definitions import (
    apply_definition,
    definitions_reading,
    read_definition,
)
from mtg_goldfishing.domain.deck.model import (
    CardDefinition,
    DeckCard,
    DeckEntry,
    LoadedDeck,
    OverriddenChecks,
)
from mtg_goldfishing.domain.events import (
    DeckLoaded,
    DeckReport,
    Error,
    ErrorKind,
    Event,
)
from mtg_goldfishing.domain.game.results import Problems, Refusal
from mtg_goldfishing.domain.reading.model import KeywordReport, ReadAbility
from mtg_goldfishing.domain.reading.reader import evasion_and_reach_of, read_card, report

MAX_COMMANDERS = 2
DECK_ID_PREFIX = "d"
DECK_ID_LENGTH = 10
DECK_ID_STEP = 2


def _malformed(subject: str, names: tuple[str, ...] = ()) -> Error:
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject=subject, names=names)


def _key(name: str) -> str:
    return name.strip().casefold()


def _by_name(name: str) -> tuple[str, str]:
    return (name.casefold(), name)


def _distinct(names: Sequence[str]) -> tuple[str, ...]:
    """The names with later repeats (in any letter case) left out."""
    kept: list[str] = []
    for name in names:
        if not any(same_name(name, earlier) for earlier in kept):
            kept.append(name)
    return tuple(kept)


# Reading the arguments


@dataclass(frozen=True)
class DeckRequest:
    """A `load_deck` call's arguments, read: everything decided before cards are looked up."""

    entries: tuple[DeckEntry, ...]
    commanders: tuple[str, ...]
    definitions: tuple[CardDefinition, ...] = ()
    override: str | None = None

    @property
    def names_to_look_up(self) -> tuple[str, ...]:
        """The names to ask the card catalog for: the commanders, then every entry."""
        return _distinct((*self.commanders, *(entry.name for entry in self.entries)))


def _read_commanders(commander: object) -> tuple[str, ...] | Error:
    if commander is None:
        given: list[str] = []
    elif isinstance(commander, str):
        given = [commander]
    elif isinstance(commander, list) and all(isinstance(name, str) for name in commander):
        given = list(commander)
    else:
        return _malformed("commander")
    names = _distinct([name.strip() for name in given if name.strip()])
    if not names:
        return Error(ErrorKind.NO_COMMANDER)
    if len(names) > MAX_COMMANDERS:
        return Error(
            ErrorKind.TOO_MANY_COMMANDERS, names=names, number=len(names), expected=MAX_COMMANDERS
        )
    return names


def _read_definitions(definitions: object) -> tuple[CardDefinition, ...] | Error:
    if definitions is None:
        return ()
    if not isinstance(definitions, list):
        return _malformed("definitions")
    read: list[CardDefinition] = []
    for data in definitions:
        definition = read_definition(data)
        if isinstance(definition, Error):
            return definition
        read.append(definition)
    return tuple(read)


# @spec DECK-001, DECK-005, DECK-007
def read_deck_request(
    *, cards: object, commander: object, definitions: object = None, override: object = None
) -> DeckRequest | Refusal:
    """Read `load_deck`'s arguments as received; every malformed argument is an error."""
    problems = Problems()
    if not isinstance(cards, str):
        problems.add(_malformed("cards"))
    commanders = _read_commanders(commander)
    problems.add(commanders if isinstance(commanders, Error) else None)
    read_definitions = _read_definitions(definitions)
    problems.add(read_definitions if isinstance(read_definitions, Error) else None)
    if override is not None and not isinstance(override, str):
        problems.add(_malformed("override"))
    entries = parse_deck_list(cards) if isinstance(cards, str) else ()
    problems.add(entries if isinstance(entries, Error) else None)
    if problems.has_errors:
        return Refusal(errors=tuple(problems.errors))
    assert not isinstance(commanders, Error)
    assert not isinstance(read_definitions, Error)
    assert not isinstance(entries, Error)
    reason = override.strip() if isinstance(override, str) else ""
    return DeckRequest(entries, commanders, read_definitions, reason or None)


# Resolving the cards


@dataclass(frozen=True)
class _Resolved:
    """A deck's contents, resolved: every name is a card and definitions are applied."""

    commanders: tuple[Card, ...]
    entries: tuple[DeckEntry, ...]
    cards: tuple[DeckCard, ...]
    definitions: tuple[CardDefinition, ...]

    def copies(self) -> tuple[tuple[Card, int], ...]:
        counts = {_key(entry.name): entry.count for entry in self.entries}
        for commander in self.commanders:
            counts[_key(commander.name)] = counts.get(_key(commander.name), 0) + 1
        return tuple(
            (deck_card.card, counts[_key(deck_card.card.name)]) for deck_card in self.cards
        )


def _fetched(name: str, lookups: Mapping[str, CardLookup]) -> Card | LookupStatus:
    """The card the catalog gave for a name, or why there is none.

    A cached card kept after a failed refresh counts as found (and is named as not
    refreshed); a name the catalog did not answer for counts as unavailable.
    """
    lookup = lookups.get(name)
    if lookup is None:
        return LookupStatus.UNAVAILABLE
    if lookup.card is not None:
        return lookup.card
    if lookup.status is LookupStatus.NOT_FOUND:
        return LookupStatus.NOT_FOUND
    return LookupStatus.UNAVAILABLE


def _defined_face(card: Card, definition: CardDefinition) -> int | None:
    if definition.face is None:
        return 0
    return card.face_named(definition.face)


def _canonical(definition: CardDefinition, card: Card) -> CardDefinition:
    """The definition under the card's own name and, when it names a face, the face's own name."""
    index = _defined_face(card, definition)
    face = definition.face
    if face is not None and index is not None:
        face = card.faces[index].name
    return replace(definition, name=card.name, face=face)


def _defined(
    card: Card, definitions: Sequence[CardDefinition], problems: Problems
) -> tuple[Card, tuple[CardDefinition, ...]] | None:
    """The card with its definitions applied, and the definitions in canonical form."""
    faces = [
        0 if card.source is CardSource.DEFINITION else _defined_face(card, d) for d in definitions
    ]
    known = [face for face in faces if face is not None]
    if len(known) != len(set(known)):
        problems.add(_malformed("definitions", (card.name,)))
        return None
    applied = card
    if card.source is not CardSource.DEFINITION:
        for definition in definitions:
            result = apply_definition(applied, definition)
            if isinstance(result, Error):
                problems.add(result)
                return None
            applied = result
    return applied, tuple(_canonical(d, applied) for d in definitions)


def _resolve(request: DeckRequest, lookups: Mapping[str, CardLookup]) -> _Resolved | Refusal:
    problems = Problems()
    not_found: list[str] = []
    unavailable: list[str] = []
    matched: set[int] = set()
    cards: dict[str, Card] = {}
    defined_by: dict[str, list[CardDefinition]] = {}
    card_named: dict[str, str] = {}

    def keep(name: str, card: Card, definitions: list[tuple[int, CardDefinition]]) -> None:
        key = _key(card.name)
        cards.setdefault(key, card)
        card_named[_key(name)] = key
        listed = defined_by.setdefault(key, [])
        for index, definition in definitions:
            if index not in matched:
                matched.add(index)
                listed.append(definition)

    for name in request.names_to_look_up:
        fetched = _fetched(name, lookups)
        if isinstance(fetched, Card):
            keep(
                name,
                fetched,
                [(i, d) for i, d in enumerate(request.definitions) if fetched.matches(d.name)],
            )
            continue
        own = [(i, d) for i, d in enumerate(request.definitions) if same_name(d.name, name)]
        defining = next((d for _, d in own if d.type_line is not None), None)
        if defining is not None:
            made = apply_definition(None, defining)
            assert isinstance(made, Card)
            keep(name, made, own)
            continue
        matched.update(i for i, _ in own)
        if fetched is LookupStatus.UNAVAILABLE:
            unavailable.append(name)
        elif own:
            problems.add(Error(ErrorKind.DEFINITION_NEEDS_TYPE_LINE, subject=own[0][1].name))
        elif any(same_name(name, commander) for commander in request.commanders):
            problems.add(Error(ErrorKind.COMMANDER_NOT_FOUND, subject=name))
        else:
            not_found.append(name)
    if not_found:
        problems.add(Error(ErrorKind.CARDS_NOT_FOUND, names=tuple(not_found)))
    if unavailable:
        problems.add(Error(ErrorKind.CARD_DATA_UNAVAILABLE, names=tuple(unavailable)))
    for index, definition in enumerate(request.definitions):
        if index not in matched:
            problems.add(Error(ErrorKind.DEFINITION_NOT_IN_DECK, subject=definition.name))
    if problems.has_errors:
        return Refusal(errors=tuple(problems.errors))

    deck_cards: list[DeckCard] = []
    definitions: list[CardDefinition] = []
    for key, card in cards.items():
        own_definitions = defined_by.get(key, [])
        if not own_definitions:
            deck_cards.append(DeckCard(card, read_card(card)))
            continue
        defined = _defined(card, own_definitions, problems)
        if defined is not None:
            applied, canonical = defined
            deck_cards.append(DeckCard(applied, definitions_reading(applied, canonical)))
            definitions.extend(canonical)
    if problems.has_errors:
        return Refusal(errors=tuple(problems.errors))

    by_key = {_key(deck_card.card.name): deck_card.card for deck_card in deck_cards}
    commander_keys = _distinct([card_named[_key(name)] for name in request.commanders])
    counts: dict[str, int] = {}
    for entry in request.entries:
        key = card_named[_key(entry.name)]
        counts[key] = counts.get(key, 0) + entry.count
    for key in commander_keys:
        if key in counts:
            counts[key] -= 1
    entries = [DeckEntry(by_key[key].name, count) for key, count in counts.items() if count > 0]
    return _Resolved(
        commanders=tuple(
            sorted((by_key[key] for key in commander_keys), key=lambda c: _by_name(c.name))
        ),
        entries=tuple(sorted(entries, key=lambda entry: _by_name(entry.name))),
        cards=tuple(sorted(deck_cards, key=lambda deck_card: _by_name(deck_card.card.name))),
        definitions=tuple(sorted(definitions, key=lambda d: (*_by_name(d.name), d.face or ""))),
    )


# The deck id


def _definition_form(definition: CardDefinition) -> list[object]:
    return [
        definition.name,
        definition.face,
        None if definition.mana_cost is None else str(definition.mana_cost),
        definition.type_line,
        definition.oracle_text,
        definition.power,
        definition.toughness,
        None if definition.color_identity is None else list(definition.color_identity),
        None if definition.keywords is None else list(definition.keywords),
        None if definition.produces is None else [str(mana) for mana in definition.produces],
        definition.enters_tapped,
    ]


def _card_form(card: Card) -> list[object]:
    return [
        card.name,
        card.layout,
        card.mana_value,
        list(card.color_identity),
        list(card.keywords),
        list(card.produced_colors),
        card.commander_legal,
        card.source.value,
        [
            [
                face.name,
                str(face.mana_cost),
                face.type_line,
                face.oracle_text,
                face.power,
                face.toughness,
            ]
            for face in card.faces
        ],
    ]


def deck_digest(
    commanders: Sequence[str],
    entries: Sequence[DeckEntry],
    definitions: Sequence[CardDefinition],
    cards: Sequence[Card],
) -> str:
    """The SHA-256 hash, in hexadecimal, of a deck's canonical form.

    The canonical form is the commander names sorted; the entries as (count, name) sorted
    by name; the definitions sorted by name, each with its fields in a fixed order; and the
    card data of every card, sorted by name.
    """
    canonical = [
        sorted(commanders, key=_by_name),
        [[entry.count, entry.name] for entry in sorted(entries, key=lambda e: _by_name(e.name))],
        [
            _definition_form(definition)
            for definition in sorted(definitions, key=lambda d: (*_by_name(d.name), d.face or ""))
        ],
        [_card_form(card) for card in sorted(cards, key=lambda c: _by_name(c.name))],
    ]
    text = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_of(deck: LoadedDeck) -> str:
    return deck_digest(
        deck.commanders,
        deck.entries,
        deck.definitions,
        tuple(deck_card.card for deck_card in deck.cards),
    )


def _place(
    digest: str, existing: Callable[[str], LoadedDeck | None]
) -> tuple[str, LoadedDeck | None]:
    """The deck's id, and the loaded deck already holding it with the same contents, if any.

    An id held by a deck with different contents is lengthened two characters at a time.
    """
    for length in range(DECK_ID_LENGTH, len(digest) + 1, DECK_ID_STEP):
        deck_id = DECK_ID_PREFIX + digest[:length]
        held = existing(deck_id)
        if held is None:
            return deck_id, None
        if _digest_of(held) == digest:
            return deck_id, held
    raise AssertionError(f"every id from the digest {digest} is held by a different deck")


# The report


# @spec DECK-037, DECK-041
def deck_report(deck: LoadedDeck) -> DeckReport:
    """What `load_deck` tells about a loaded deck's definitions and readings."""
    readings = report((deck_card.card, deck_card.reading) for deck_card in deck.cards)
    not_used_on_their_own: list[ReadAbility] = []
    keywords_with_assumptions: list[KeywordReport] = []
    for deck_card in deck.cards:
        for face, reading in zip(deck_card.card.faces, deck_card.reading.faces, strict=False):
            not_used_on_their_own.extend(
                ReadAbility(face.name, ability)
                for ability in reading.mana_abilities
                if ability.sacrifices or ability.other_cost is not None
            )
            keywords_with_assumptions.extend(
                KeywordReport(face.name, keyword, keyword_reading)
                for keyword, keyword_reading in (
                    ("haste", reading.haste),
                    ("vigilance", reading.vigilance),
                    ("flash", reading.flash),
                    *evasion_and_reach_of(reading),
                )
                if keyword_reading.assumptions
            )
    return DeckReport(
        definitions_applied=_distinct([definition.name for definition in deck.definitions]),
        read_with_assumptions=readings.read_with_assumptions,
        unread=readings.unread,
        not_used_on_their_own=tuple(not_used_on_their_own),
        granting_haste_or_vigilance=tuple(
            keyword for keyword in readings.keywords if keyword.reading.grant is not None
        ),
        granting_evasion_or_reach=tuple(
            keyword for keyword in readings.evasion_and_reach if keyword.reading.grant is not None
        ),
        enters_tapped=readings.enters_tapped,
        assumed_untapped=readings.assumed_untapped,
        keywords_with_assumptions=tuple(keywords_with_assumptions),
    )


def _not_refreshed(lookups: Mapping[str, CardLookup]) -> tuple[str, ...]:
    """The cards the catalog kept on their cached data because it could not fetch them again."""
    return tuple(
        sorted(
            {
                lookup.card.name
                for lookup in lookups.values()
                if lookup.card is not None and lookup.status is not LookupStatus.FOUND
            },
            key=_by_name,
        )
    )


# Loading


@dataclass(frozen=True)
class DeckLoad:
    """A loaded deck, new or already held, with the headline event and anything else to tell.

    The deck is new, and to be added, unless the summary says it was already loaded.
    """

    deck: LoadedDeck
    summary: DeckLoaded
    events: tuple[Event, ...] = ()


# @spec DECK-006, DECK-008, DECK-010, DECK-012, DECK-018, DECK-019, DECK-020
# @spec DECK-027, DECK-028, DECK-029, DECK-030, DECK-031, DECK-032, DECK-033, DECK-034
# @spec DECK-035, DECK-036, DECK-038
def load_deck(
    request: DeckRequest,
    lookups: Mapping[str, CardLookup],
    existing: Callable[[str], LoadedDeck | None],
) -> DeckLoad | Refusal:
    """Build and check a loaded deck from a request and the catalog's answers for its names.

    `lookups` holds the catalog's answer for each of the request's `names_to_look_up`;
    `existing` gives the loaded deck holding an id, if any. Errors refuse; failed deck
    checks refuse unless the request carries an override. A deck whose id is already held
    by a deck with the same contents is returned as it is.
    """
    resolved = _resolve(request, lookups)
    if isinstance(resolved, Refusal):
        return resolved
    problems = Problems()
    problems.extend(check_deck(resolved.commanders, resolved.copies()))
    judged = problems.judge(request.override)
    if isinstance(judged, Refusal):
        return judged
    commanders = tuple(card.name for card in resolved.commanders)
    digest = deck_digest(
        commanders,
        resolved.entries,
        resolved.definitions,
        tuple(deck_card.card for deck_card in resolved.cards),
    )
    deck_id, held = _place(digest, existing)
    deck = held or LoadedDeck(
        deck_id=deck_id,
        commanders=commanders,
        entries=resolved.entries,
        cards=resolved.cards,
        definitions=resolved.definitions,
        overrides=() if judged is None else (OverriddenChecks(judged.checks, judged.reason),),
    )
    summary = DeckLoaded(
        deck.deck_id,
        deck.card_count,
        deck.commanders,
        already_loaded=held is not None,
        report=replace(deck_report(deck), not_refreshed=_not_refreshed(lookups)),
    )
    return DeckLoad(deck, summary, () if judged is None else (judged,))
