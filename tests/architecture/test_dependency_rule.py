"""The dependency rule: adapters -> application -> domain, and never the other way."""

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

PACKAGE = "mtg_goldfishing"
SRC = Path(__file__).resolve().parents[2] / "src" / PACKAGE


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC.parent).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path) -> Iterator[str]:
    """Every module a file imports, with relative imports resolved to absolute names."""
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                yield ".".join([*base, node.module] if node.module else base)
            elif node.module:
                yield node.module


def _files(ring: str) -> list[Path]:
    return sorted((SRC / ring).rglob("*.py"))


def _is_stdlib(name: str) -> bool:
    return name.split(".", maxsplit=1)[0] in sys.stdlib_module_names


def _violations(ring: str, allowed_prefixes: tuple[str, ...]) -> list[str]:
    found = []
    for path in _files(ring):
        for imported in _imports(path):
            if _is_stdlib(imported) or imported.startswith(allowed_prefixes):
                continue
            found.append(f"{_module_name(path)} imports {imported}")
    return found


# @spec APP-001, APP-004
def test_domain_imports_only_the_standard_library_and_itself() -> None:
    assert _violations("domain", (f"{PACKAGE}.domain",)) == []


# @spec APP-002, APP-004
def test_application_imports_only_the_standard_library_the_domain_and_itself() -> None:
    allowed = (f"{PACKAGE}.domain", f"{PACKAGE}.application")
    assert _violations("application", allowed) == []


# @spec APP-003, APP-004
def test_only_the_composition_root_imports_adapters() -> None:
    adapters = f"{PACKAGE}.adapters"
    found = []
    for path in sorted(SRC.rglob("*.py")):
        module = _module_name(path)
        if module == f"{PACKAGE}.bootstrap":
            continue
        for imported in _imports(path):
            if not imported.startswith(adapters + "."):
                continue
            own_adapter = ".".join(module.split(".")[:3])
            if module.startswith(adapters + ".") and imported.startswith(own_adapter):
                continue
            found.append(f"{module} imports {imported}")
    assert found == []
