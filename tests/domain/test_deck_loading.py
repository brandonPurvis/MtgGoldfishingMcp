"""Loading a deck: resolving its cards, applying definitions, the deck checks and the deck id."""

from __future__ import annotations

import copy
import dataclasses
import re

import pytest

from mtg_goldfishing.domain.cards import CardLookup, CardSource, LookupStatus
from mtg_goldfishing.domain.deck.loading import DeckLoad, load_deck, read_deck_request
from mtg_goldfishing.domain.deck.model import DeckEntry, OverriddenChecks
from mtg_goldfishing.domain.events import (
    CheckKind,
    ChecksOverridden,
    DeckLoaded,
    DeckReport,
    Error,
    ErrorKind,
    FailedCheck,
)
from mtg_goldfishing.domain.game.results import Refusal
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.reading.model import (
    ASSUMES_CONDITION_MET,
    EntersTappedReading,
    FaceReading,
    Fixed,
    ManaAbility,
)
from tests.support.card_data import recorded_card, recorded_cards
from tests.support.cards import a_card
from tests.support.decks import ATRAXA, DeckStore, a_deck_list, catalog_answers

M = ManaString.parse
DECK_ID = re.compile(r"^d[0-9a-f]{10}$")
THRASIOS = "Thrasios, Triton Hero"
TYMNA = "Tymna the Weaver"
VALKI = "Valki, God of Lies // Tibalt, Cosmic Impostor"


def check_kinds(refusal: Refusal) -> set[CheckKind]:
    return {check.kind for check in refusal.checks}


def error_kinds(refusal: Refusal) -> list[ErrorKind]:
    return [error.kind for error in refusal.errors]


def deck_card_reading(load: DeckLoad, name: str) -> FaceReading:
    found = load.deck.card(name)
    assert found is not None
    return found.reading.face(0)


# Commanders


# @spec DECK-006
def test_a_commander_also_listed_in_the_cards_is_counted_once() -> None:
    builder = a_deck_list()
    text = builder.text() + f"\n1 {ATRAXA}"
    assert builder.loaded(text).deck.card_count == 100


# @spec DECK-006
def test_a_commander_listed_in_the_cards_is_not_also_an_entry() -> None:
    builder = a_deck_list()
    deck = builder.loaded(builder.text() + f"\n{ATRAXA}").deck
    assert ATRAXA not in {entry.name for entry in deck.entries}


# @spec DECK-007
def test_no_commander_is_an_error() -> None:
    assert error_kinds(a_deck_list().with_commander().refused()) == [ErrorKind.NO_COMMANDER]


# @spec DECK-007
def test_more_than_two_commanders_is_an_error() -> None:
    refusal = a_deck_list().with_commander(THRASIOS, TYMNA, ATRAXA).refused()
    assert error_kinds(refusal) == [ErrorKind.TOO_MANY_COMMANDERS]


# @spec DECK-007
def test_two_commanders_make_a_deck_led_by_both() -> None:
    load = a_deck_list().with_commander(THRASIOS, TYMNA).loaded()
    assert load.deck.commanders == (THRASIOS, TYMNA)


# @spec DECK-008
def test_a_commander_that_resolves_to_no_card_is_an_error_naming_it() -> None:
    refusal = a_deck_list().with_commander("Atraxa, Praetor's Voice").refused()
    assert refusal.errors == (
        Error(ErrorKind.COMMANDER_NOT_FOUND, subject="Atraxa, Praetor's Voice"),
    )


# @spec DECK-008, DECK-010
def test_a_commander_known_only_by_its_definition_resolves() -> None:
    load = (
        a_deck_list()
        .with_commander("Homebrew Queen")
        .with_definition(
            name="Homebrew Queen",
            type_line="Legendary Creature — Human",
            color_identity=["W", "U", "B", "G"],
        )
        .loaded()
    )
    assert load.deck.commanders == ("Homebrew Queen",)


# Card definitions


