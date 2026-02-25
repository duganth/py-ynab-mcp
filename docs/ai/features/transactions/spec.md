---
feature: transactions
status: implementing
created: 2026-02-25
updated: 2026-02-25
iteration: 1
---

## Overview

Add transaction write operations (create, update, delete — single and bulk) to the MCP server. This is the first write capability, so it also establishes the patterns for request body handling, dollar-to-milliunit conversion, and input validation that future write features will follow. Supporting read methods (categories, payees) are added to the client for name-to-ID resolution but not exposed as MCP tools.

## Requirements

- [x] Extend `_request()` to accept an optional JSON body for POST/PUT/DELETE
- [x] Add `dollars_to_milliunits()` conversion function (reverse of existing)
- [x] Add Pydantic models for transaction request/response shapes
- [x] Add client methods: `create_transaction`, `create_transactions` (bulk), `update_transaction`, `update_transactions` (bulk), `delete_transaction`
- [x] Add client read methods for lookups: `get_categories`, `get_payees`
- [x] Add MCP tools: `create_transaction`, `update_transaction`, `delete_transaction`
- [x] Validate all inputs: amounts (parseable as Decimal), dates (YYYY-MM-DD), IDs (UUID format)
- [x] Add `create_transactions` (bulk) MCP tool that batches multiple transactions in one API call
- [x] Track rate limit usage via YNAB response headers (`X-Rate-Limit`) in the client
- [x] Return rate limit warning in tool responses when approaching the 200/hr ceiling
- [x] Add `dry_run` parameter to all write MCP tools for safe testing
- [x] Tests for all new client methods, models, and MCP tools

## Technical Design

### 1. Client changes (`src/py_ynab_mcp/client.py`)

**Extend `_request()`** to accept a `json` parameter:

```python
async def _request(
    self, method: str, path: str, *, json: dict[str, object] | None = None
) -> dict[str, object]:
```

This passes through to `self._client.request(method, path, json=json)`. No other changes to error handling.

**New methods:**

```python
# Write
async def create_transaction(self, budget_id: str, transaction: TransactionWrite) -> Transaction
async def create_transactions(self, budget_id: str, transactions: list[TransactionWrite]) -> list[Transaction]
async def update_transaction(self, budget_id: str, transaction_id: str, transaction: TransactionWrite) -> Transaction
async def update_transactions(self, budget_id: str, transactions: list[TransactionUpdate]) -> list[Transaction]
async def delete_transaction(self, budget_id: str, transaction_id: str) -> None

# Supporting reads
async def get_categories(self, budget_id: str = "last-used") -> list[CategoryGroup]
async def get_payees(self, budget_id: str = "last-used") -> list[Payee]
```

**YNAB API endpoints:**
- `POST /budgets/{id}/transactions` — body: `{ "transaction": {...} }` or `{ "transactions": [...] }`
- `PUT /budgets/{id}/transactions/{id}` — body: `{ "transaction": {...} }`
- `PATCH /budgets/{id}/transactions` — body: `{ "transactions": [...] }` (bulk update)
- `DELETE /budgets/{id}/transactions/{id}`
- `GET /budgets/{id}/categories`
- `GET /budgets/{id}/payees`

All write methods validate `budget_id` with `_BUDGET_ID_RE` (existing pattern). Transaction IDs validated with UUID regex.

### 2. Model changes (`src/py_ynab_mcp/models.py`)

**New conversion function:**

```python
def dollars_to_milliunits(dollars: Decimal) -> int:
    """Convert dollar amount to YNAB milliunits. $10.00 = 10000."""
    return int(dollars * Decimal(1000))
```

**Request models** (what we send to YNAB):

```python
class TransactionWrite(BaseModel):
    """Fields for creating/updating a transaction."""
    account_id: str
    date: str  # YYYY-MM-DD
    amount: int  # milliunits (converted before construction)
    payee_id: str | None = None
    payee_name: str | None = None  # YNAB auto-creates payee
    category_id: str | None = None
    memo: str | None = None
    cleared: str | None = None  # "cleared", "uncleared", "reconciled"
    approved: bool | None = None
    flag_color: str | None = None
    import_id: str | None = None

class TransactionUpdate(BaseModel):
    """For bulk update — includes the transaction ID."""
    id: str
    account_id: str | None = None
    date: str | None = None
    amount: int | None = None
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    memo: str | None = None
    cleared: str | None = None
    approved: bool | None = None
    flag_color: str | None = None
```

