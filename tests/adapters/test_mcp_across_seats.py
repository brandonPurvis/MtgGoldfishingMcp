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
def test_attack_says_a_blocked_attacker_s_damage_entry_is_dealt_in_full() -> None:
    targets = parameter("attack", "targets")
    assert targets is not None
    assert targets.meaning.startswith("Contested games: ")
    description = DEFINITIONS["attack"].description
    assert "blocked attacker" in description
    assert "dealt in full" in description
    assert "no reduction for blockers" in description


# @spec TOOL-071
def test_attack_says_it_may_stop_undeclared_where_another_seat_has_a_reminder() -> None:
    description = DEFINITIONS["attack"].description
    contested = description[description.index("Contested games:") :]
    for words in ("reminder", "nothing is declared or tapped", "send attack again"):
        assert words in contested, words