# @spec DECK-009
def test_a_definition_replaces_the_fetched_fields_it_gives_in_the_loaded_deck() -> None:
    load = a_deck_list().with_definition(name="Grizzly Bears", power="3").loaded()
    card = load.deck.card("Grizzly Bears")
    assert card is not None
    assert (card.card.front.power, card.card.front.toughness) == ("3", "2")


# @spec DECK-010
def test_a_definition_for_a_card_scryfall_has_is_accepted() -> None:
    load = a_deck_list().with_definition(name="Sol Ring", oracle_text="{T}: Add {C}.").loaded()
    card = load.deck.card("Sol Ring")
    assert card is not None
    assert card.card.source is CardSource.SCRYFALL_AND_DEFINITION


# @spec DECK-010
def test_a_definition_for_a_card_scryfall_does_not_have_is_accepted() -> None:
    load = (
        a_deck_list()
        .with_cards("Homemade Elf")
        .with_definition(name="Homemade Elf", type_line="Creature — Elf")
        .loaded()
    )
    card = load.deck.card("Homemade Elf")
    assert card is not None
    assert card.card.source is CardSource.DEFINITION


# @spec DECK-011
def test_a_definition_naming_a_face_changes_that_face_in_the_loaded_deck() -> None:
    load = (
        a_deck_list()
        .with_cards("Fire // Ice")
        .with_definition(name="Fire // Ice", face="Ice", mana_cost="{U}")
        .with_override("testing a split card")
        .loaded()
    )
    card = load.deck.card("Fire // Ice")
    assert card is not None
    assert [face.mana_cost for face in card.card.faces] == [M("{1}{R}"), M("{U}")]


# @spec DECK-011
def test_definitions_for_two_faces_of_one_card_both_apply() -> None:
    load = (
        a_deck_list()
        .with_cards("Fire // Ice")
        .with_definition(name="Fire // Ice", face="Fire", mana_cost="{R}")
        .with_definition(name="Fire // Ice", face="Ice", mana_cost="{U}")
        .with_override("testing a split card")
        .loaded()
    )
    card = load.deck.card("Fire // Ice")
    assert card is not None
    assert [face.mana_cost for face in card.card.faces] == [M("{R}"), M("{U}")]


def test_two_definitions_for_the_same_face_are_an_error() -> None:
    refusal = (
        a_deck_list()
        .with_definition(name="Sol Ring", oracle_text="{T}: Add {C}.")
        .with_definition(name="sol ring", oracle_text="{T}: Add {C}{C}.")
        .refused()
    )
    assert refusal.errors == (
        Error(ErrorKind.MALFORMED_ARGUMENT, subject="definitions", names=("Sol Ring",)),
    )


def test_a_definition_naming_a_face_the_card_does_not_have_is_an_error() -> None:
    refusal = a_deck_list().with_definition(name="Sol Ring", face="Moon Ring", power="1").refused()
    assert refusal.errors == (Error(ErrorKind.MALFORMED_ARGUMENT, subject="definition.face"),)


# @spec DECK-012
def test_a_definition_naming_a_card_not_in_the_deck_is_an_error_naming_it() -> None:
    refusal = a_deck_list().with_definition(name="Lightning Bolt", power="3").refused()
    assert refusal.errors == (Error(ErrorKind.DEFINITION_NOT_IN_DECK, subject="Lightning Bolt"),)


# @spec DECK-012
def test_a_definition_naming_a_face_of_a_deck_card_is_in_the_deck() -> None:
    load = (
        a_deck_list()
        .with_cards(VALKI)
        .with_definition(name="Valki, God of Lies", power="3")
        .with_override("Valki is off-color here")
        .loaded()
    )
    card = load.deck.card("Valki, God of Lies")
    assert card is not None
    assert card.card.front.power == "3"


# @spec DECK-013
def test_a_definition_for_an_unfound_card_without_a_type_line_is_an_error_naming_it() -> None:
    refusal = (
        a_deck_list()
        .with_cards("Homemade Elf")
        .with_definition(name="Homemade Elf", power="2")
        .refused()
    )
    assert refusal.errors == (Error(ErrorKind.DEFINITION_NEEDS_TYPE_LINE, subject="Homemade Elf"),)