**Response models** (what we get back):

```python
class Transaction(BaseModel):
    id: str
    account_id: str
    account_name: str
    date: str
    amount: Decimal  # field_validator converts milliunits
    payee_id: str | None
    payee_name: str | None
    category_id: str | None
    category_name: str | None
    memo: str | None
    cleared: str
    approved: bool
    deleted: bool

class TransactionResponse(BaseModel):
    transaction: Transaction

class TransactionsResponse(BaseModel):
    transactions: list[Transaction]

# Duplicate IDs returned by bulk create
class BulkCreateResponse(BaseModel):
    bulk: BulkResult
class BulkResult(BaseModel):
    transaction_ids: list[str]
    duplicate_import_ids: list[str]
```

**Supporting read models:**

```python
class Category(BaseModel):
    id: str
    name: str
    budgeted: Decimal  # milliunit conversion
    activity: Decimal
    balance: Decimal
    deleted: bool

class CategoryGroup(BaseModel):
    id: str
    name: str
    categories: list[Category]
    deleted: bool

class CategoriesResponse(BaseModel):
    category_groups: list[CategoryGroup]

class Payee(BaseModel):
    id: str
    name: str
    deleted: bool

class PayeesResponse(BaseModel):
    payees: list[Payee]
```

### 3. MCP tool changes (`src/py_ynab_mcp/server.py`)

Four new tools. All follow the existing pattern (create client, try/except/finally). Each checks `client.rate_limit_remaining` after the call and appends a warning if <= 20.

**`create_transaction`** — The main write tool. Accepts human-friendly inputs:
- `account_id: str` — account UUID
- `amount: str` — dollar amount as string (e.g. "-42.50" for an outflow)
- `date: str` — YYYY-MM-DD
- `payee_name: str | None` — payee (YNAB auto-creates if new)
- `category_id: str | None` — category UUID
- `memo: str | None`
- `budget_id: str | None` — defaults to "last-used"

Parses amount to Decimal, converts to milliunits, builds `TransactionWrite`, calls client. Returns formatted confirmation string.

**`update_transaction`** — Accepts `transaction_id` plus any fields to update. Only sends non-None fields. Returns updated transaction summary.

**`delete_transaction`** — Accepts `transaction_id` and `budget_id`. Returns confirmation.

**`create_transactions`** (bulk) — Accepts a JSON array of transactions. Each element has the same fields as `create_transaction`. Calls the bulk `POST /transactions` endpoint (one API call for N transactions). Returns summary of created transactions + any duplicate import IDs. This is the preferred tool when the AI needs to create multiple transactions — avoids burning rate limit.

Bulk update is available as a client method but not an MCP tool yet (less common use case).

### 4. Rate limit tracking (`src/py_ynab_mcp/client.py`)

YNAB allows 200 requests/hour per access token. The API returns rate limit info in response headers.

**Client-side tracking in `_request()`:**

After each successful or error response, read the rate limit headers:
```python
# YNAB returns these headers (exact names TBD — check actual responses)
# Common pattern: X-Rate-Limit, X-Rate-Limit-Remaining, etc.
self._rate_limit_remaining: int | None  # updated after each request
```

Store as instance state on `YNABClient`. Expose via a property:
```python
@property
def rate_limit_remaining(self) -> int | None:
    """Remaining API requests this period, or None if unknown."""
    return self._rate_limit_remaining
```

**Warning threshold:** When `rate_limit_remaining` is known and <= 20, append a warning line to the MCP tool response:

```
⚠️ Rate limit: {remaining}/200 requests remaining this hour.
```

This is appended by a helper in `server.py` that checks the client after each call — not baked into the client itself. The client just tracks; the server decides what to surface.

**Bulk endpoints are the primary defense:** Using `POST /transactions` with an array body means creating 50 transactions costs 1 request, not 50.

### 5. Dry-run mode

All write MCP tools accept an optional `dry_run: bool = False` parameter. When `True`:

1. **Full validation runs** — amount parsing, date format, UUID checks, milliunit conversion
2. **Request body is built** — the exact payload that would be sent to YNAB
3. **No API call is made** — skips the client method entirely
4. **Returns a preview** showing what would happen:

```
[DRY RUN] Would create transaction:
  Account: <account_id>
  Amount: -$42.50 (-42500 milliunits)
  Date: 2026-02-25
  Payee: Costco
  Category: <category_id>
  Memo: Groceries
```

