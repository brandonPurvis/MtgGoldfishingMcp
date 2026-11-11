"""The tool parameters through which seats reach one another: targets for attackers, answers to
choices addressed to a seat, and the immediate effect that states the result of combat."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_goldfishing.adapters.mcp.definitions import TOOL_DEFINITIONS
from mtg_goldfishing.adapters.mcp.parameters import Shaped, shape

DEFINITIONS = {definition.name: definition for definition in TOOL_DEFINITIONS}


def parameter(tool: str, name: str) -> Any:
    return next((p for p in DEFINITIONS[tool].parameters if p.name == name), None)


# @spec CMBT-030, CMBT-031
@pytest.mark.parametrize("targets", [2, {"Grizzly Bears": 3}, '{"Grizzly Bears": 3}'])
def test_attack_takes_targets_as_one_seat_number_or_a_map(targets: object) -> None:
    arguments = {"game_id": "g1", "attackers": ["Grizzly Bears"], "targets": targets}
    assert isinstance(shape(DEFINITIONS["attack"].parameters, arguments), Shaped)


# @spec CMBT-039, PLAY-099
@pytest.mark.parametrize(
    "answer",
    [{"blocks": {"Llanowar Elves": "Grizzly Bears"}}, {"delta": {"discard": ["Island"]}}, {}],
    ids=["blocks", "an ask's delta", "nothing"],
)
def test_choose_takes_blocks_or_a_delta_in_place_of_selections(answer: dict[str, object]) -> None:
    arguments = {"game_id": "g1", "choice_id": "x1", **answer}
    assert isinstance(shape(DEFINITIONS["choose"].parameters, arguments), Shaped)


# @spec CMBT-045
def test_choose_takes_an_override_for_the_rule_checks_on_blockers() -> None:
    arguments = {"game_id": "g1", "choice_id": "x1", "blocks": {}, "override": "it can block"}
    assert isinstance(shape(DEFINITIONS["choose"].parameters, arguments), Shaped)


# @spec PLAY-084, CMBT-051
def test_effect_takes_immediate() -> None:
    arguments = {"game_id": "g1", "source": "combat", "delta": {}, "immediate": True}
    assert isinstance(shape(DEFINITIONS["effect"].parameters, arguments), Shaped)


# @spec TOOL-069
def test_effect_says_a_combat_result_gives_only_what_happens_to_the_creatures() -> None:
    immediate = parameter("effect", "immediate")
    assert immediate is not None
    assert immediate.meaning.startswith("Contested games: ")
    for words in ("combat_damage", "only what happens to the creatures", "in addition"):
        assert words in immediate.meaning, words


# @spec TOOL-070
def test_attack_says_a_blocked_attacker_deals_no_combat_damage_unless_trample_is_stated() -> None:
    trample = parameter("attack", "trample")
    assert trample is not None
    assert trample.meaning.startswith("Contested games: ")
    description = DEFINITIONS["attack"].description
    for words in (
        "A blocked attacker deals no combat damage to the seat it attacks",
        "its damage entry included",
        "once blocks are known and before combat damage",
        "trample and no attackers",
    ):
        assert words in description, words
    assert "dealt in full" not in description


# @spec TOOL-076
def test_attack_says_evasion_states_flying_horsemanship_or_can_t_be_blocked_per_attacker() -> None:
    evasion = parameter("attack", "evasion")
    assert evasion is not None
    assert evasion.meaning.startswith("Contested games: ")
    for words in (
        "flying",
        "horsemanship",
        "can't be blocked (unblockable)",
        "beyond what the service has read",
        "for this declaration only",
        "refused as a rule check",
    ):
        assert words in evasion.meaning, words


# @spec TOOL-077
def test_choose_says_a_block_forbidden_by_evasion_fails_a_rule_check_overridden_for_this_turn() -> (
    None
):
    description = DEFINITIONS["choose"].description
    contested = description[description.index("Contested games:") :]
    for words in (
        "flying, horsemanship or can't be blocked forbids",
        "fails a rule check",
        "flying or reach only for this turn",
        "override giving that reason",
    ):
        assert words in contested, words


# @spec CMBT-080, TOOL-076
@pytest.mark.parametrize(
    "evasion", [{"Grizzly Bears": "flying"}, {"Grizzly Bears": ["flying", "unblockable"]}]
)
def test_attack_takes_evasion_as_a_map_from_attacker_to_an_evasion_or_a_list(
    evasion: object,
) -> None:
    arguments = {"game_id": "g1", "attackers": ["Grizzly Bears"], "evasion": evasion}
    assert isinstance(shape(DEFINITIONS["attack"].parameters, arguments), Shaped)


# @spec CMBT-098, TOOL-070
def test_attack_takes_trample_alone_without_attackers() -> None:
    arguments = {"game_id": "g1", "trample": {"Shivan Dragon": 3}}
    assert isinstance(shape(DEFINITIONS["attack"].parameters, arguments), Shaped)


# @spec TOOL-071
def test_attack_says_it_may_stop_undeclared_where_another_seat_has_a_reminder() -> None:
    description = DEFINITIONS["attack"].description
    contested = description[description.index("Contested games:") :]
    for words in ("reminder", "nothing is declared or tapped", "send attack again"):
        assert words in contested, words


# ------------------------------------------------------------------ cast triggers and answer text

NOT_BUILT = pytest.mark.xfail(strict=True, reason="M2: not implemented yet")


def contested_part(tool: str) -> str:
    description = DEFINITIONS[tool].description
    return description[description.index("Contested games:") :]


# @spec TOOL-081
@NOT_BUILT
def test_play_describes_cast_triggers_for_every_game() -> None:
    cast_triggers = parameter("play", "cast_triggers")
    assert cast_triggers is not None
    assert not cast_triggers.meaning.startswith("Contested games: ")
    for words in ("source", "delta", "choices", "before the spell", "first listed first", "land"):
        assert words in cast_triggers.meaning, words


# @spec TOOL-081
@NOT_BUILT
def test_play_gives_one_example_of_the_whole_cast_triggers_parameter() -> None:
    cast_triggers = parameter("play", "cast_triggers")
    assert cast_triggers is not None
    (example,) = cast_triggers.example
    assert set(example) >= {"source", "delta"}


# @spec TOOL-081, TOOL-010
@NOT_BUILT
def test_play_takes_cast_triggers_as_a_list_or_a_json_string() -> None:
    for triggers in ([{"source": "x", "delta": {}}], '[{"source": "x", "delta": {}}]'):
        arguments = {"game_id": "g1", "card": "Lightning Bolt", "cast_triggers": triggers}
        assert isinstance(shape(DEFINITIONS["play"].parameters, arguments), Shaped)


# @spec TOOL-082
@NOT_BUILT
def test_play_says_cast_triggers_go_on_the_stack_above_the_spell_before_any_seat_is_asked() -> None:
    contested = contested_part("play")
    for words in (
        "cast triggers",
        "above the spell",
        "before any seat is asked",
        "resolves within",
    ):
        assert words in contested, words


# @spec TOOL-083
@NOT_BUILT
def test_choose_says_an_ask_answer_may_carry_public_answer_text() -> None:
    contested = contested_part("choose")
    for words in (
        "`text`",
        "the card named, the guess, the number",
        "every seat is shown",
        "never judged",
        "200 characters",
        "no other kind of choice",
    ):
        assert words in contested, words


# @spec TOOL-083, PLAY-107
@NOT_BUILT
def test_choose_takes_answer_text() -> None:
    arguments = {"game_id": "g1", "choice_id": "x1", "text": "Lightning Bolt"}
    assert isinstance(shape(DEFINITIONS["choose"].parameters, arguments), Shaped)