# @spec DECK-014
def test_produces_makes_the_card_a_mana_source_for_that_mana() -> None:
    load = a_deck_list().with_definition(name="Grizzly Bears", produces="{G}").loaded()
    reading = deck_card_reading(load, "Grizzly Bears")
    assert reading.mana_abilities == (ManaAbility(Fixed(M("{G}"))),)


# @spec DECK-015
def test_enters_tapped_replaces_the_enters_tapped_reading_in_the_loaded_deck() -> None:
    load = a_deck_list().with_definition(name="Command Tower", enters_tapped=True).loaded()
    reading = deck_card_reading(load, "Command Tower")
    assert reading.enters_tapped == EntersTappedReading(tapped=True)


# @spec DECK-016
def test_haste_among_a_definitions_keywords_is_the_cards_own_in_the_loaded_deck() -> None:
    load = a_deck_list().with_definition(name="Grizzly Bears", keywords=["Haste"]).loaded()
    assert deck_card_reading(load, "Grizzly Bears").haste.own


# @spec DECK-017
def test_the_loaded_deck_reads_a_definitions_rules_text() -> None:
    load = a_deck_list().with_definition(name="Grizzly Bears", oracle_text="{T}: Add {G}.").loaded()
    reading = deck_card_reading(load, "Grizzly Bears")
    assert reading.mana_abilities[0].produces == Fixed(M("{G}"))


# @spec DECK-018
def test_loading_with_definitions_leaves_the_fetched_card_data_untouched() -> None:
    request = read_deck_request(
        cards=a_deck_list().text(),
        commander=ATRAXA,
        definitions=[{"name": "Sol Ring", "oracle_text": "{T}: Add {G}."}],
    )
    assert not isinstance(request, Refusal)
    lookups = catalog_answers(request.names_to_look_up, recorded_cards())
    before = copy.deepcopy(lookups)
    load_deck(request, lookups, DeckStore().get)
    assert lookups == before


# Resolution errors


# @spec DECK-019
def test_every_unfound_name_is_listed_in_one_error() -> None:
    refusal = a_deck_list().with_cards("Sol Rnig", "Lighting Bolt", "Main Deck").refused()
    assert refusal.errors == (
        Error(ErrorKind.CARDS_NOT_FOUND, names=("Sol Rnig", "Lighting Bolt", "Main Deck")),
    )


# @spec DECK-020
def test_unavailable_card_data_is_an_error_listing_the_names() -> None:
    refusal = a_deck_list().with_unavailable("Sol Ring", "Ponder").refused()
    assert refusal.errors == (Error(ErrorKind.CARD_DATA_UNAVAILABLE, names=("Sol Ring", "Ponder")),)


# @spec DECK-020
def test_unavailable_card_data_is_not_needed_for_a_card_defined_with_a_type_line() -> None:
    load = (
        a_deck_list()
        .with_unavailable("Sol Ring")
        .with_definition(name="Sol Ring", type_line="Artifact", oracle_text="{T}: Add {C}{C}.")
        .loaded()
    )
    assert load.deck.card("Sol Ring") is not None


# @spec DECK-020
def test_a_cached_card_kept_when_its_refresh_was_unavailable_is_used() -> None:
    request = read_deck_request(cards="99 Forest", commander=ATRAXA)
    assert not isinstance(request, Refusal)
    lookups = catalog_answers(request.names_to_look_up, [recorded_card("Forest")])
    lookups[ATRAXA] = CardLookup(LookupStatus.UNAVAILABLE, recorded_card(ATRAXA))
    assert isinstance(load_deck(request, lookups, DeckStore().get), DeckLoad)


