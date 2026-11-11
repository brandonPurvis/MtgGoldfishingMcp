"""The real service process, started on a free port with a database in a given folder, and
stopped with everything it started. Shared by the end-to-end tests and the HTTP scenarios.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
START_TIMEOUT = 60.0
RECORDED_SERVICE = (sys.executable, "-m", "tests.e2e.recorded_service")
"""The real service with recorded card data in place of Scryfall."""


@dataclass(frozen=True)
class RunningService:
    url: str
    database: Path


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def _environment(port: int, database: Path) -> dict[str, str]:
    return {
        **os.environ,
        "MTG_GOLDFISHING_HOST": "127.0.0.1",
        "MTG_GOLDFISHING_PORT": str(port),
        "MTG_GOLDFISHING_DB": str(database),
    }


def _wait_until_healthy(base: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the service exited early with status {process.returncode}")
        try:
            if httpx.get(f"{base}/health", timeout=1.0).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.2)
    raise AssertionError("the service did not answer /health in time")


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Stop the process and anything it started (`uv run` starts the service as a child)."""
    if process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=30)


@contextmanager
def running_service(
    folder: Path, command: Sequence[str] = RECORDED_SERVICE
) -> Iterator[RunningService]:
    """The service started by `command` with its database in `folder`, until the block ends."""
    port = _free_port()
    database = folder / "games.sqlite3"
    process = subprocess.Popen(
        list(command),
        cwd=ROOT,
        env=_environment(port, database),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=sys.platform != "win32",
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_until_healthy(base, process)
        yield RunningService(f"{base}/mcp", database)
    finally:
        _stop(process)
