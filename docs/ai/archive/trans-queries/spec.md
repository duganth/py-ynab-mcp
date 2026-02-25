---
feature: trans-queries
status: complete
created: 2026-02-25
updated: 2026-02-25
iteration: 1
---

## Overview

Add a `list_transactions` MCP tool that queries transactions with filtering by account, category, payee, and date range. Uses a single tool with optional filter parameters that routes to the appropriate YNAB endpoint under the hood. `since_date` is required to prevent unbounded result sets. Delta sync is deferred to a future feature.

## Requirements

- [x] Extend `_request()` to accept optional query string parameters (`params`)
- [x] Add client method `get_transactions()` with optional filters that routes to the correct YNAB endpoint
- [x] Add `list_transactions` MCP tool with required `since_date` and optional filters
- [x] Support filtering by `account_id`, `category_id`, `payee_id` (mutually exclusive — each uses a different YNAB endpoint)
- [x] Support filtering by `type` (`uncategorized` or `unapproved`)
- [x] Handle `HybridTransactionsResponse` (returned by category/payee/month endpoints) alongside `TransactionsResponse`
- [x] Format output as a readable transaction list with totals
- [x] Validate all inputs at the server layer (date, UUIDs, type enum, filter exclusivity)
- [x] Tests for client method, MCP tool, validation, and formatting

## Technical Design

### 1. Client changes (`src/py_ynab_mcp/client.py`)

**Extend `_request()` to accept query params:**

```python
async def _request(
    self, method: str, path: str, *,
    json: dict[str, object] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, object]:
```

Pass through to `self._client.request(method, path, json=json, params=params)`.

**New method:**

```python
async def get_transactions(
    self,
    budget_id: str = "last-used",
    *,
    since_date: str,
    account_id: str | None = None,
    category_id: str | None = None,
    payee_id: str | None = None,
    type: str | None = None,
) -> list[Transaction]:
```

Route to the correct YNAB endpoint based on which filter is provided:

| Filter | Endpoint |
|---|---|
| none | `GET /budgets/{id}/transactions` |
| `account_id` | `GET /budgets/{id}/accounts/{aid}/transactions` |
| `category_id` | `GET /budgets/{id}/categories/{cid}/transactions` |
| `payee_id` | `GET /budgets/{id}/payees/{pid}/transactions` |

All endpoints accept `since_date` and `type` as query params. The client validates that at most one of `account_id`, `category_id`, `payee_id` is provided (raise `ValueError` if multiple).

**Response handling:** The category, payee, and month endpoints return `HybridTransactionsResponse` which has the same `transactions` field shape as `TransactionsResponse`. We can use the same `TransactionsResponse` model for parsing — the hybrid fields (like `account_name` on sub-transactions) are already covered by our `Transaction` model. Verify this works; if the response shape differs, add a `HybridTransaction` model.

Filter deleted transactions out of the result (consistent with `get_categories`, `get_payees`).

### 2. Model changes (`src/py_ynab_mcp/models.py`)

Likely no new models needed — `Transaction` and `TransactionsResponse` should handle all endpoints. If hybrid responses have extra fields, we can just ignore them (Pydantic's default behavior with `model_validate`).

### 3. MCP tool (`src/py_ynab_mcp/server.py`)

**`list_transactions`** — Single tool with required date filter:

```python
@mcp.tool()
async def list_transactions(
    since_date: str,
    account_id: str | None = None,
    category_id: str | None = None,
    payee_id: str | None = None,
    type: str | None = None,
    budget_id: str | None = None,
) -> str:
```

**Validation:**
- `since_date`: required, must match `YYYY-MM-DD` regex
- `account_id`, `category_id`, `payee_id`: optional UUIDs, mutually exclusive
- `type`: optional, must be `"uncategorized"` or `"unapproved"` if provided
- `budget_id`: optional, validated with `_validate_budget_id()`
- If multiple filter IDs are provided, return a clear error

**Output format:**

```
Transactions since 2026-02-01 (42 found):

1. 2026-02-25: **-$42.50** to Costco (Groceries) — "Weekly shop"
   ID: `txn-uuid`
2. 2026-02-24: **$2,500.00** (Paycheck)
   ID: `txn-uuid`
...

Total: -$1,234.56 (42 transactions)
```

Each transaction uses the existing `_format_transaction()` helper with date prepended and ID on the next line. Append a summary line with total amount and count.

### 4. Validation helpers (`src/py_ynab_mcp/server.py`)

Add:
- `_TRANSACTION_TYPE_VALUES = {"uncategorized", "unapproved"}`
- `_validate_transaction_type(type: str) -> str | None` — returns error or None

Reuse existing: `_validate_date`, `_validate_uuid`, `_validate_budget_id`.

### 5. Files to modify

| File | Changes |
|---|---|
| `src/py_ynab_mcp/client.py` | Extend `_request` with `params`, add `get_transactions()` |
| `src/py_ynab_mcp/server.py` | Add `list_transactions` tool, type validation helper |
| `tests/test_client.py` | Test `get_transactions()` routing, filtering, params, error paths |
| `tests/test_server.py` | Test `list_transactions` tool, validation, formatting, filter exclusivity |

## Acceptance Criteria

- [x] `list_transactions` returns transactions filtered by date range
- [x] Filtering by `account_id` routes to the account-specific YNAB endpoint
- [x] Filtering by `category_id` routes to the category-specific YNAB endpoint
- [x] Filtering by `payee_id` routes to the payee-specific YNAB endpoint
- [x] Providing multiple filter IDs returns a clear error
- [x] `type` filter (`uncategorized`/`unapproved`) works alongside other filters
- [x] Invalid `since_date` returns a clear error
- [x] Missing `since_date` returns a clear error (it's required)
- [x] Invalid filter IDs return clear error messages
- [x] Invalid `type` returns a clear error
- [x] Deleted transactions are filtered out of results
- [x] Output includes transaction count and total amount
- [x] Each transaction in output includes its ID for reference by write tools
- [x] `_request()` correctly passes query params to httpx
- [x] All existing tests continue to pass
- [x] `uv run pytest` passes, `uv run ruff check .` clean, `uv run mypy src/` clean

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->

**[iter 1]** All 16 acceptance criteria pass. No issues found. 291 tests pass, 60 new tests added (22 client + 38 server).

### Security
<!-- appended by /dev-security, tagged [iter N] -->

**[iter 1]** No issues found. All inputs validated at server layer before client call. Filter IDs validated as UUIDs at both server and client layers. `type` validated against allowlist. Query params properly URL-encoded by httpx.

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added `list_transactions` MCP tool for querying YNAB transactions with required date filtering and optional account/category/payee filters. The client routes to the correct YNAB endpoint based on which filter is provided, and the `_request()` method was extended with query parameter support. Clean pipeline run — 0 QA findings, 0 security findings, 1 iteration.
