"""Reading a deck list: one entry per line, with the formats deck sites export."""

from __future__ import annotations

from mtg_goldfishing.domain.deck.deck_list import parse_deck_list
from mtg_goldfishing.domain.deck.model import DeckEntry
from mtg_goldfishing.domain.events import Error, ErrorKind


def entries(text: str) -> tuple[DeckEntry, ...]:
    result = parse_deck_list(text)
    assert not isinstance(result, Error), result
    return result


def error(text: str) -> Error:
    result = parse_deck_list(text)
    assert isinstance(result, Error), result
    return result


# @spec DECK-001
def test_a_line_with_a_count_and_a_name_is_that_many_of_the_card() -> None:
    assert entries("4 Forest") == (DeckEntry("Forest", 4),)


# @spec DECK-001
def test_a_line_with_a_count_marked_x_is_that_many_of_the_card() -> None:
    assert entries("3x Island") == (DeckEntry("Island", 3),)


# @spec DECK-001
def test_a_bare_name_is_one_of_the_card() -> None:
    assert entries("Sol Ring") == (DeckEntry("Sol Ring", 1),)


# @spec DECK-001
def test_surrounding_whitespace_is_not_part_of_the_name() -> None:
    assert entries("  2   Swamp  \t") == (DeckEntry("Swamp", 2),)


# @spec DECK-001
def test_entries_keep_the_order_of_their_first_lines() -> None:
    assert entries("Sol Ring\n2 Forest\nArcane Signet") == (
        DeckEntry("Sol Ring", 1),
        DeckEntry("Forest", 2),
        DeckEntry("Arcane Signet", 1),
    )


# @spec DECK-002
def test_blank_lines_and_comment_lines_are_ignored() -> None:
    text = "# Ramp\n\n   \n// Lands\n1 Sol Ring\n  # indented comment\n"
    assert entries(text) == (DeckEntry("Sol Ring", 1),)


# @spec DECK-002
def test_a_list_of_only_comments_has_no_entries() -> None:
    assert entries("# nothing here\n// nor here") == ()


# @spec DECK-003
def test_a_set_code_and_everything_after_it_is_dropped() -> None:
    assert entries("1 Sol Ring (C21) 263 *F*") == (DeckEntry("Sol Ring", 1),)


# @spec DECK-003
def test_a_set_code_is_dropped_from_a_bare_name() -> None:
    assert entries("Arcane Signet (CMR) 297") == (DeckEntry("Arcane Signet", 1),)


# @spec DECK-004
def test_counts_of_a_card_on_several_lines_are_added_together() -> None:
    assert entries("10 Forest\nSol Ring\n5x Forest") == (
        DeckEntry("Forest", 15),
        DeckEntry("Sol Ring", 1),
    )


# @spec DECK-004
def test_lines_naming_a_card_in_different_letter_case_are_the_same_card() -> None:
    assert entries("2 forest\n3 FOREST") == (DeckEntry("forest", 5),)


# @spec DECK-005
def test_a_count_of_zero_is_an_error_naming_the_line() -> None:
    assert error("1 Sol Ring\n0 Forest") == Error(
        ErrorKind.COUNT_NOT_POSITIVE, subject="0 Forest", number=2
    )


# @spec DECK-005
def test_a_negative_count_is_an_error_naming_the_line() -> None:
    assert error("-2x Forest") == Error(
        ErrorKind.COUNT_NOT_POSITIVE, subject="-2x Forest", number=1
    )


def test_a_count_with_no_name_is_an_unreadable_line() -> None:
    assert error("Sol Ring\n4x") == Error(ErrorKind.LINE_UNREADABLE, subject="4x", number=2)


def test_a_line_that_is_only_printing_details_is_unreadable() -> None:
    assert error("1 (C21) 263") == Error(ErrorKind.LINE_UNREADABLE, subject="1 (C21) 263", number=1)
