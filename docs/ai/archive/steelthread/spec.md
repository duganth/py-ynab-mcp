---
feature: steelthread
project: py-ynab-mcp
status: complete
iteration: 2
created: 2026-02-24
updated: 2026-02-25
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

- [x] `uv run py-ynab-mcp` starts the MCP server
- [x] Connecting from Claude Code with a valid token shows available tools
- [x] `list_accounts` returns real account data from YNAB
- [x] Balances are correct (milliunit conversion verified)
- [x] Missing/invalid token produces a clear error message
- [x] `uv run pytest` passes
- [x] `uv run ruff check .` passes
- [x] `uv run mypy src/` passes

## Test Plan

- Unit tests: API client with mocked httpx responses
- Unit tests: milliunit to dollar conversion
- Unit tests: missing token error handling
- Integration: manual test with real YNAB token against live API

## Findings

### QA (iteration 1)

- [x] [bug] `server.py` — Unhandled exceptions propagate to MCP framework. Fixed: added `except Exception` catch-all.
- [x] [bug] `client.py:56` — `response.json()` on non-JSON error bodies. Fixed: wrapped in try/except.
- [x] [gap] `client.py:46-49` — Only TimeoutException/ConnectError caught. Fixed: catch `httpx.HTTPError` base class.
- [x] [edge-case] `server.py:35` — Negative balances format. Fixed: `_format_dollars()` helper.
- [x] [edge-case] `test_client.py` — No test for ConnectError path. Fixed: added test.
- [x] [edge-case] `test_client.py` — No test for error.detail JSON body. Fixed: added test.

### Security (iteration 1)

- [x] [medium] `client.py:70` — budget_id path traversal. Fixed: UUID regex validation.
- [x] [medium] `server.py:21` + `client.py:30` — Token exposure via tracebacks. Fixed: catch-all prevents propagation.
- [x] [low] `client.py:56` — Error detail passed through verbatim. Accepted: by design per charter.
- [x] [info] `client.py:44-49` — Unhandled httpx exceptions. Fixed: catch `httpx.HTTPError` base class.
- [x] [medium] `client.py` — Token in httpx headers visible in repr. Fixed: `from None` suppresses chaining.
- [x] [info] `pyproject.toml:20-24` — Dependencies unpinned; add lower-bound pins. Deferred to future work.

### QA (iteration 2)

- [x] [low] `client.py` — Success path `response.json()` not wrapped. Fixed: wrapped in try/except.
- [x] [nit] `client.py` — `raise YNABError(...)` now uses `from None` to suppress chaining.
- [x] [nit] `server.py` — Catch-all has no logging. Deferred to future work.

### Security (iteration 2)

- [x] [low] `client.py` — Exception chaining suppressed with `from None`.
- [x] [low] `client.py` — Pydantic `ValidationError` now caught and converted to `YNABError`.

## Outcome

Implemented a working MCP server with a `list_accounts` tool that proves the full stack: YNAB API auth, async httpx client, Pydantic models with Decimal milliunit conversion, and FastMCP tool registration. Two iterations of QA and security review hardened error handling, input validation (budget_id UUID check), and exception safety (no token or financial data leakage via tracebacks). 54 tests passing, mypy strict clean, ruff clean.
