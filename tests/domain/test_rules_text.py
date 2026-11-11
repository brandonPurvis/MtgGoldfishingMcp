"""Rules text on request: `get_state` with `card` answers the rules text of the cards the
calling seat names and may see, by name or instance id, once each, and refuses the whole call
when any entry is refused."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.deck.model import DeckCard, LoadedDeck
from mtg_goldfishing.domain.events import Error
from mtg_goldfishing.domain.game.decks import Decks
from mtg_goldfishing.domain.game.model import (
    CardInstance,
    PendingChoice,
    TokenSpec,
    Zone,
)
from mtg_goldfishing.domain.game.rules_text import RulesText, rules_text
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from tests.support.acting import S1, S2, S3
from tests.support.builders import Situation, a_game
from tests.support.library import LIBRARY

pytestmark = pytest.mark.xfail(strict=True, reason="M3: not implemented yet")

SOL_RING = LIBRARY["Sol Ring"][0]
FOREST = LIBRARY["Forest"][0]
VALKI = LIBRARY["Valki, God of Lies // Tibalt, Cosmic Impostor"][0]
SHIVAN = LIBRARY["Shivan Dragon"][0]
BEARS = LIBRARY["Grizzly Bears"][0]
TREASURE = TokenSpec(
    "Treasure", "Artifact — Treasure", produces=tuple(ManaString.parse(m) for m in ("{W}", "{U}"))
)


def asked(
    situation: Situation,
    card: object,
    seat: SeatNumber = S1,
    *,
    decks: Decks | None = None,
    detail: object = None,
) -> RulesText | Error:
    every = decks or Decks.everyone_playing(situation.game, situation.deck)
    return rules_text(situation.game, every, seat, card, detail=detail)


def cards_of(answer: RulesText | Error) -> tuple[Card | TokenSpec, ...]:
    assert isinstance(answer, RulesText), answer
    return answer.cards


def kind_of(answer: RulesText | Error) -> str:
    assert isinstance(answer, Error), answer
    return answer.kind.value


def a_table() -> Situation:
    """Seat 1 holds a Sol Ring in hand and a Forest on the battlefield, Valki in its graveyard
    and Grizzly Bears in its library; seat 2 holds a Shivan Dragon in hand and a Forest in its
    library."""
    builder: Any = (
        a_game()
        .with_hand("Sol Ring")
        .with_battlefield("Forest")
        .with_graveyard("Valki, God of Lies // Tibalt, Cosmic Impostor")
        .with_library("Grizzly Bears")
    )
    situation: Situation = (
        builder.and_an_opposing_seat().with_hand("Shivan Dragon").with_library("Forest").build()
    )
    return situation


def instance(situation: Situation, name: str, owner: SeatNumber) -> CardInstance:
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


def carrying(situation: Situation, name: str, owner: SeatNumber, data: Card) -> None:
    """The instance carries card data of its own, as a card brought from outside does."""
    instance(situation, name, owner).definition = data


def with_text(card: Card, text: str) -> Card:
    return replace(card, faces=(replace(card.front, oracle_text=text),))


# ------------------------------------------------------------------ what is answered


# @spec GAME-186, GAME-187
def test_a_card_named_is_answered_with_its_card_data_in_a_contested_game() -> None:
    assert cards_of(asked(a_table(), "Sol Ring")) == (SOL_RING,)


# @spec GAME-186
def test_a_card_named_is_answered_in_a_goldfish_game_too() -> None:
    situation = a_game().with_battlefield("Sol Ring").build()

    assert cards_of(asked(situation, "Sol Ring")) == (SOL_RING,)


# @spec GAME-186
def test_a_list_of_entries_is_answered_card_by_card_in_the_order_given() -> None:
    situation = a_table()
    forest = instance(situation, "Forest", S1).id

    assert cards_of(asked(situation, ["Sol Ring", forest])) == (SOL_RING, FOREST)


# @spec GAME-187
def test_a_card_with_both_faces_is_answered_with_every_face() -> None:
    (valki,) = cards_of(asked(a_table(), "Valki, God of Lies"))

    assert isinstance(valki, Card)
    assert [face.name for face in valki.faces] == ["Valki, God of Lies", "Tibalt, Cosmic Impostor"]


# @spec GAME-187
def test_a_card_instance_carrying_its_own_card_data_is_answered_with_that_data() -> None:
    situation = a_table()
    own = with_text(SOL_RING, "{T}: Add {C}{C}{C}.")
    carrying(situation, "Sol Ring", S1, own)

    assert cards_of(asked(situation, "Sol Ring")) == (own,)


# @spec GAME-187
def test_a_card_is_answered_from_its_owner_s_deck_whichever_seat_controls_it() -> None:
    builder: Any = a_game().and_an_opposing_seat().with_battlefield("Sol Ring")
    situation = builder.controlled_by("Sol Ring", 1).build()
    owners = with_text(SOL_RING, "the opposing deck's Sol Ring")
    opposing = LoadedDeck(
        "dother",
        situation.deck.commanders,
        situation.deck.entries,
        (DeckCard(owners, LIBRARY["Sol Ring"][1]),),
    )
    decks = Decks({S1: situation.deck, S2: opposing})

    assert cards_of(asked(situation, "Sol Ring", decks=decks)) == (owners,)


# @spec GAME-188
def test_a_token_is_answered_with_its_spec() -> None:
    situation = a_table()
    situation.game.cards.append(
        CardInstance(
            id=situation.game.new_instance_id(),
            name="Treasure",
            zone=Zone.BATTLEFIELD,
            owner=S1,
            controller=S1,
            is_token=True,
            token=TREASURE,
        )
    )

    assert cards_of(asked(situation, "treasure")) == (TREASURE,)


# @spec GAME-189
def test_a_card_named_twice_is_answered_once_in_the_place_of_its_first_entry() -> None:
    situation = a_table()
    forest = instance(situation, "Forest", S1).id

    answer = asked(situation, ["Forest", "Sol Ring", "forest", forest])

    assert cards_of(answer) == (FOREST, SOL_RING)


# @spec GAME-189
def test_two_copies_with_the_same_data_in_different_zones_are_answered_once() -> None:
    builder: Any = a_game().with_hand("Forest").with_battlefield("Forest")
    situation = builder.build()
    ids = [card.id for card in situation.game.cards if card.name == "Forest"]

    assert cards_of(asked(situation, ids)) == (FOREST,)


# @spec GAME-189
def test_two_copies_with_different_data_are_each_answered() -> None:
    situation = a_game().with_hand("Sol Ring").with_battlefield("Sol Ring").build()
    on_battlefield = situation.game.in_zone(Zone.BATTLEFIELD, S1)[0]
    own = with_text(SOL_RING, "a Sol Ring brought from outside")
    on_battlefield.definition = own
    in_hand = situation.game.in_zone(Zone.HAND, S1)[0]

    assert cards_of(asked(situation, [in_hand.id, on_battlefield.id])) == (SOL_RING, own)


# ------------------------------------------------------------------ where a name is looked for


# @spec GAME-190
def test_a_name_is_looked_for_ignoring_case_and_by_face_name() -> None:
    assert cards_of(asked(a_table(), "TIBALT, COSMIC IMPOSTOR")) == (VALKI,)


# @spec GAME-190
def test_a_name_is_found_in_the_calling_seat_s_own_hand_before_the_battlefield() -> None:
    situation = a_game().with_hand("Sol Ring").with_battlefield("Sol Ring").build()
    situation.game.in_zone(Zone.BATTLEFIELD, S1)[0].definition = with_text(SOL_RING, "elsewhere")

    assert cards_of(asked(situation, "Sol Ring")) == (SOL_RING,)


# @spec GAME-190
def test_a_name_is_found_on_another_seat_s_battlefield() -> None:
    situation = a_game().and_an_opposing_seat().with_battlefield("Shivan Dragon").build()

    assert cards_of(asked(situation, "Shivan Dragon")) == (SHIVAN,)


# @spec GAME-190
def test_a_name_is_found_in_a_public_zone_before_the_calling_seat_s_own_library() -> None:
    builder: Any = a_game().with_library("Sol Ring")
    situation = builder.and_an_opposing_seat().with_battlefield("Sol Ring").build()
    instance(situation, "Sol Ring", S2).definition = with_text(SOL_RING, "the public one")

    assert cards_of(asked(situation, "Sol Ring")) == (with_text(SOL_RING, "the public one"),)


# @spec GAME-190
def test_a_name_is_found_on_the_stack() -> None:
    situation = a_game().and_an_opposing_seat().with_spell_on_stack("Shivan Dragon").build()

    assert cards_of(asked(situation, "Shivan Dragon")) == (SHIVAN,)


# @spec GAME-190
def test_a_name_is_found_among_cards_a_waiting_pending_choice_reveals_to_the_calling_seat() -> None:
    situation = a_table()
    dragon = instance(situation, "Shivan Dragon", S2)
    situation.game.pending.append(
        PendingChoice("x1", S1, "Duress", "hand", [dragon.id], None, asked_by=S1, hand_of=S2)
    )

    assert cards_of(asked(situation, "Shivan Dragon")) == (SHIVAN,)


# @spec GAME-190
def test_a_name_is_found_in_the_calling_seat_s_own_library() -> None:
    assert cards_of(asked(a_table(), "Grizzly Bears")) == (BEARS,)


# @spec GAME-191
def test_the_answer_for_a_name_is_the_same_whichever_zone_holds_the_card() -> None:
    in_library = asked(a_table(), "Grizzly Bears")
    on_battlefield = asked(a_game().with_battlefield("Grizzly Bears").build(), "Grizzly Bears")

    assert in_library == on_battlefield


# ------------------------------------------------------------------ refusals


# @spec GAME-192
def test_a_name_matching_no_card_the_seat_may_see_is_not_found() -> None:
    assert kind_of(asked(a_table(), "Black Lotus")) == "no_card_seen"


# @spec GAME-192
def test_a_name_held_only_in_another_seat_s_hand_or_library_gets_the_same_error_as_none() -> None:
    situation = a_table()

    held = asked(situation, "Shivan Dragon")
    unheld = asked(situation, "Serra Angel")

    assert isinstance(held, Error)
    assert isinstance(unheld, Error)
    assert (held.kind, held.subject) == (unheld.kind, "Shivan Dragon")


# @spec GAME-192
@pytest.mark.parametrize("instance_id", ["c999", "C999"])
def test_an_instance_id_never_issued_is_not_found(instance_id: str) -> None:
    assert kind_of(asked(a_table(), instance_id)) == "no_card_seen"


# @spec GAME-192
def test_an_instance_id_of_a_token_that_left_the_game_is_not_found() -> None:
    situation = a_table()
    gone = situation.game.new_instance_id()

    assert kind_of(asked(situation, gone)) == "no_card_seen"


# @spec GAME-193
def test_an_instance_id_in_another_seat_s_hand_is_in_a_hidden_zone_of_that_seat() -> None:
    situation = a_table()
    dragon = instance(situation, "Shivan Dragon", S2)

    answer = asked(situation, dragon.id)

    assert isinstance(answer, Error)
    assert (answer.kind.value, answer.subject, answer.number) == ("hidden_zone", dragon.id, 2)


# @spec GAME-193
def test_an_instance_id_in_another_seat_s_library_is_in_a_hidden_zone_of_that_seat() -> None:
    situation = a_table()

    answer = asked(situation, instance(situation, "Forest", S2).id)

    assert kind_of(answer) == "hidden_zone"


# @spec GAME-193
def test_an_instance_id_another_seat_s_card_revealed_to_the_calling_seat_is_answered() -> None:
    situation = a_table()
    dragon = instance(situation, "Shivan Dragon", S2)
    situation.game.pending.append(
        PendingChoice("x1", S1, "Duress", "hand", [dragon.id], None, asked_by=S1, hand_of=S2)
    )

    assert cards_of(asked(situation, dragon.id)) == (SHIVAN,)


# @spec GAME-193
def test_a_card_revealed_to_another_seat_is_not_answered_to_the_calling_seat() -> None:
    builder: Any = a_game().and_an_opposing_seat().with_hand("Shivan Dragon")
    situation = builder.and_an_opposing_seat().build()
    dragon = instance(situation, "Shivan Dragon", S2)
    situation.game.pending.append(
        PendingChoice("x1", S3, "Duress", "hand", [dragon.id], None, asked_by=S3, hand_of=S2)
    )

    assert kind_of(asked(situation, dragon.id)) == "hidden_zone"


# @spec GAME-194
def test_an_instance_id_in_the_calling_seat_s_own_library_is_refused_saying_to_ask_by_name() -> (
    None
):
    situation = a_table()
    bears = instance(situation, "Grizzly Bears", S1)

    answer = asked(situation, bears.id)

    assert isinstance(answer, Error)
    assert (answer.kind.value, answer.subject) == ("library_card_by_id", bears.id)


# @spec GAME-194
def test_an_instance_id_in_the_own_library_revealed_by_a_waiting_choice_is_answered() -> None:
    situation = a_table()
    bears = instance(situation, "Grizzly Bears", S1)
    situation.game.pending.append(PendingChoice("x1", S1, "Ponder", "look", [bears.id], None))

    assert cards_of(asked(situation, bears.id)) == (BEARS,)


# @spec GAME-195
def test_card_together_with_detail_is_an_error() -> None:
    assert kind_of(asked(a_table(), "Sol Ring", detail="full")) == "card_with_detail"


# @spec GAME-195
def test_a_detail_given_as_null_counts_as_not_given() -> None:
    assert cards_of(asked(a_table(), "Sol Ring", detail=None)) == (SOL_RING,)


# @spec GAME-197
@pytest.mark.parametrize("card", [7, [], ["Sol Ring", 7], "   ", ["Sol Ring", " "], {"a": 1}])
def test_a_card_that_is_not_a_text_or_a_non_empty_list_of_texts_is_malformed(card: object) -> None:
    answer = asked(a_table(), card)

    assert isinstance(answer, Error)
    assert (answer.kind.value, answer.subject) == ("malformed_argument", "card")


# @spec GAME-197
def test_an_entry_is_taken_with_its_surrounding_whitespace_removed() -> None:
    assert cards_of(asked(a_table(), "  Sol Ring \n")) == (SOL_RING,)


# @spec GAME-196
def test_one_refused_entry_refuses_the_call_with_the_first_refused_entry_s_error() -> None:
    situation = a_table()
    bears = instance(situation, "Grizzly Bears", S1).id

    answer = asked(situation, ["Sol Ring", "Black Lotus", bears])

    assert isinstance(answer, Error)
    assert (answer.kind.value, answer.subject) == ("no_card_seen", "Black Lotus")