# @spec DECK-020
def test_a_name_missing_from_the_catalogs_answers_counts_as_unavailable() -> None:
    request = read_deck_request(cards="99 Forest", commander=ATRAXA)
    assert not isinstance(request, Refusal)
    lookups = catalog_answers([ATRAXA], [recorded_card(ATRAXA)])
    result = load_deck(request, lookups, DeckStore().get)
    assert result == Refusal.error(Error(ErrorKind.CARD_DATA_UNAVAILABLE, names=("Forest",)))


# Deck checks


def test_a_deck_that_passes_every_check_loads() -> None:
    assert isinstance(a_deck_list().load(), DeckLoad)


# @spec DECK-021
def test_a_deck_of_fewer_than_100_cards_fails_the_size_check() -> None:
    refusal = a_deck_list().of_size(99).refused()
    assert refusal.checks == (FailedCheck(CheckKind.DECK_SIZE, number=99, expected=100),)


# @spec DECK-021
def test_a_deck_of_more_than_100_cards_fails_the_size_check() -> None:
    assert check_kinds(a_deck_list().of_size(101).refused()) == {CheckKind.DECK_SIZE}


# @spec DECK-022
def test_two_copies_of_a_card_fail_the_singleton_check() -> None:
    refusal = a_deck_list().with_cards("Sol Ring", count=2).refused()
    assert refusal.checks == (
        FailedCheck(CheckKind.SINGLETON, subject="Sol Ring", number=2, expected=1),
    )


# @spec DECK-022
def test_a_commander_listed_twice_in_the_cards_fails_the_singleton_check() -> None:
    builder = a_deck_list().of_size(99)
    refusal = builder.refused(builder.text() + f"\n2 {ATRAXA}")
    assert refusal.checks == (
        FailedCheck(CheckKind.SINGLETON, subject=ATRAXA, number=2, expected=1),
    )


# @spec DECK-022
def test_many_copies_of_a_basic_land_pass_the_singleton_check() -> None:
    load = a_deck_list().with_cards("Island", count=20).loaded()
    assert DeckEntry("Island", 20) in load.deck.entries


# @spec DECK-022
def test_a_card_any_number_of_which_a_deck_can_have_passes_the_singleton_check() -> None:
    load = a_deck_list().with_cards("Relentless Rats", count=30).loaded()
    assert DeckEntry("Relentless Rats", 30) in load.deck.entries


# @spec DECK-023
def test_a_stated_number_of_copies_passes_the_singleton_check() -> None:
    load = (
        a_deck_list()
        .with_cards("Seven Dwarves", count=7)
        .with_definition(name="Seven Dwarves", color_identity=["G"])
        .loaded()
    )
    assert DeckEntry("Seven Dwarves", 7) in load.deck.entries


# @spec DECK-023
def test_more_than_the_stated_number_of_copies_fails_the_singleton_check() -> None:
    refusal = (
        a_deck_list()
        .with_cards("Seven Dwarves", count=8)
        .with_definition(name="Seven Dwarves", color_identity=["G"])
        .refused()
    )
    assert refusal.checks == (
        FailedCheck(CheckKind.SINGLETON, subject="Seven Dwarves", number=8, expected=7),
    )


# @spec DECK-024
def test_a_card_outside_the_commanders_color_identity_fails_the_color_identity_check() -> None:
    refusal = a_deck_list().with_cards("Lightning Bolt", "Goblin Guide").refused()
    assert refusal.checks == (
        FailedCheck(CheckKind.COLOR_IDENTITY, names=("Goblin Guide", "Lightning Bolt")),
    )


# @spec DECK-024
def test_the_color_identity_check_allows_the_commanders_combined_identity() -> None:
    assert isinstance(a_deck_list().with_commander(THRASIOS, TYMNA).load(), DeckLoad)


# @spec DECK-024
def test_a_definitions_color_identity_is_what_the_check_uses() -> None:
    load = (
        a_deck_list()
        .with_cards("Lightning Bolt")
        .with_definition(name="Lightning Bolt", color_identity=["B"])
        .loaded()
    )
    assert load.deck.card("Lightning Bolt") is not None


