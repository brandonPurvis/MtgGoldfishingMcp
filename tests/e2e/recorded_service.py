"""The real service, served exactly as `mtg-goldfishing` serves it, but with card data from
the recorded Scryfall answers instead of the network.

    python -m tests.e2e.recorded_service

Run from the repository root. It reads the same settings from the environment as the
`mtg-goldfishing` command: SQLite, HTTP, the MCP adapter and every other adapter are the
production ones; only the card catalog differs, so the end-to-end check never reaches
Scryfall. It is a test entry point and is not part of the installed service.
"""

from __future__ import annotations

import os
import sys

from mtg_goldfishing.adapters.memory import InMemoryCardCatalog
from mtg_goldfishing.bootstrap import SettingsProblem, serve, settings_from
from tests.support.card_data import recorded_cards


def main() -> int:
    settings = settings_from(os.environ)
    if isinstance(settings, SettingsProblem):
        print(settings.message, file=sys.stderr)
        return 2
    return serve(settings, catalog=InMemoryCardCatalog(recorded_cards()))


if __name__ == "__main__":
    sys.exit(main())
