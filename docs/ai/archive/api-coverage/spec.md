---
feature: api-coverage
status: complete
created: 2026-02-28
updated: 2026-02-28
iteration: 1
---

## Overview

Add the remaining YNAB API endpoints to reach full coverage: single-resource GETs (get_account, get_category, get_payee, get_transaction), budget settings, and user info. Also update the charter to remove endpoints that don't exist in the YNAB API (account create, payee update, transaction import).

## Requirements

- [x] `get_user` tool — returns user ID from GET /user
- [x] `get_budget_settings` tool — returns date format and currency format from GET /budgets/{id}/settings
- [x] `get_account` tool — returns single account with extra fields (on_budget, note, uncleared_balance, transfer_payee_id) from GET /budgets/{id}/accounts/{id}
- [x] `get_category` tool — returns single category detail from GET /budgets/{id}/categories/{id} (reuse existing CategoryResponse)
- [x] `get_payee` tool — returns single payee with transfer_account_id from GET /budgets/{id}/payees/{id}
- [x] `get_transaction` tool — returns single transaction from GET /budgets/{id}/transactions/{id} (reuse existing TransactionResponse)
- [x] Update charter — remove nonexistent endpoints from write operations table: account create, payee update, transaction import
- [x] Update charter — remove payee locations from read operations table (not implementing)

## Technical Design

### New models (models.py)
- `User` — `id: str`
- `UserResponse` — `{"user": User}`
- `BudgetSettings` — `date_format: DateFormat`, `currency_format: CurrencyFormat`
- `DateFormat` — `format: str` (e.g. "MM/DD/YYYY")
- `CurrencyFormat` — `iso_code: str`, `example_format: str`, `decimal_digits: int`, `decimal_separator: str`, `symbol_first: bool`, `group_separator: str`, `currency_symbol: str`, `display_symbol: bool`
- `BudgetSettingsResponse` — `{"settings": BudgetSettings}`
- `AccountDetail` — extends `Account` with `on_budget: bool`, `note: str | None`, `uncleared_balance: Decimal`, `transfer_payee_id: str | None`
- `AccountDetailResponse` — `{"account": AccountDetail}`
- `PayeeDetail` — extends `Payee` with `transfer_account_id: str | None`
- `PayeeDetailResponse` — `{"payee": PayeeDetail}`

### Client methods (client.py)
- `get_user()` — GET /user
- `get_budget_settings(budget_id)` — GET /budgets/{id}/settings
- `get_account(budget_id, account_id)` — GET /budgets/{id}/accounts/{id}
- `get_category(budget_id, category_id)` — GET /budgets/{id}/categories/{id}
- `get_payee(budget_id, payee_id)` — GET /budgets/{id}/payees/{id}
- `get_transaction(budget_id, transaction_id)` — GET /budgets/{id}/transactions/{id}
- Add `_validate_account_id()` and `_validate_payee_id()` helpers (reuse `_UUID_RE`)

### Server tools (server.py)
- `get_user(ctx)` — no params
- `get_budget_settings(ctx, budget_id?)` — formatted settings output
- `get_account(ctx, account_id, budget_id?)` — full account detail
- `get_category(ctx, category_id, budget_id?)` — full category detail with group info
- `get_payee(ctx, payee_id, budget_id?)` — payee detail
- `get_transaction(ctx, transaction_id, budget_id?)` — full transaction detail

### Patterns to follow
- Same error handling pattern: ValidationError → YNABError(0, "Unexpected response format")
- Same `_get_client(ctx)` + `budget_id or "last-used"` pattern
- UUID validation on all resource IDs
- Human-readable formatted output strings

## Acceptance Criteria

- [x] All 6 new tools register and return correctly formatted output
- [x] UUID validation on account_id, category_id, payee_id, transaction_id
- [x] Budget ID defaults to "last-used" where applicable
- [x] Tests cover success paths, validation errors, and API errors for each tool
- [x] mypy strict passes
- [x] ruff passes
- [x] Charter accurately reflects actual YNAB API surface

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
- [x] [iter 1] Single-resource GETs (get_account, get_category, get_payee, get_transaction) did not display deleted/closed status — fixed, now shows [DELETED]/[CLOSED] tags
- [x] [iter 1] Account/Payee model split drops fields from list responses (on_budget, transfer_account_id) — by design, list endpoints show summary fields only

### Security
<!-- appended by /dev-security, tagged [iter N] -->
- [x] [iter 1] No findings — all inputs UUID-validated, no injection surface, read-only endpoints, no token leakage

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added 6 single-resource GET tools (get_user, get_budget_settings, get_account, get_category, get_payee, get_transaction) with new models for detailed account/payee/settings responses. Updated charter to remove YNAB API endpoints that don't actually exist (account create, payee update, transaction import, payee locations). Single-resource GETs include [DELETED]/[CLOSED] tags when fetching stale resources by UUID.
