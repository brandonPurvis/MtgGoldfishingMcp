"""The fast test suites stay fast: no database file, no network, no server."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    return [
        f"{path.relative_to(ROOT)} imports {imported}"
        for path in sorted(folder.rglob("*.py"))
        for imported in _imports(path)
        if imported.startswith(OUTSIDE_WORLD)
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
