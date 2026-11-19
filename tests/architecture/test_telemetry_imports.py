"""The telemetry import rule: under `src/`, only the telemetry adapter and the composition root
import OpenTelemetry."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

PACKAGE = "mtg_goldfishing"
SRC = Path(__file__).resolve().parents[2] / "src"
ALLOWED = (f"{PACKAGE}.adapters.telemetry", f"{PACKAGE}.bootstrap")


def _module_name(path: Path, src: Path) -> str:
    parts = path.relative_to(src).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path: Path) -> Iterator[str]:
    """Every absolute module name a file's import statements name, at any depth."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.module


def _is_allowed(module: str) -> bool:
    return any(module == allowed or module.startswith(allowed + ".") for allowed in ALLOWED)


def _is_opentelemetry(name: str) -> bool:
    return name == "opentelemetry" or name.startswith("opentelemetry.")


def _violations(src: Path) -> list[str]:
    found = []
    for path in sorted((src / PACKAGE).rglob("*.py")):
        module = _module_name(path, src)
        if _is_allowed(module):
            continue
        found.extend(
            f"{module} imports {imported}"
            for imported in _imported_modules(path)
            if _is_opentelemetry(imported)
        )
    return found


def _a_package_with(src: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = src / PACKAGE / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return src


# @spec TEL-022, TEL-023
def test_only_the_telemetry_adapter_and_the_composition_root_import_opentelemetry() -> None:
    assert _violations(SRC) == []


# @spec TEL-023
def test_the_rule_catches_another_module_importing_opentelemetry(tmp_path: Path) -> None:
    src = _a_package_with(
        tmp_path,
        {
            "adapters/mcp/server.py": "from opentelemetry.sdk.metrics import MeterProvider\n",
            "application/service.py": "def later():\n    import opentelemetry\n",
        },
    )

    assert _violations(src) == [
        f"{PACKAGE}.adapters.mcp.server imports opentelemetry.sdk.metrics",
        f"{PACKAGE}.application.service imports opentelemetry",
    ]


# @spec TEL-022, TEL-023
def test_the_rule_lets_the_telemetry_adapter_and_the_composition_root_import_it(
    tmp_path: Path,
) -> None:
    src = _a_package_with(
        tmp_path,
        {
            "adapters/telemetry/__init__.py": "import opentelemetry.sdk.metrics\n",
            "adapters/telemetry/settings.py": "from opentelemetry.sdk.resources import Resource\n",
            "bootstrap.py": "from opentelemetry.sdk.metrics import MeterProvider\n",
        },
    )

    assert _violations(src) == []


# @spec TEL-023
def test_the_rule_does_not_mistake_a_module_named_like_opentelemetry(tmp_path: Path) -> None:
    src = _a_package_with(tmp_path, {"adapters/mcp/app.py": "import opentelemetry_lookalike\n"})

    assert _violations(src) == []