# @spec DECK-025
def test_a_card_banned_in_commander_fails_the_legality_check() -> None:
    refusal = a_deck_list().with_cards("Black Lotus").refused()
    assert refusal.checks == (FailedCheck(CheckKind.LEGALITY, names=("Black Lotus",)),)


# @spec DECK-025
def test_a_card_supplied_only_by_definition_passes_the_legality_check() -> None:
    load = (
        a_deck_list()
        .with_cards("Homemade Elf")
        .with_definition(name="Homemade Elf", type_line="Creature — Elf")
        .loaded()
    )
    assert load.deck.card("Homemade Elf") is not None


# @spec DECK-026
def test_a_commander_that_is_not_a_legendary_creature_fails_commander_eligibility() -> None:
    refusal = (
        a_deck_list()
        .with_commander("Grizzly Bears")
        .without("Grizzly Bears")
        .with_card_data(
            dataclasses.replace(recorded_card("Grizzly Bears"), color_identity=("W", "U", "B", "G"))
        )
        .refused()
    )
    assert refusal.checks == (
        FailedCheck(CheckKind.COMMANDER_ELIGIBILITY, names=("Grizzly Bears",)),
    )


# @spec DECK-026
def test_a_commander_whose_rules_text_allows_it_passes_commander_eligibility() -> None:
    planeswalker = a_card(
        "Grist, Ancient Walker",
        "Grist can be your commander.",
        "Legendary Planeswalker — Grist",
    )
    load = (
        a_deck_list()
        .with_commander("Grist, Ancient Walker")
        .with_card_data(dataclasses.replace(planeswalker, color_identity=("W", "U", "B", "G")))
        .loaded()
    )
    assert load.deck.commanders == ("Grist, Ancient Walker",)


# @spec DECK-027
def test_every_failed_deck_check_is_listed_together() -> None:
    refusal = a_deck_list().with_cards("Lightning Bolt", "Black Lotus").of_size(105).refused()
    assert check_kinds(refusal) == {
        CheckKind.DECK_SIZE,
        CheckKind.COLOR_IDENTITY,
        CheckKind.LEGALITY,
    }


# @spec DECK-027
def test_failed_deck_checks_without_an_override_refuse_with_no_errors() -> None:
    assert a_deck_list().of_size(99).refused().errors == ()


# @spec DECK-028
def test_with_an_override_a_deck_failing_its_checks_is_loaded() -> None:
    load = a_deck_list().of_size(99).with_override("testing a short deck").loaded()
    assert load.deck.card_count == 99


# @spec DECK-028
def test_the_loaded_deck_records_the_overridden_checks_and_the_reason() -> None:
    load = a_deck_list().of_size(99).with_override("testing a short deck").loaded()
    assert load.deck.overrides == (
        OverriddenChecks(
            (FailedCheck(CheckKind.DECK_SIZE, number=99, expected=100),), "testing a short deck"
        ),
    )


# @spec DECK-028, DECK-037
def test_overridden_deck_checks_are_reported() -> None:
    load = a_deck_list().of_size(99).with_override("testing a short deck").loaded()
    assert load.events == (
        ChecksOverridden(
            (FailedCheck(CheckKind.DECK_SIZE, number=99, expected=100),), "testing a short deck"
        ),
    )


# Deck id and loaded decks


# @spec DECK-029
def test_the_deck_id_is_d_and_ten_hexadecimal_characters() -> None:
    assert DECK_ID.match(a_deck_list().loaded().deck.deck_id)


# @spec DECK-029
def test_the_deck_id_depends_on_the_entries() -> None:
    first = a_deck_list().loaded().deck.deck_id
    second = a_deck_list().without("Ponder").with_cards("Island").loaded().deck.deck_id
    assert first != second


# @spec DECK-029
def test_the_deck_id_depends_on_the_commanders() -> None:
    first = a_deck_list().with_commander(THRASIOS).with_override("off-color")
    second = a_deck_list().with_commander(TYMNA).with_override("off-color")
    assert first.loaded().deck.deck_id != second.loaded().deck.deck_id


