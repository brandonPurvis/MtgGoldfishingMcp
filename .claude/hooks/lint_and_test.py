"""Claude Code PostToolUse hook: format-check and lint the edited Python file, type-check
the project, then run the unit tests.

Reads the hook payload from stdin. Does nothing for non-Python files. On any
failure it writes the tool output to stderr and exits 2, which Claude Code feeds
back to Claude so it can fix the problem.
"""

import json
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or payload.get("tool_response", {}).get("filePath")
    if not file_path or not file_path.endswith(".py"):
        return 0

    project_dir = Path(__file__).resolve().parents[2]
    checks = [
        ("format (ruff)", ["uv", "run", "ruff", "format", "--check", "--diff", file_path]),
        ("lint (ruff)", ["uv", "run", "ruff", "check", file_path]),
        ("type check (mypy)", ["uv", "run", "mypy"]),
        ("unit tests (pytest)", ["uv", "run", "pytest", "-m", "not e2e"]),
    ]

    failures = []
    for name, command in checks:
        ok, output = run(command, project_dir)
        if not ok:
            failures.append(f"{name} failed:\n{output}")

    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
