"""What every CardCache promises. Add another adapter's cache as one more fixture param."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from mtg_goldfishing.adapters.memory import InMemoryCardCache
from mtg_goldfishing.adapters.sqlite import SqliteCardCache, SqliteDatabase
from mtg_goldfishing.application.ports import CardCache
from mtg_goldfishing.domain.cards import Card, Face
from tests.support.card_data import recorded_card

CacheFactory = Callable[[], CardCache]


# @spec APP-012, STOR-001
@pytest.fixture(params=["memory", "sqlite"])
def new_cache(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[CacheFactory]:
    if request.param == "memory":
        yield InMemoryCardCache
        return
    databases: list[SqliteDatabase] = []

    def sqlite_cache() -> CardCache:
        databases.append(SqliteDatabase(tmp_path / f"cache{len(databases)}.db"))
        return SqliteCardCache(databases[-1])

    yield sqlite_cache
    for database in databases:
        database.close()


def _two_faced(name: str, *faces: str) -> Card:
    return Card(name, tuple(Face(face) for face in faces), layout="modal_dfc")


# @spec CARD-017
def test_a_cache_returns_a_stored_card_by_its_full_name(new_cache: CacheFactory) -> None:
    cache = new_cache()
    cache.put(recorded_card("Sol Ring"))

    assert cache.get("Sol Ring") == recorded_card("Sol Ring")


# @spec CARD-006, CARD-017
def test_a_cache_returns_a_stored_card_by_any_face_name(new_cache: CacheFactory) -> None:
    valki = recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor")
    cache = new_cache()
    cache.put(valki)

    assert (cache.get("Valki, God of Lies"), cache.get("Tibalt, Cosmic Impostor")) == (valki, valki)


# @spec CARD-006
def test_a_cache_ignores_letter_case_and_surrounding_whitespace(new_cache: CacheFactory) -> None:
    cache = new_cache()
    cache.put(recorded_card("Sol Ring"))

    assert cache.get("  sOL rING ") == recorded_card("Sol Ring")


# @spec CARD-006
@pytest.mark.parametrize("name", ["Sol", "Sol Rings", "SolRing", "Arcane Signet", ""])
def test_a_cache_has_nothing_for_a_name_no_stored_card_matches(
    new_cache: CacheFactory, name: str
) -> None:
    cache = new_cache()
    cache.put(recorded_card("Sol Ring"))

    assert cache.get(name) is None


# @spec CARD-021, CARD-024
@pytest.mark.xfail(strict=True, reason="M4: not implemented yet")
@pytest.mark.parametrize(
    "name", ["Gallifrey Falls/No More", "gallifrey falls / no more", " Gallifrey Falls//No More "]
)
def test_a_cache_returns_a_stored_multi_faced_card_by_its_full_name_written_with_slashes(
    new_cache: CacheFactory, name: str
) -> None:
    gallifrey = recorded_card("Gallifrey Falls // No More")
    cache = new_cache()
    cache.put(gallifrey)

    assert cache.get(name) == gallifrey


# @spec CARD-021, CARD-024
@pytest.mark.parametrize(
    "name", ["Gallifrey Falls/No Mor", "No More/Gallifrey Falls", "Gallifrey Falls/No More/No More"]
)
def test_a_cache_has_nothing_for_a_name_with_slashes_naming_no_card_s_faces_in_order(
    new_cache: CacheFactory, name: str
) -> None:
    cache = new_cache()
    cache.put(recorded_card("Gallifrey Falls // No More"))

    assert cache.get(name) is None


# @spec CARD-022
def test_a_cache_returns_the_card_a_name_names_as_written_before_one_whose_faces_it_names(
    new_cache: CacheFactory,
) -> None:
    choco = recorded_card("Summon: Choco/Mog")
    cache = new_cache()
    cache.put(_two_faced("Summon: Choco // Mog", "Summon: Choco", "Mog"))
    cache.put(choco)

    assert cache.get("Summon: Choco/Mog") == choco


def test_an_empty_cache_has_nothing(new_cache: CacheFactory) -> None:
    assert new_cache().get("Sol Ring") is None


# @spec CARD-018
def test_storing_a_card_replaces_the_cached_card_with_the_same_full_name(
    new_cache: CacheFactory,
) -> None:
    cache = new_cache()
    cache.put(Card("Sol Ring", (Face("Sol Ring", oracle_text="old text"),)))
    cache.put(Card("Sol Ring", (Face("Sol Ring", oracle_text="new text"),)))

    assert cache.get("Sol Ring") == Card("Sol Ring", (Face("Sol Ring", oracle_text="new text"),))


# @spec CARD-018
def test_replacing_a_card_retires_face_names_it_no_longer_has(new_cache: CacheFactory) -> None:
    cache = new_cache()
    cache.put(_two_faced("Front // Back", "Front", "Back"))
    cache.put(_two_faced("Front // Back", "Front", "Reverse"))

    assert cache.get("Back") is None


def test_storing_a_card_keeps_the_other_cached_cards(new_cache: CacheFactory) -> None:
    cache = new_cache()
    cache.put(recorded_card("Sol Ring"))
    cache.put(recorded_card("Arcane Signet"))

    assert cache.get("Sol Ring") == recorded_card("Sol Ring")


# @spec CARD-007
def test_a_face_name_shared_by_two_cards_resolves_to_the_card_whose_full_name_sorts_first(
    new_cache: CacheFactory,
) -> None:
    later = _two_faced("Zebra // Shared Face", "Zebra", "Shared Face")
    earlier = _two_faced("Aardvark // Shared Face", "Aardvark", "Shared Face")
    cache = new_cache()
    cache.put(later)
    cache.put(earlier)

    assert cache.get("Shared Face") == earlier


# @spec CARD-007
def test_a_shared_face_name_resolves_the_same_whatever_order_the_cards_were_stored(
    new_cache: CacheFactory,
) -> None:
    later = _two_faced("Zebra // Shared Face", "Zebra", "Shared Face")
    earlier = _two_faced("Aardvark // Shared Face", "Aardvark", "Shared Face")
    cache = new_cache()
    cache.put(earlier)
    cache.put(later)

    assert cache.get("Shared Face") == earlier


def test_a_full_name_resolves_to_that_card_even_when_another_card_has_a_face_of_that_name(
    new_cache: CacheFactory,
) -> None:
    ice = Card("Ice", (Face("Ice"),))
    fire_ice = Card("Fire // Ice", (Face("Fire"), Face("Ice")), layout="split")
    cache = new_cache()
    cache.put(ice)
    cache.put(fire_ice)

    assert cache.get("Ice") == ice