# @spec DECK-029
def test_the_deck_id_depends_on_the_definitions() -> None:
    plain = a_deck_list().loaded().deck.deck_id
    defined = a_deck_list().with_definition(name="Grizzly Bears", power="3").loaded()
    assert plain != defined.deck.deck_id


# @spec DECK-029
def test_the_order_commanders_are_given_in_does_not_change_the_deck_id() -> None:
    first = a_deck_list().with_commander(THRASIOS, TYMNA).loaded().deck.deck_id
    second = a_deck_list().with_commander(TYMNA, THRASIOS).loaded().deck.deck_id
    assert first == second


# @spec DECK-030
def test_formatting_line_order_letter_case_and_comments_do_not_change_the_deck_id() -> None:
    builder = a_deck_list()
    reworded = ["# my deck", ""]
    for line in reversed(builder.lines()):
        count, name = line.split(" ", 1)
        reworded.append(f"  {count}x {name.upper()} (SET) 12")
    assert builder.loaded().deck.deck_id == builder.loaded("\n".join(reworded)).deck.deck_id


# @spec DECK-030
def test_a_card_split_over_several_lines_gives_the_same_deck_id() -> None:
    builder = a_deck_list().without("Sol Ring").with_cards("Island", count=2)
    split = builder.text().replace("2 Island", "1 Island\n1 island")
    assert builder.loaded(split).deck.deck_id == builder.loaded().deck.deck_id


# @spec DECK-030, DECK-004
def test_a_card_named_by_full_name_and_by_face_name_is_one_entry() -> None:
    builder = a_deck_list().with_override("off-color").of_size(98)
    load = builder.loaded(builder.text() + f"\n{VALKI}\nTibalt, Cosmic Impostor")
    assert DeckEntry(VALKI, 2) in load.deck.entries


# @spec DECK-031
def test_an_existing_deck_with_the_same_id_is_returned_unchanged() -> None:
    builder = a_deck_list()
    stored = builder.loaded().deck
    assert builder.loaded(existing=DeckStore(stored).get).deck is stored


# @spec DECK-031, DECK-036
def test_an_existing_deck_is_reported_as_already_loaded() -> None:
    builder = a_deck_list()
    stored = builder.loaded().deck
    assert builder.loaded(existing=DeckStore(stored).get).summary.already_loaded


# @spec DECK-031
def test_a_new_deck_is_not_reported_as_already_loaded() -> None:
    assert not a_deck_list().loaded().summary.already_loaded


# @spec DECK-031, DECK-027
def test_a_deck_that_failed_its_checks_needs_its_override_on_every_load() -> None:
    stored = a_deck_list().of_size(99).with_override("short deck").loaded().deck
    again = a_deck_list().of_size(99).load(existing=DeckStore(stored).get)
    assert isinstance(again, Refusal)


# @spec DECK-032
def test_a_loaded_deck_cannot_be_altered() -> None:
    deck = a_deck_list().loaded().deck
    with pytest.raises(dataclasses.FrozenInstanceError):
        deck.deck_id = "dchanged"  # type: ignore[misc]


# @spec DECK-032
def test_loading_again_with_a_different_override_reason_leaves_the_deck_as_it_was() -> None:
    stored = a_deck_list().of_size(99).with_override("first reason").loaded().deck
    again = (
        a_deck_list()
        .of_size(99)
        .with_override("second reason")
        .loaded(existing=DeckStore(stored).get)
    )
    assert again.deck.overrides[0].reason == "first reason"


# @spec DECK-033
def test_changed_card_data_gives_a_new_deck_id() -> None:
    before = a_deck_list().loaded().deck
    after = (
        a_deck_list()
        .with_changed_card_data("Sol Ring", mana_value=2.0)
        .loaded(existing=DeckStore(before).get)
    )
    assert after.deck.deck_id != before.deck_id