This serves two testing scenarios:
- **UA (interactive)**: User tells Claude "create a transaction, dry run" — sees the preview, verifies it looks right, then runs for real.
- **QA (`/dev-qa`)**: Exercises the full tool pipeline (parsing, validation, conversion, request building) without needing a YNAB token or hitting the API.

Implementation: each tool checks `dry_run` after validation/conversion but before calling the client. The client is still instantiated (to verify the token exists) but no request is made. For dry-run, the "Configuration error" path still fires if no token is set — use `YNAB_ACCESS_TOKEN=dummy` for tokenless QA testing.

### 6. Input validation

All in the MCP tool layer (before hitting the client):
- **Amount**: Must parse as `Decimal`. Reject empty/non-numeric.
- **Date**: Must match `YYYY-MM-DD` regex.
- **IDs**: Must match UUID regex (reuse `_BUDGET_ID_RE` pattern, add `_UUID_RE`).
- Return user-friendly error strings on validation failure (not exceptions).

### 7. Files to modify

| File | Changes |
|---|---|
| `src/py_ynab_mcp/models.py` | Add `dollars_to_milliunits`, transaction/category/payee models |
| `src/py_ynab_mcp/client.py` | Extend `_request` with json + rate limit tracking, add write + read methods |
| `src/py_ynab_mcp/server.py` | Add 4 MCP tools with dry_run support, rate limit warning helper, validation helpers |
| `tests/test_models.py` | Test `dollars_to_milliunits`, new model validation |
| `tests/test_client.py` | Test all new client methods, rate limit tracking, error paths |
| `tests/test_server.py` | Test all new MCP tools, dry_run mode, validation, formatting |

## Acceptance Criteria

- [ ] `create_transaction` tool creates a transaction and returns confirmation with the transaction ID
- [ ] `update_transaction` tool updates specified fields and returns the updated summary
- [ ] `delete_transaction` tool deletes a transaction and returns confirmation
- [ ] Invalid amounts (empty, non-numeric, NaN) return clear error messages
- [ ] Invalid dates return clear error messages
- [ ] Invalid IDs return clear error messages
- [ ] Dollar-to-milliunit conversion is exact (no floating point drift)
- [ ] Client bulk methods (`create_transactions`, `update_transactions`) work correctly
- [ ] `get_categories` and `get_payees` client methods return filtered (non-deleted) results
- [ ] `create_transactions` (bulk) tool creates multiple transactions in a single API call
- [ ] Rate limit remaining is tracked from YNAB response headers after each request
- [ ] Tool responses include a warning when rate limit remaining <= 20
- [ ] `dry_run=True` validates inputs and returns a preview without making API calls
- [ ] `dry_run=True` works for all four write tools (create, create bulk, update, delete)
- [ ] All existing tests continue to pass
- [ ] `uv run pytest` passes, `uv run ruff check .` clean, `uv run mypy src/` clean

## Findings

### QA

**[iter 1]** All 15 acceptance criteria pass. 3 issues found and fixed:

- [x] `get_categories` was not filtering deleted categories within non-deleted groups — fixed, test added
- [x] Rate limit header parser assumed plain int, but YNAB uses `used/total` format (e.g. `"36/200"`) — fixed to parse both formats, tests updated
- [x] `update_transaction` client signature uses `TransactionUpdate` (partial model via bulk PATCH) instead of spec's `TransactionWrite` via PUT — implementation is better (supports partial updates), spec deviation is intentional
- Note: dry_run skips client instantiation entirely (no token check) — this is intentional, enables tokenless QA testing

### Security

**[iter 1]** 4 issues found:

- [x] `budget_id` was not validated at server layer — dry-run would accept path traversal payloads that fail on real calls. Fixed: added `_validate_budget_id()` to all 4 tools before dry-run check. **MEDIUM**
- [x] `cleared` field accepted arbitrary strings, passed straight to YNAB API. Fixed: added `_validate_cleared()` against allowed values. **LOW**
- [x] `get_categories` didn't filter deleted categories within groups (also caught by QA). **LOW**
- [x] Rate limit header parsing handled wrong format (also caught by QA). **LOW**
- Accepted: sub-milliunit truncation in `dollars_to_milliunits` (uses `int()` which truncates). YNAB amounts are milliunits so 3 decimal places covers all valid inputs. **LOW, accepted**
- Accepted: no upper bound on bulk array size. YNAB API has its own limits. **LOW, accepted**

### User Notes
<!-- appended by /dev-ua -->
