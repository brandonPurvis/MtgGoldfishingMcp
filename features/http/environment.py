"""The HTTP scenarios: the real service process, on SQLite with a temporary database and
recorded card data, played over HTTP with a separate MCP client for each seat.

They start a process and several clients, so like the end-to-end tests they are run by CI and
not before commits; every feature here is tagged @http, which the default run leaves out:

    uv run behave features/http --tags=@http
"""

# @spec APP-077

from __future__ import annotations

import io
import shutil
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.http.players import Table  # noqa: E402  (needs the repository root on the path)
from tests.e2e.running_service import running_service  # noqa: E402


def before_all(context: Any) -> None:
    # Steps quote response text (`·`, `→`); a console on a legacy code page cannot print it.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    context.resources = ExitStack()
    folder = Path(tempfile.mkdtemp(prefix="mtg-goldfishing-http-"))
    context.resources.callback(shutil.rmtree, folder, ignore_errors=True)
    context.service = context.resources.enter_context(running_service(folder))


def before_scenario(context: Any, scenario: Any) -> None:
    context.players = Table(context.service.url)


def after_scenario(context: Any, scenario: Any) -> None:
    context.players.close()


def after_all(context: Any) -> None:
    context.resources.close()