# @spec DECK-033
def test_changed_card_data_makes_a_new_deck() -> None:
    before = a_deck_list().loaded().deck
    after = (
        a_deck_list()
        .with_changed_card_data("Sol Ring", mana_value=2.0)
        .loaded(existing=DeckStore(before).get)
    )
    assert not after.summary.already_loaded


def _holding(deck_id: str, *, without: str) -> DeckStore:
    """A store where a deck different from the standard list holds `deck_id`."""
    other = a_deck_list().without(without).loaded().deck
    return DeckStore(dataclasses.replace(other, deck_id=deck_id))


# @spec DECK-034
def test_an_id_held_by_a_different_deck_is_lengthened_by_two_characters() -> None:
    builder = a_deck_list()
    deck_id = builder.loaded().deck.deck_id
    load = builder.loaded(existing=_holding(deck_id, without="Ponder").get)
    assert re.match(rf"^{deck_id}[0-9a-f]{{2}}$", load.deck.deck_id)


# @spec DECK-034
def test_an_id_is_lengthened_until_it_is_unique() -> None:
    builder = a_deck_list()
    short = builder.loaded().deck.deck_id
    longer = builder.loaded(existing=_holding(short, without="Ponder").get).deck.deck_id
    store = _holding(short, without="Ponder")
    store.decks |= _holding(longer, without="Brainstorm").decks
    assert len(builder.loaded(existing=store.get).deck.deck_id) == len(short) + 4


# @spec DECK-034, DECK-031
def test_a_lengthened_id_finds_the_deck_stored_under_it() -> None:
    builder = a_deck_list()
    store = _holding(builder.loaded().deck.deck_id, without="Ponder")
    stored = builder.loaded(existing=store.get).deck
    store.decks[stored.deck_id] = stored
    assert builder.loaded(existing=store.get).deck is stored


# @spec DECK-035
def test_the_loaded_deck_holds_its_id_commanders_and_entries() -> None:
    load = a_deck_list().with_cards("Island", count=3).loaded()
    deck = load.deck
    assert (deck.deck_id, deck.commanders, DeckEntry("Island", 3) in deck.entries) == (
        load.summary.deck_id,
        (ATRAXA,),
        True,
    )


# @spec DECK-035
def test_the_loaded_deck_holds_card_data_for_every_card() -> None:
    deck = a_deck_list().loaded().deck
    names = {ATRAXA, *(entry.name for entry in deck.entries)}
    assert {card.card.name for card in deck.cards} == names


# @spec DECK-035
def test_the_loaded_deck_holds_the_reading_of_every_card() -> None:
    deck = a_deck_list().loaded().deck
    sol_ring = deck.card("Sol Ring")
    assert sol_ring is not None
    assert sol_ring.reading.face(0).mana_abilities[0].produces == Fixed(M("{C}{C}"))


# @spec DECK-035
def test_entries_use_the_canonical_card_names() -> None:
    builder = a_deck_list().without("Sol Ring").of_size(99)
    deck = builder.loaded(builder.text() + "\nsol ring").deck
    assert DeckEntry("Sol Ring", 1) in deck.entries


# @spec DECK-035, DECK-009
def test_the_loaded_deck_holds_its_definitions_under_the_canonical_card_name() -> None:
    deck = a_deck_list().with_definition(name="grizzly bears", power="3").loaded().deck
    assert [(d.name, d.power) for d in deck.definitions] == [("Grizzly Bears", "3")]


# Response


# @spec DECK-036
def test_a_successful_load_states_the_id_card_count_and_commanders() -> None:
    load = a_deck_list().loaded()
    assert load.summary == DeckLoaded(load.deck.deck_id, 100, (ATRAXA,), report=load.summary.report)


# @spec DECK-037
def test_the_report_lists_definitions_applied() -> None:
    load = a_deck_list().with_definition(name="Grizzly Bears", power="3").loaded()
    assert load.summary.report.definitions_applied == ("Grizzly Bears",)


