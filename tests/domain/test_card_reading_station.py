"""The card reader's station reading: how many charge counters make a station card a creature,
and how it reads the abilities after a station symbol."""

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.reading.model import (
    FaceReading,
    KeywordReading,
    StationReading,
)
from mtg_goldfishing.domain.reading.reader import read_card, report
from tests.support.cards import a_card

STATION = (
    "Station (Tap another creature you control: Put charge counters equal to its power on this"
    " Spacecraft. Station only as a sorcery."
)
LABSHIP = a_card(
    "Synthesizer Labship",
    STATION + " It's an artifact creature at 9+.)\n"
    "2+ | At the beginning of combat on your turn, up to one other target artifact you control"
    " becomes an artifact creature with base power and toughness 2/2 and gains flying until end"
    " of turn.\n"
    "9+ | Flying, vigilance",
    "Artifact — Spacecraft",
    pt="4/4",
)
MIRROR_MIGRANT = a_card(
    "U.S.S. Defiant, Mirror Migrant",
    "Flash\nWhen U.S.S. Defiant enters, it and up to one target creature you control phase out.\n"
    "Station\n"
    "3+ | Vigilance\n"
    "8+ | Flying",
    "Legendary Artifact — Spacecraft",
    pt="5/5",
)
DEEP_SPACE_9 = a_card(
    "Deep Space 9",
    "When Deep Space 9 enters and at the beginning of your upkeep, exile the top four cards of"
    " your library. Put all permanent cards exiled this way onto the battlefield.\n"
    + STATION
    + ")\n9+ | Creatures you control get +3/+3.",
    "Legendary Artifact — Spacecraft",
)
ETERNITY_ELEVATOR = a_card(
    "The Eternity Elevator",
    "{T}: Add {C}{C}{C}.\n"
    + STATION
    + ")\n20+ | {T}: Add X mana of any one color, where X is the number of charge counters on"
    " The Eternity Elevator.",
    "Legendary Artifact — Spacecraft",
)
KVORT = a_card(
    "K'Vort-Class Raider",
    "During your turn, this Spacecraft and creatures you control have hexproof.\n"
    + STATION
    + " It's an artifact creature at 4+.)\n4+ | Flying, menace, haste",
    "Artifact — Spacecraft",
    pt="5/5",
)


def face_reading(card: Card) -> FaceReading:
    return read_card(card).faces[0]


# @spec READ-065
def test_the_reminder_text_gives_the_charge_counters_that_make_it_a_creature() -> None:
    assert face_reading(LABSHIP).station == StationReading(creature_at=9)


# @spec READ-066
def test_without_reminder_text_a_station_card_with_power_is_a_creature_at_its_highest_symbol() -> (
    None
):
    assert face_reading(MIRROR_MIGRANT).station == StationReading(
        creature_at=8,
        assumptions=("assumes it is a creature at its highest station symbol",),
    )


# @spec READ-067
def test_a_station_card_with_no_power_and_toughness_never_becomes_a_creature() -> None:
    assert face_reading(DEEP_SPACE_9).station == StationReading(creature_at=None)


# @spec READ-067
def test_a_card_with_no_station_symbols_never_becomes_a_creature() -> None:
    bears = a_card("Grizzly Bears", "", "Creature — Bear", pt="2/2")
    assert face_reading(bears).station == StationReading(creature_at=None)


# @spec READ-067
def test_a_creature_with_station_symbols_gets_no_charge_counters_to_become_one() -> None:
    station_creature = a_card(
        "Station Creature", "Station\n4+ | Flying", "Artifact Creature — Robot", pt="2/2"
    )
    assert face_reading(station_creature).station == StationReading(creature_at=None)


# @spec READ-068
def test_a_keyword_after_a_station_symbol_is_read_with_the_charge_counters_assumed() -> None:
    reading = face_reading(LABSHIP)
    assumed = ("assumes it has 9 or more charge counters",)
    assert reading.flying == KeywordReading(own=True, assumptions=assumed)
    assert reading.vigilance == KeywordReading(own=True, assumptions=assumed)


