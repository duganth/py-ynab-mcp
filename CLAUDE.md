# py-ynab-mcp

Python MCP server for YNAB (You Need A Budget).

## Quick Reference
- **Run**: `uv run py-ynab-mcp`
- **Test**: `uv run pytest`
- **Lint**: `uv run ruff check .`
- **Type check**: `uv run mypy src/`
- **Build**: `uv build`

## Project Charter
See `docs/ai/charter.md` for architecture, roadmap, and development context.

## Conventions
- Use `Decimal` for all money values, never floats
- YNAB amounts are milliunits ($10.00 = 10000)
- Auth via `YNAB_ACCESS_TOKEN` env var
- 4-space indentation
- mypy strict, ruff for linting
