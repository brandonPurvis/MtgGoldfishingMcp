"""Claude Code PostToolUse hook: format-check and lint the edited Python file, then type-check
the checkout it belongs to. Tests are left to the pre-commit hook and CI, so red tests during
test-first work do not block edits.

Reads the hook payload from stdin. Does nothing for non-Python files. The checks run in the
git checkout that holds the edited file, so an edit in a linked worktree is type-checked
against that worktree's code, not the main checkout's. A file outside any checkout falls back
to the project this hook belongs to. On any failure it writes the tool output to stderr and
exits 2, which Claude Code feeds back to Claude so it can fix the problem.
"""

import json
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def checkout_of(file_path: Path, fallback: Path) -> Path:
    """The root of the git checkout (main or linked worktree) holding the file."""
    ok, output = run(["git", "rev-parse", "--show-toplevel"], file_path.parent)
    if ok and output:
        root = Path(output)
        if (root / "pyproject.toml").is_file():
            return root
    return fallback


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or payload.get("tool_response", {}).get("filePath")
    if not file_path or not file_path.endswith(".py"):
        return 0

    edited = Path(file_path).resolve()
    if not edited.parent.is_dir():
        return 0
    root = checkout_of(edited, fallback=Path(__file__).resolve().parents[2])
    uv = ["uv", "run", "--project", str(root)]
    checks = [
        ("format (ruff)", [*uv, "ruff", "format", "--check", "--diff", str(edited)]),
        ("lint (ruff)", [*uv, "ruff", "check", str(edited)]),
        ("type check (mypy)", [*uv, "mypy"]),
    ]

    failures = []
    for name, command in checks:
        ok, output = run(command, root)
        if not ok:
            failures.append(f"{name} failed in {root}:\n{output}")

    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