# @spec DECK-037
def test_the_report_lists_mana_abilities_read_with_assumptions() -> None:
    load = a_deck_list().with_cards("Exotic Orchard").loaded()
    assert [
        (read.card, read.ability.assumptions) for read in load.summary.report.read_with_assumptions
    ] == [("Exotic Orchard", ("assumes any color",))]


# @spec DECK-037
def test_the_report_lists_mana_abilities_not_read() -> None:
    load = a_deck_list().with_cards("Utopia Sprawl").loaded()
    assert [unread.card for unread in load.summary.report.unread] == ["Utopia Sprawl"]


# @spec DECK-037
def test_the_report_lists_sources_the_auto_payment_system_will_not_use_on_its_own() -> None:
    load = a_deck_list().with_cards("Lotus Petal").loaded()
    assert [read.card for read in load.summary.report.not_used_on_their_own] == ["Lotus Petal"]


# @spec DECK-037
def test_the_report_lists_cards_that_grant_haste_or_vigilance() -> None:
    load = a_deck_list().with_cards("Concordant Crossroads").loaded()
    assert [grant.card for grant in load.summary.report.granting_haste_or_vigilance] == [
        "Concordant Crossroads"
    ]


# @spec DECK-037
def test_the_report_lists_cards_read_as_entering_tapped() -> None:
    load = a_deck_list().with_cards("Temple of Plenty").loaded()
    assert [tapped.card for tapped in load.summary.report.enters_tapped] == ["Temple of Plenty"]


# @spec DECK-037
def test_the_report_lists_cards_assumed_to_enter_untapped_with_their_conditions() -> None:
    load = a_deck_list().with_cards("Glacial Fortress").loaded()
    condition = "assumes it enters untapped: unless you control a Plains or an Island"
    assert [
        (untapped.card, untapped.reading.assumptions)
        for untapped in load.summary.report.assumed_untapped
    ] == [("Glacial Fortress", (condition,))]


# @spec DECK-037
def test_the_report_lists_keyword_readings_made_with_assumptions() -> None:
    load = (
        a_deck_list()
        .with_cards("Homemade Ghast")
        .with_definition(
            name="Homemade Ghast",
            type_line="Creature — Vampire",
            oracle_text="This creature has haste as long as an opponent has 10 or less life.",
        )
        .loaded()
    )
    assert [
        (keyword.card, keyword.keyword, keyword.reading.assumptions)
        for keyword in load.summary.report.keywords_with_assumptions
    ] == [("Homemade Ghast", "haste", (ASSUMES_CONDITION_MET,))]


# @spec DECK-037
def test_the_report_is_empty_for_a_deck_with_nothing_to_report() -> None:
    assert a_deck_list().loaded().summary.report == DeckReport()


# Reading the arguments


def test_a_cards_argument_that_is_not_text_is_malformed() -> None:
    result = read_deck_request(cards=["Sol Ring"], commander=ATRAXA)
    assert result == Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="cards"))


def test_a_commander_argument_that_is_not_a_name_or_list_of_names_is_malformed() -> None:
    result = read_deck_request(cards="Sol Ring", commander=7)
    assert result == Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="commander"))


def test_a_definitions_argument_that_is_not_a_list_is_malformed() -> None:
    result = read_deck_request(cards="Sol Ring", commander=ATRAXA, definitions={"name": "x"})
    assert result == Refusal.error(Error(ErrorKind.MALFORMED_ARGUMENT, subject="definitions"))


# @spec DECK-005
def test_a_malformed_deck_list_line_refuses_before_any_lookup() -> None:
    result = read_deck_request(cards="0 Sol Ring", commander=ATRAXA)
    assert result == Refusal.error(
        Error(ErrorKind.COUNT_NOT_POSITIVE, subject="0 Sol Ring", number=1)
    )


def test_the_names_to_look_up_are_the_commanders_and_every_entry() -> None:
    request = read_deck_request(cards="Sol Ring\n2 Forest", commander=ATRAXA)
    assert not isinstance(request, Refusal)
    assert request.names_to_look_up == (ATRAXA, "Sol Ring", "Forest")
