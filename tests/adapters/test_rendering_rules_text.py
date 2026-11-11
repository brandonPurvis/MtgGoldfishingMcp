"""The text of rules text on request: `get_state` with `card` answers with a summary counting the
cards, then each card's faces, its rules text indented beneath, in place of the listing."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer
from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.game.model import CardInstance, PendingChoice, TokenSpec, Zone
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from tests.support.acting import S1, S2
from tests.support.builders import Situation, a_game
from tests.support.library import LIBRARY
from tests.support.service import ServiceHarness, a_service

pytestmark = pytest.mark.xfail(strict=True, reason="M3: not implemented yet")

VALKI = "Valki, God of Lies // Tibalt, Cosmic Impostor"


def with_texts(card: Card, *texts: str) -> Card:
    return replace(
        card,
        faces=tuple(
            replace(face, oracle_text=text) for face, text in zip(card.faces, texts, strict=True)
        ),
    )


SOL_RING = with_texts(LIBRARY["Sol Ring"][0], "{T}: Add {C}{C}.")
VALKI_CARD = with_texts(
    LIBRARY[VALKI][0],
    "When Valki enters, each opponent reveals their hand.\n{X}: Choose a creature card.",
    "+2: Exile the top card of each player's library.",
)


def a_table() -> Situation:
    """Seat 1 holds a Sol Ring and a Forest, has Valki in its graveyard and Grizzly Bears in
    its library; seat 2 holds a Shivan Dragon."""
    builder: Any = (
        a_game().with_hand("Sol Ring", "Forest").with_graveyard(VALKI).with_library("Grizzly Bears")
    )
    situation: Situation = builder.and_an_opposing_seat().with_hand("Shivan Dragon").build()
    for card in situation.game.cards:
        if card.name == "Sol Ring":
            card.definition = SOL_RING
        if card.name == VALKI:
            card.definition = VALKI_CARD
    return situation


def held(situation: Situation) -> tuple[ServiceHarness, str]:
    harness = a_service(renderer=TextRenderer())
    return harness, harness.holding(situation)


def asked(harness: ServiceHarness, game_id: str, card: object, **more: object) -> list[str]:
    answer = harness.service.get_state({"game_id": game_id, "card": card, **more})
    return answer.response.splitlines()


def instance(situation: Situation, name: str, owner: SeatNumber) -> CardInstance:
    return next(c for c in situation.game.cards if c.name == name and c.owner == owner)


# @spec TOOL-095, GAME-186
def test_each_card_reads_its_faces_with_their_rules_text_indented_beneath() -> None:
    harness, game_id = held(a_table())

    lines = asked(harness, game_id, ["Sol Ring", "Tibalt, Cosmic Impostor", "Forest"])

    assert lines[:-1] == [
        "OK Rules text of 3 cards.",
        "Sol Ring {1} · Artifact",
        "  {T}: Add {C}{C}.",
        "Valki, God of Lies {1}{B} · Legendary Creature — God 2/1",
        "  When Valki enters, each opponent reveals their hand.",
        "  {X}: Choose a creature card.",
        "// Tibalt, Cosmic Impostor {5}{B}{R} · Legendary Planeswalker — Tibalt",
        "  +2: Exile the top card of each player's library.",
        "Forest · Basic Land — Forest",
    ]


# @spec TOOL-095
def test_one_card_is_counted_as_one_card() -> None:
    harness, game_id = held(a_table())

    assert asked(harness, game_id, "Sol Ring")[0] == "OK Rules text of 1 card."


# @spec GAME-186
def test_the_answer_keeps_the_status_line_and_gives_no_listing() -> None:
    situation = a_table()
    situation.game.pending.append(
        PendingChoice("x1", S1, "Duress", "ask", [], None, asked_by=S2, text="discard")
    )
    harness, game_id = held(situation)

    lines = asked(harness, game_id, "Sol Ring")

    assert lines[-1].startswith("T3 main1 (S1) · You S1 · ")
    assert not any(
        line.startswith(("Hand (", "Your pending choices", "S1 (you)")) for line in lines
    )


# @spec TOOL-096, GAME-188
@pytest.mark.parametrize(
    ("token", "line"),
    [
        (
            TokenSpec(
                "Treasure",
                "Artifact — Treasure",
                produces=tuple(ManaString.parse(m) for m in ("{W}", "{U}", "{B}", "{R}", "{G}")),
            ),
            "Treasure token · Artifact — Treasure · makes {W} or {U} or {B} or {R} or {G}"
            " · no rules text held",
        ),
        (
            TokenSpec("Elf Warrior", "Creature — Elf Warrior", pt="1/1"),
            "Elf Warrior token · Creature — Elf Warrior 1/1 · no rules text held",
        ),
    ],
)
def test_a_token_reads_on_one_line_with_its_types_and_what_it_makes(
    token: TokenSpec, line: str
) -> None:
    situation = a_table()
    situation.game.cards.append(
        CardInstance(
            id=situation.game.new_instance_id(),
            name=token.name,
            zone=Zone.BATTLEFIELD,
            owner=S1,
            controller=S1,
            is_token=True,
            token=token,
        )
    )
    harness, game_id = held(situation)

    assert asked(harness, game_id, token.name)[:2] == ["OK Rules text of 1 card.", line]


# @spec TOOL-097, GAME-194
def test_an_instance_id_in_the_calling_seat_s_library_is_refused_saying_to_ask_by_name() -> None:
    situation = a_table()
    bears = instance(situation, "Grizzly Bears", S1).id
    harness, game_id = held(situation)

    assert asked(harness, game_id, bears)[0] == (
        f"ERROR {bears} is in your library; ask for a library card's rules text by name."
    )


# @spec GAME-191
def test_a_card_answered_by_name_says_neither_its_zone_nor_its_instance_id() -> None:
    situation = a_table()
    bears = instance(situation, "Grizzly Bears", S1).id
    harness, game_id = held(situation)

    lines = asked(harness, game_id, "Grizzly Bears")[:-1]
    text = "\n".join(lines)

    assert lines[1] == "Grizzly Bears {1}{G} · Creature — Bear 2/2"
    assert "library" not in text
    assert bears not in text


# @spec GAME-192, TOOL-068
def test_a_name_held_only_in_another_seat_s_hand_is_refused_word_for_word_as_one_held_nowhere() -> (
    None
):
    harness, game_id = held(a_table())

    held_there = asked(harness, game_id, "Shivan Dragon")[0]
    nowhere = asked(harness, game_id, "Serra Angel")[0]

    assert held_there.startswith("ERROR ")
    assert held_there.replace("Shivan Dragon", "Serra Angel") == nowhere


# @spec GAME-193, TOOL-067
def test_an_instance_id_in_another_seat_s_hand_is_refused_as_in_a_hidden_zone_of_that_seat() -> (
    None
):
    situation = a_table()
    dragon = instance(situation, "Shivan Dragon", S2).id
    harness, game_id = held(situation)

    assert asked(harness, game_id, dragon)[0] == f"ERROR {dragon} is in a hidden zone of S2."


# @spec GAME-195
def test_card_and_detail_together_are_refused_saying_they_are_not_given_together() -> None:
    harness, game_id = held(a_table())

    headline = asked(harness, game_id, "Sol Ring", detail="full")[0]

    assert headline.startswith("ERROR ")
    assert "not both" in headline


# @spec GAME-186, TOOL-051
def test_rules_text_is_answered_in_a_goldfish_game_with_its_status_line() -> None:
    situation = a_game().with_hand("Sol Ring").build()
    situation.game.cards[0].definition = SOL_RING
    harness, game_id = held(situation)

    lines = asked(harness, game_id, "Sol Ring")

    assert lines[:3] == [
        "OK Rules text of 1 card.",
        "Sol Ring {1} · Artifact",
        "  {T}: Add {C}{C}.",
    ]
    assert lines[-1].startswith("T3 main1 · Hand 1 · ")
