# Contributing to py-ynab-mcp

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/duges/py-ynab-mcp.git
cd py-ynab-mcp
uv sync
```

## Running Checks

Before submitting a PR, make sure everything passes:

```bash
uv run ruff check .       # linting
uv run ruff format --check .  # formatting
uv run mypy src/          # type checking
uv run pytest             # tests
```

## Code Style

- Format with `ruff format`, lint with `ruff check`
- Type annotations on all public functions (mypy strict mode)
- Use `Decimal` for money — never floats
- YNAB amounts are in milliunits (e.g. `$10.00` = `10000`)

## Adding a New MCP Tool

1. Add the YNAB API client method in the appropriate module
2. Add the MCP tool registration in `server.py`
3. Add tests for both the API call and the tool
4. Update README if it exposes new functionality

## Pull Requests

- Keep PRs focused — one feature or fix per PR
- Include tests for new functionality
- Update docs if behavior changes
- PR title should describe what changed, not how

## Issues

Found a bug or have an idea? Open an issue. Include:
- What you expected vs. what happened
- Steps to reproduce (for bugs)
- YNAB API endpoint involved (if relevant)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
