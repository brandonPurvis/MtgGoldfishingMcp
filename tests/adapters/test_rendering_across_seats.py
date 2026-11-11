"""The text a seat reads when effects reach across seats: hidden-zone errors, damage and life per
seat, changes of control, choices addressed to a seat, combat against seats, eliminations and
their notices."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.rendering import TextRenderer, digest_line, event_lines
from mtg_goldfishing.application.outcome import DigestElement, Outcome, Status
from mtg_goldfishing.domain import events
from mtg_goldfishing.domain.combat.attack import attack
from mtg_goldfishing.domain.events import Refused
from mtg_goldfishing.domain.game.ending import end_game
from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.game.seeing import as_seen_by
from mtg_goldfishing.domain.game.summary import summarize
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect
from mtg_goldfishing.domain.turn import advance
from tests.support.acting import S1, S2, S3, acted
from tests.support.builders import Situation, a_game

RENDERER = TextRenderer()
ATRAXA = "Atraxa, Praetors' Voice"


def three_seats() -> Situation:
    builder: Any = a_game().with_battlefield("Grizzly Bears").with_library("Forest")
    builder = builder.and_an_opposing_seat().with_hand("Island", "Lightning Bolt")
    return builder.with_battlefield("Llanowar Elves").and_an_opposing_seat().build()


def response(tool: str, situation: Situation, seat: SeatNumber, result: Any) -> str:
    """The text answering `seat`'s call, its events as that seat may see them."""
    if isinstance(result, Refusal):
        outcome = Outcome(
            Status.ERROR,
            Refused(result.errors, result.checks),
            (),
            summarize(situation.game, situation.deck, seat),
        )
        return RENDERER.render(tool, outcome).response
    assert isinstance(result, Applied), result
    (summary, *events) = as_seen_by((result.summary, *result.events), seat)
    waiting = result.game.pending
    status = Status.CHOICE if waiting and waiting[0].seat == seat else Status.OK
    outcome = Outcome(status, summary, tuple(events), summarize(result.game, situation.deck, seat))
    return RENDERER.render(tool, outcome).response


def recorded(situation: Situation, delta: object, seat: SeatNumber = S1) -> Any:
    return effect(
        situation.game, situation.deck, seat, source="a test effect", delta=delta, immediate=True
    )


# ------------------------------------------------------------------ hidden zones


# @spec TOOL-067
def test_an_instance_id_in_another_seat_s_hand_reads_as_a_hidden_zone_of_that_seat() -> None:
    situation = three_seats()
    bolt = next(c.id for c in situation.game.cards if c.name == "Lightning Bolt")
    text = response("effect", situation, S1, recorded(situation, {"discard": [bolt]}))
    assert text.splitlines()[0] == (
        f"ERROR {bolt} is in a hidden zone of S2."
        " Other seats' hands and libraries are reached through ask."
    )
    assert "Lightning Bolt" not in text


# @spec TOOL-068
def test_a_name_another_seat_holds_out_of_sight_reads_as_one_held_nowhere() -> None:
    held = three_seats()
    nowhere: Any = a_game().with_battlefield("Grizzly Bears").with_library("Forest")
    nowhere = nowhere.and_an_opposing_seat().with_hand("Island").and_an_opposing_seat().build()
    delta = {"move": {"exile": ["Lightning Bolt"]}}
    first = response("effect", held, S1, recorded(held, delta)).splitlines()[0]
    second = response("effect", nowhere, S1, recorded(nowhere, delta)).splitlines()[0]
    assert first == second
    assert first.endswith("Other seats' hands and libraries are reached through ask.")


# ------------------------------------------------------------------ deltas across seats


# @spec PLAY-092
def test_damage_and_life_per_seat_read_with_the_seat_they_changed() -> None:
    situation = three_seats()
    result = recorded(situation, {"life": {"3": 2}, "damage": {"2": 3}})
    lines = response("effect", situation, S1, result).splitlines()
    assert "S3 life +2, now 42." in lines
    assert "S2 took 3 damage; life now 37." in lines


