# MTG Goldfishing

An MCP service that holds the state of agent-played Magic: The Gathering Commander goldfish games. The agent makes every decision and says what each card does; the service owns the shuffle, the bookkeeping, the checks and the records.

- Why and what: [`docs/high-level-design.md`](docs/high-level-design.md)
- How each part works: [`docs/intent/`](docs/intent/)
- Vocabulary: [`GLOSSARY.md`](GLOSSARY.md)
- Working on the code: [`AGENTS.md`](AGENTS.md)

## Development

```
uv sync                         # install everything
uv run pre-commit install       # once: lint, type check and unit tests run before every commit
uv run pytest                   # unit, application, contract and architecture tests
uv run behave                   # feature tests
uv run ruff check && uv run ruff format --check && uv run mypy
```

A commit is refused if formatting, linting, type checking or the unit tests fail.
