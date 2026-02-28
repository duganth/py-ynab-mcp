---
feature: list-budgets
status: complete
created: 2026-02-28
updated: 2026-02-28
iteration: 1
---

## Overview

Add a `list_budgets` MCP tool that returns all budgets for the authenticated user. This lets Claude discover available budgets and their IDs, which is needed when someone has multiple budgets and wants to target a specific one (all other tools default to `last-used`).

## Requirements

- [x] Add `list_budgets` MCP tool that returns budget name, ID, date range, and last modified
- [x] Expand `BudgetSummary` model to include `last_modified_on`, `first_month`, `last_month`
- [x] No `budget_id` parameter — this endpoint lists all budgets for the token
- [x] Follow existing tool patterns (shared client via ctx, error handling, tests)

## Technical Design

### Files to modify

- `src/py_ynab_mcp/models.py` — Add `last_modified_on`, `first_month`, `last_month` fields to `BudgetSummary`
- `src/py_ynab_mcp/server.py` — Add `list_budgets` tool function
- `tests/test_server.py` — Add `TestListBudgets` test class
- `tests/test_models.py` — Add tests for expanded `BudgetSummary` fields

### Tool signature

```python
@mcp.tool()
async def list_budgets(ctx: ToolContext) -> str:
```

No parameters. Returns all budgets for the authenticated token.

### Output format

```
- **My Budget** (last modified: 2026-02-28)
  Jan 2024 – Feb 2026
  ID: `<uuid>`
```

### YNAB API

`GET /budgets` → `data.budgets[]` with fields: `id`, `name`, `last_modified_on`, `first_month`, `last_month`

### Existing patterns to follow

- Error handling: `try/except YNABError` + generic `except Exception` (see `list_accounts`)
- Client access: `_get_client(ctx)` from lifespan context
- Client method: `get_budgets()` already exists in `client.py`

## Acceptance Criteria

- [x] `list_budgets` returns formatted budget list with names, IDs, and date ranges
- [x] Works with single and multiple budgets
- [x] Returns friendly message when no budgets found
- [x] API errors surface clearly
- [x] All tests pass, mypy clean, ruff clean

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
[iter 1] No findings. Implementation matches spec, all acceptance criteria met. Test coverage includes happy path (single/multiple budgets), empty state, error handling, and output formatting.

### Security
<!-- appended by /dev-security, tagged [iter N] -->
[iter 1] No findings. Read-only tool with zero user input (no injection surface). No sensitive data exposed — only budget names, IDs, and date ranges. Token handling delegated to shared lifespan client.

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added `list_budgets` MCP tool that returns all budgets for the authenticated user with names, IDs, date ranges, and last modified dates. Expanded the `BudgetSummary` model to include the additional fields from the YNAB API. Also refactored all tools to use a shared `YNABClient` via FastMCP's lifespan context for connection pooling.
