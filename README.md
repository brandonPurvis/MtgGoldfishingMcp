# MTG Goldfishing

An MCP service that holds the state of agent-played Magic: The Gathering Commander goldfish games. The agent makes every decision and says what each card does; the service owns the shuffle, the bookkeeping, the checks and the records.

- Why and what: [`docs/high-level-design.md`](docs/high-level-design.md)
- How each part works: [`docs/intent/`](docs/intent/)
- Vocabulary: [`GLOSSARY.md`](GLOSSARY.md)
- Working on the code: [`AGENTS.md`](AGENTS.md)

## Running the service

```
uv sync
uv run mtg-goldfishing          # serves MCP at http://127.0.0.1:8000/mcp; GET /health checks it is up
```

| Setting              | Environment variable   | Default                        |
|----------------------|------------------------|--------------------------------|
| Address to listen on | `MTG_GOLDFISHING_HOST` | `127.0.0.1`                    |
| Port                 | `MTG_GOLDFISHING_PORT` | `8000`                         |
| Database file        | `MTG_GOLDFISHING_DB`   | `data/mtg-goldfishing.sqlite3` |

Card data is fetched from Scryfall on first use and cached in the database.

## Connecting an agent

The repository's `.mcp.json` connects Claude Code to the running service as the MCP server `goldfishing`. The server's instructions and tool descriptions are enough for any MCP client to play a game. For Claude Code, the subagent `goldfish-player` (`.claude/agents/goldfish-player.md`) plays one game given a deck id or deck list, and optionally a seed and turn limit, and returns the game id, seed and verdict.

## Development

```
uv sync                         # install everything
uv run pre-commit install       # once: lint, type check and unit tests run before every commit
uv run pytest                   # unit, application, contract, architecture and end-to-end tests
uv run pytest -m "not e2e"      # the same without starting the real service
uv run behave                   # feature tests
uv run ruff check && uv run ruff format --check && uv run mypy
```

A commit is refused if formatting, linting, type checking or the unit tests fail.

The end-to-end tests (`tests/e2e`, marked `e2e`) start the real process on a free port with a database under a temporary directory. One starts `uv run mtg-goldfishing`; the other plays a short game over HTTP against `python -m tests.e2e.recorded_service`, which serves exactly as `mtg-goldfishing` does but takes card data from the recorded Scryfall answers in `tests/support`, so no test reaches the network.