# @spec PLAY-094
def test_a_change_of_control_names_the_new_controller() -> None:
    situation = three_seats()
    result = recorded(situation, {"control": {"1": ["Llanowar Elves"]}})
    assert "S1 now controls Llanowar Elves." in response("effect", situation, S1, result)


# @spec PLAY-097
def test_an_ask_reads_as_a_choice_for_the_seat_it_is_addressed_to() -> None:
    situation = three_seats()
    result = acted(situation, recorded(situation, {"ask": [{"seats": [2], "text": "discard"}]}))
    choice = situation.game.pending[0].choice_id
    caller = response("effect", situation, S1, result).splitlines()
    assert caller[0].startswith("OK ")
    assert f"Choice {choice} (ask) for S2: discard." in caller
    assert caller[-1].endswith(f"Act S2 ask · #{situation.game.change}")


# @spec GAME-090, GAME-094
def test_another_seat_reads_a_look_at_a_hand_without_its_cards() -> None:
    situation = three_seats()
    result = recorded(situation, {"look_at_hand": 2})
    looker = response("effect", situation, S1, result)
    other = response("effect", situation, S3, result)
    assert "Lightning Bolt" in looker
    assert "Lightning Bolt" not in other
    assert "S1 looks at S2's hand (CHOICE hand)." in other.splitlines()


# ------------------------------------------------------------------ combat


# @spec CMBT-031
def test_an_attack_reads_with_the_seat_each_attacker_attacks() -> None:
    situation = three_seats()
    result = attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"], targets=3)  # type: ignore[call-arg]
    assert "Attacking S3 with Grizzly Bears." in response("attack", situation, S1, result)


# @spec CMBT-037, TOOL-079
def test_blocks_asked_of_a_seat_read_with_the_attackers_attacking_it() -> None:
    situation = three_seats()
    acted(
        situation,
        attack(situation.game, situation.deck, S1, attackers=["Grizzly Bears"], targets=2),  # type: ignore[call-arg]
    )
    result = acted(situation, advance(situation.game, situation.deck, S1, to="declare_blockers"))
    choice = situation.game.pending[0].choice_id
    lines = response("advance", situation, S1, result).splitlines()
    bears = next(c.id for c in situation.game.cards if c.name == "Grizzly Bears")
    assert f"Choice {choice} (blocks) for S2: attacked by Grizzly Bears ({bears})." in lines
    assert lines[-1].endswith(f"Act S2 blocks · #{situation.game.change}")


# @spec CMBT-066
def test_combat_damage_reads_per_attacker_with_each_damaged_seat_s_totals() -> None:
    builder: Any = a_game().with_commander(ATRAXA, zone=Zone.BATTLEFIELD)
    situation = builder.and_an_opposing_seat().build()
    acted(situation, attack(situation.game, situation.deck, S1, attackers=[ATRAXA]))
    result = advance(situation.game, situation.deck, S1, to="combat_damage")
    lines = response("advance", situation, S1, result).splitlines()
    assert f"{ATRAXA} dealt 4 combat damage to S2." in lines
    assert f"S2 life now 36; commander damage from {ATRAXA} 4." in lines


# ------------------------------------------------------------------ elimination


# @spec GAME-138
@pytest.mark.parametrize(
    ("delta", "line"),
    [
        ({"damage": {"2": 40}}, "S2 is eliminated: its life is 0 or less."),
        ({"life": {"3": -40}}, "S3 is eliminated: its life is 0 or less."),
    ],
)
def test_an_elimination_reads_with_the_seat_and_why(delta: object, line: str) -> None:
    situation = three_seats()
    assert line in response("effect", situation, S1, recorded(situation, delta)).splitlines()


# @spec GAME-138, GAME-131
def test_a_concession_reads_as_the_seat_conceding() -> None:
    situation = three_seats()
    result = end_game(situation.game, situation.deck, S2, result="loss", notes="beaten")
    lines = response("end_game", situation, S2, result).splitlines()
    assert lines[0] == "OK S2 conceded and is eliminated."
    assert lines[-1].startswith("Out · ")


