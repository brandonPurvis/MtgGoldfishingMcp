"""The in-memory card catalog: a fixed set of cards, loaded from recorded card data."""

from mtg_goldfishing.adapters.memory import InMemoryCardCatalog
from mtg_goldfishing.domain.cards import Card, CardLookup, Face, LookupStatus
from tests.support.card_data import recorded_card, recorded_cards


# @spec APP-013
def test_the_in_memory_catalog_supplies_recorded_card_data() -> None:
    catalog = InMemoryCardCatalog(recorded_cards())

    assert catalog.look_up(["Cultivate"])["Cultivate"] == CardLookup(
        LookupStatus.FOUND, recorded_card("Cultivate")
    )


# @spec CARD-007
def test_a_face_name_shared_by_two_cards_gives_the_card_whose_full_name_sorts_first() -> None:
    earlier = Card("Aardvark // Shared", (Face("Aardvark"), Face("Shared")), layout="split")
    later = Card("Zebra // Shared", (Face("Zebra"), Face("Shared")), layout="split")
    catalog = InMemoryCardCatalog([later, earlier])

    assert catalog.look_up(["Shared"])["Shared"].card == earlier


def test_a_name_made_unavailable_is_unavailable_in_any_spelling() -> None:
    catalog = InMemoryCardCatalog(recorded_cards(), unavailable=["Sol Ring"])

    assert catalog.look_up([" sol ring"])[" sol ring"] == CardLookup(LookupStatus.UNAVAILABLE)


def test_a_name_made_unavailable_leaves_other_names_found() -> None:
    catalog = InMemoryCardCatalog(recorded_cards(), unavailable=["Sol Ring"])

    assert catalog.look_up(["Cultivate"])["Cultivate"].status is LookupStatus.FOUND
