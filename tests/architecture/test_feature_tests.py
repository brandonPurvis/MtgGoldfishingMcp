"""The fast test suites stay fast: no database file, no network, no server. The HTTP
scenarios, which start the real service, run in CI and not before commits."""

import ast
import configparser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HTTP_FEATURES = ROOT / "features" / "http"
OUTSIDE_WORLD = (
    "mtg_goldfishing.adapters.sqlite",
    "mtg_goldfishing.adapters.scryfall.catalog",
    "mtg_goldfishing.adapters.mcp.app",
    "mtg_goldfishing.bootstrap",
    "sqlite3",
    "httpx",
    "uvicorn",
    "socket",
    "subprocess",
)


def _imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def _reaching_out(folder: Path) -> list[str]:
    """Imports of the outside world in `folder`, leaving out the HTTP scenarios."""
    return [
        f"{path.relative_to(ROOT)} imports {imported}"
        for path in sorted(folder.rglob("*.py"))
        if HTTP_FEATURES not in path.parents
        for imported in _imports(path)
        if imported.startswith(OUTSIDE_WORLD)
    ]


def _run_steps(workflow: Path) -> list[str]:
    """The commands of a workflow's `run:` steps."""
    return [
        line.split("run:", 1)[1].strip()
        for line in workflow.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- run:") or line.strip().startswith("run:")
    ]


# @spec APP-024
def test_the_feature_tests_reach_no_database_network_or_server() -> None:
    assert _reaching_out(ROOT / "features") == []


# @spec APP-024
def test_the_domain_tests_reach_no_database_network_or_server() -> None:
    assert _reaching_out(ROOT / "tests" / "domain") == []


# @spec APP-025
def test_the_feature_tests_drive_the_tool_functions_over_in_memory_adapters() -> None:
    imported = _imports(ROOT / "features" / "environment.py")

    assert "mtg_goldfishing.adapters.mcp.tools" in imported
    assert "tests.support.service" in imported


# @spec APP-077
def test_the_http_scenarios_start_the_real_service_and_give_each_seat_its_own_client() -> None:
    imported = _imports(HTTP_FEATURES / "environment.py") + _imports(HTTP_FEATURES / "players.py")

    assert "tests.e2e.running_service" in imported
    assert "tests.e2e.seat_clients" in imported


# @spec APP-080
def test_every_http_feature_is_tagged_http() -> None:
    untagged = [
        path.name
        for path in sorted(HTTP_FEATURES.glob("*.feature"))
        if not path.read_text(encoding="utf-8").lstrip().startswith("@http")
    ]

    assert untagged == []


# @spec APP-080
def test_the_default_behave_run_leaves_the_http_scenarios_out() -> None:
    config = configparser.ConfigParser()
    config.read(ROOT / "behave.ini", encoding="utf-8")

    assert "not @http" in config["behave"]["default_tags"]


# @spec APP-080
def test_the_checks_before_a_commit_do_not_run_behave() -> None:
    hooks = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "behave" not in hooks


# @spec APP-080
@pytest.mark.xfail(strict=True, reason="M5: not built")
def test_ci_runs_the_http_scenarios() -> None:
    commands = _run_steps(ROOT / ".github" / "workflows" / "ci.yml")

    assert "uv run behave features/http --tags=@http" in commands, commands