# @spec GAME-142, GAME-143
def test_the_elimination_notices_read_on_every_later_response() -> None:
    situation = three_seats()
    acted(situation, recorded(situation, {"damage": {"2": 40, "3": 40}}))
    result = recorded(situation, {"life": -40})
    lines = response("effect", situation, S1, result).splitlines()
    assert "Notice: every opposing seat has been eliminated" in lines
    assert "Notice: the tested seat has been eliminated" in lines


# ------------------------------------------------------------------ moves that name a seat


def a_move(card: str, from_zone: str, to: str, **seats: SeatNumber) -> Any:
    made: Any = events.CardMoved
    return made(card, from_zone, to, **seats)


def event_text(event: Any) -> list[str]:
    return event_lines(event)


# @spec TOOL-094
@pytest.mark.parametrize(
    ("move", "seats", "line"),
    [
        (
            ("Sol Ring", "graveyard", "battlefield"),
            {"from_seat": S2},
            "Moved Sol Ring: S2's graveyard → battlefield.",
        ),
        (
            ("Grizzly Bears", "battlefield", "hand"),
            {"from_seat": S3, "to_seat": S3},
            "Moved Grizzly Bears: S3's battlefield → S3's hand.",
        ),
        (
            ("Grizzly Bears", "battlefield", "library_top"),
            {"from_seat": S2, "to_seat": S2},
            "Moved Grizzly Bears: S2's battlefield → top of S2's library.",
        ),
        (
            ("Shivan Dragon", "stack", "graveyard"),
            {"to_seat": S2},
            "Moved Shivan Dragon: stack → S2's graveyard.",
        ),
        (
            ("Sol Ring", "exile", "command"),
            {"from_seat": S2, "to_seat": S2},
            "Moved Sol Ring: S2's exile → S2's command zone.",
        ),
    ],
)
def test_a_move_names_the_seat_of_each_zone_the_event_names_one_for(
    move: tuple[str, str, str], seats: dict[str, SeatNumber], line: str
) -> None:
    assert event_text(a_move(*move, **seats)) == [line]


# @spec TOOL-094
def test_a_digest_line_names_the_reading_seat_s_own_zone_like_any_other_seat_s() -> None:
    moved = a_move("Sol Ring", "graveyard", "battlefield", from_seat=S2)

    line = digest_line(DigestElement(S1, 5, (moved,)))

    assert line == "S1 #5: Moved Sol Ring: S2's graveyard → battlefield"


# @spec TOOL-094, PLAY-144
def test_a_seat_that_moves_another_seat_s_card_reads_that_seat_in_its_response() -> None:
    situation = three_seats()
    situation.game.cards[-1].zone = Zone.GRAVEYARD
    result = recorded(situation, {"move": {"battlefield": ["Llanowar Elves"]}})

    assert (
        "Moved Llanowar Elves: S2's graveyard → battlefield."
        in response("effect", situation, S1, result).splitlines()
    )


# @spec TOOL-094, PLAY-146
def test_a_card_placed_from_another_seat_s_hand_reads_both_seats_zones() -> None:
    situation = three_seats()
    acted(situation, recorded(situation, {"look_at_hand": 2}))
    choice = situation.game.pending[0].choice_id
    choosing: Any = choose
    result = choosing(
        situation.game,
        situation.deck,
        S1,
        choice_id=choice,
        selections={"graveyard": ["Lightning Bolt"]},
    )

    assert response("choose", situation, S1, result).splitlines()[0] == (
        "OK Placed the revealed cards: Lightning Bolt from S2's hand → S2's graveyard."
    )


# @spec TOOL-094
def test_a_goldfish_move_reads_its_zones_alone() -> None:
    assert event_text(a_move("Forest", "graveyard", "hand")) == ["Moved Forest: graveyard → hand."]
