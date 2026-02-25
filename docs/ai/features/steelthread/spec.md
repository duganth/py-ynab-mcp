---
feature: steelthread
project: py-ynab-mcp
status: pending
created: 2026-02-24
updated: 2026-02-24
---

## Summary

Implement a minimal working MCP server with one tool: `list_accounts`. This proves the full stack — auth, YNAB API client, Pydantic models, and MCP tool registration — works end-to-end.

## Requirements

### Functional
1. MCP server starts and registers with MCP clients
2. `list_accounts` tool accepts an optional `budget_id` parameter
3. If no `budget_id` provided, use the default budget (first budget or `last-used`)
4. Returns account name, type, balance, and cleared balance for each account
5. Balances displayed in dollars (converted from milliunits)
6. Auth via `YNAB_ACCESS_TOKEN` environment variable
7. Clear error if token is missing or invalid

### Non-functional
1. Server starts in under 2 seconds
2. Handles YNAB API errors gracefully (rate limit, auth failure, network)
3. No financial data in logs or error traces

## Implementation Notes

### Files to create/modify
- `src/py_ynab_mcp/server.py` — FastMCP server setup, `list_accounts` tool
- `src/py_ynab_mcp/client.py` — YNAB API client (httpx), `get_accounts()` method
- `src/py_ynab_mcp/models.py` — Pydantic models: `Account`, `AccountsResponse`
- `tests/test_server.py` — tool integration tests
- `tests/test_client.py` — API client tests (mocked)

### API endpoints used
- `GET /budgets` — to resolve default budget
- `GET /budgets/{budget_id}/accounts` — to list accounts

### Key decisions
- Use `Decimal` for balance conversion from milliunits
- httpx async client for API calls
- Pydantic models match YNAB API response shapes

## Acceptance Criteria

- [ ] `uv run py-ynab-mcp` starts the MCP server
- [ ] Connecting from Claude Code with a valid token shows available tools
- [ ] `list_accounts` returns real account data from YNAB
- [ ] Balances are correct (milliunit conversion verified)
- [ ] Missing/invalid token produces a clear error message
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` passes
- [ ] `uv run mypy src/` passes

## Test Plan

- Unit tests: API client with mocked httpx responses
- Unit tests: milliunit to dollar conversion
- Unit tests: missing token error handling
- Integration: manual test with real YNAB token against live API
