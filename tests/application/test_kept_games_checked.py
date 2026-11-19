"""When an application test or an in-process feature scenario ends, every game the in-memory
game repository keeps is checked against its private copy, and a difference fails the test.

Each check is seen from outside: a test, or a scenario, that changes a kept game is run in
its own process, which must report a failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).with_name("kept_game_changed_case.py")

not_yet_checked = pytest.mark.xfail(
    strict=True, reason="no test checks the games the in-memory repository keeps when it ends yet"
)

FEATURE = """\
Feature: A scenario that changes a kept game
  Scenario: The scenario changes a game the agent's service keeps
    Given a game the agent's service keeps
    When the scenario changes that game
"""

STEPS = """\
from behave import given, when

from tests.support.builders import a_game


@given("a game the agent's service keeps")
def a_kept_game(context):
    context.agent.harness.holding(a_game().build())


@when("the scenario changes that game")
def changing_it(context):
    context.agent.harness.game().tested.life = 1
"""

ENVIRONMENT = f"""\
import sys

sys.path.insert(0, {str(ROOT)!r})

from features.environment import *  # the in-process features' own hooks
"""


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


# @spec APP-102, APP-098, APP-103
@not_yet_checked
def test_an_application_test_that_changes_a_kept_game_fails_when_it_ends() -> None:
    finished = run("pytest", str(CASE), "-p", "no:cacheprovider")

    assert finished.returncode == pytest.ExitCode.TESTS_FAILED, finished.stdout


# @spec APP-102, APP-098, APP-103
@not_yet_checked
def test_an_in_process_feature_scenario_that_changes_a_kept_game_fails(tmp_path: Path) -> None:
    features = tmp_path / "features"
    (features / "steps").mkdir(parents=True)
    (features / "kept_game.feature").write_text(FEATURE, encoding="utf-8")
    (features / "steps" / "kept_game_steps.py").write_text(STEPS, encoding="utf-8")
    (features / "environment.py").write_text(ENVIRONMENT, encoding="utf-8")

    finished = run("behave", str(features))

    assert finished.returncode != 0, finished.stdout