# @spec READ-068
def test_each_keyword_after_a_station_symbol_assumes_its_own_symbols_number() -> None:
    reading = face_reading(MIRROR_MIGRANT)
    assert reading.vigilance.assumptions == ("assumes it has 3 or more charge counters",)
    assert reading.flying.assumptions == ("assumes it has 8 or more charge counters",)


# @spec READ-068
def test_haste_after_a_station_symbol_is_read_with_the_others_on_its_line() -> None:
    reading = face_reading(KVORT)
    assumed = ("assumes it has 4 or more charge counters",)
    assert reading.haste == KeywordReading(own=True, assumptions=assumed)
    assert reading.flying == KeywordReading(own=True, assumptions=assumed)


# @spec READ-068
def test_a_grant_after_a_station_symbol_is_read_with_the_charge_counters_assumed() -> None:
    flagship = a_card(
        "Flagship", STATION + ")\n6+ | Other creatures you control have haste.", "Artifact"
    )
    assert face_reading(flagship).haste.assumptions == ("assumes it has 6 or more charge counters",)


# @spec READ-069
def test_a_mana_ability_after_a_station_symbol_gets_no_reading() -> None:
    reading = face_reading(ETERNITY_ELEVATOR)
    assert [ability.text for ability in reading.mana_abilities] == ["{T}: Add {C}{C}{C}."]


# @spec READ-070
def test_the_report_lists_station_cards_that_become_creatures_with_their_charge_counters() -> None:
    cards = [LABSHIP, MIRROR_MIGRANT, DEEP_SPACE_9]
    found = report((card, read_card(card)) for card in cards)
    assert [(s.card, s.reading.creature_at, s.reading.assumptions) for s in found.stations] == [
        ("Synthesizer Labship", 9, ()),
        (
            "U.S.S. Defiant, Mirror Migrant",
            8,
            ("assumes it is a creature at its highest station symbol",),
        ),
    ]


# @spec READ-002
def test_a_station_reading_from_reminder_text_carries_no_assumptions() -> None:
    assert face_reading(KVORT).station.assumptions == ()


# @spec READ-071
def test_flash_after_a_station_symbol_is_not_read() -> None:
    late_flash = a_card("Late Flash", STATION + ")\n3+ | Flash", "Artifact — Spacecraft", pt="2/2")
    assert face_reading(late_flash).flash == KeywordReading()


# @spec READ-065
def test_the_reminder_text_is_read_with_a_curly_apostrophe() -> None:
    curly = a_card(
        "Curly Ship",
        STATION + " It\u2019s an artifact creature at 6+.)\n6+ | Flying",
        "Artifact — Spacecraft",
        pt="3/3",
    )
    assert face_reading(curly).station == StationReading(creature_at=6)


# @spec READ-065, READ-067
def test_a_creature_type_line_wins_over_the_reminder_text() -> None:
    odd = a_card(
        "Odd Ship",
        STATION + " It's an artifact creature at 5+.)\n5+ | Flying",
        "Artifact Creature — Spacecraft",
        pt="3/3",
    )
    assert face_reading(odd).station == StationReading(creature_at=None)


# @spec READ-066
def test_a_station_symbol_is_read_with_any_spaces_around_its_bar() -> None:
    tight = a_card("Tight Ship", "Station\n7+|Flying", "Artifact — Spacecraft", pt="3/3")
    assert face_reading(tight).station.creature_at == 7


# @spec READ-069
def test_a_mana_ability_after_a_station_symbol_is_reported_unread_when_colors_are_known() -> None:
    elevator = a_card(
        "The Eternity Elevator",
        ETERNITY_ELEVATOR.faces[0].oracle_text,
        "Legendary Artifact — Spacecraft",
        produced_colors=("W", "U", "B", "R", "G", "C"),
    )
    assert len(face_reading(elevator).unread_mana_abilities) == 1
