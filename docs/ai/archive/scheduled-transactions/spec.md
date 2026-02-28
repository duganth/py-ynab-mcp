---
feature: scheduled-transactions
status: complete
created: 2026-02-28
updated: 2026-02-28
iteration: 1
---

## Overview

Add full CRUD for YNAB scheduled transactions: list, get, create, update, delete. Scheduled transactions represent recurring bills and future-dated transactions. This powers "what bills are coming up?" conversations and lets Claude help manage recurring expenses.

## Requirements

### Models (`src/py_ynab_mcp/models.py`)

- [x] Add `ScheduledSubTransaction` model with `id`, `scheduled_transaction_id`, `amount` (milliunit conversion), `memo: str | None`, `payee_id: str | None`, `category_id: str | None`, `transfer_account_id: str | None`, `deleted: bool`
- [x] Add `ScheduledTransaction` model with `id`, `date_first`, `date_next`, `frequency`, `amount` (milliunit conversion), `memo: str | None`, `flag_color: str | None`, `account_id`, `account_name`, `payee_id: str | None`, `payee_name: str | None`, `category_id: str | None`, `category_name: str | None`, `transfer_account_id: str | None`, `subtransactions: list[ScheduledSubTransaction]`, `deleted: bool`
- [x] Add `ScheduledTransactionWrite` model with `account_id`, `date` (first occurrence), `amount` (milliunits int), `frequency`, optional `payee_id`, `payee_name`, `category_id`, `memo`, `flag_color`
- [x] Add `ScheduledTransactionUpdate` model — partial update with `id` required, all other fields optional
- [x] Add `ScheduledTransactionsResponse` and `ScheduledTransactionResponse` wrapper models

### Client (`src/py_ynab_mcp/client.py`)

- [x] Add `get_scheduled_transactions(budget_id)` — `GET /budgets/{id}/scheduled_transactions`, filter deleted
- [x] Add `get_scheduled_transaction(budget_id, scheduled_transaction_id)` — `GET /budgets/{id}/scheduled_transactions/{id}`
- [x] Add `create_scheduled_transaction(budget_id, write)` — `POST /budgets/{id}/scheduled_transactions`
- [x] Add `update_scheduled_transaction(budget_id, scheduled_transaction_id, update)` — `PUT /budgets/{id}/scheduled_transactions/{id}`
- [x] Add `delete_scheduled_transaction(budget_id, scheduled_transaction_id)` — `DELETE /budgets/{id}/scheduled_transactions/{id}`

### Server (`src/py_ynab_mcp/server.py`)

- [x] Add `list_scheduled_transactions` tool — optional `budget_id`, displays each with frequency/amount/next date/payee/category, sorted by `date_next`
- [x] Add `get_scheduled_transaction` tool — required `scheduled_transaction_id`, optional `budget_id`, shows full detail including subtransactions
- [x] Add `create_scheduled_transaction` tool — required `account_id`, `amount` (dollars), `date`, `frequency`; optional `payee_name`, `category_id`, `memo`, `flag_color`, `budget_id`, `dry_run`
- [x] Add `update_scheduled_transaction` tool — required `scheduled_transaction_id`; optional fields to change, `budget_id`, `dry_run`
- [x] Add `delete_scheduled_transaction` tool — required `scheduled_transaction_id`, optional `budget_id`, `dry_run`

### Tests

- [x] Model tests — milliunit conversion, optional fields, subtransactions, write/update model dumps
- [x] Client tests — happy path for all 5 methods, validation, deleted filtering
- [x] Server tests — formatting, validation, dry-run, empty results, error handling for all 5 tools

## Technical Design

### Frequency enum

YNAB frequency values: `never`, `daily`, `weekly`, `everyOtherWeek`, `twiceAMonth`, `every4Weeks`, `monthly`, `everyOtherMonth`, `every3Months`, `every4Months`, `twiceAYear`, `yearly`, `everyOtherYear`. Validate in server layer with `_FREQUENCY_VALUES` set, same pattern as `_CLEARED_VALUES`.

Add `_format_frequency()` helper to convert camelCase to human-readable (e.g. `everyOtherWeek` → `Every other week`, `monthly` → `Monthly`).

### Write model

Follows the same pattern as `TransactionWrite` — amount in milliunits (int), server tool accepts dollar strings and converts via `_parse_amount()`. Frequency is required on create.

### Update model

`ScheduledTransactionUpdate` has `id` required, everything else optional. Unlike regular transactions which use PATCH with bulk, scheduled transactions use `PUT` on a single resource. Only send fields that are non-None.

### Endpoints

| Operation | Method | Path |
|-----------|--------|------|
| List | GET | `/budgets/{id}/scheduled_transactions` |
| Get | GET | `/budgets/{id}/scheduled_transactions/{st_id}` |
| Create | POST | `/budgets/{id}/scheduled_transactions` |
| Update | PUT | `/budgets/{id}/scheduled_transactions/{st_id}` |
| Delete | DELETE | `/budgets/{id}/scheduled_transactions/{st_id}` |

### Files modified

- `src/py_ynab_mcp/models.py` — new models
- `src/py_ynab_mcp/client.py` — 5 new methods + imports
- `src/py_ynab_mcp/server.py` — 5 new tools + frequency validation/formatting
- `tests/test_models.py` — model tests
- `tests/test_client.py` — client tests
- `tests/test_server.py` — server tool tests

## Acceptance Criteria

- [x] `list_scheduled_transactions` shows all non-deleted scheduled transactions with frequency, next date, amount, payee
- [x] `get_scheduled_transaction` shows full detail including subtransactions
- [x] `create_scheduled_transaction` creates with required fields and validates frequency
- [x] `update_scheduled_transaction` updates only provided fields
- [x] `delete_scheduled_transaction` deletes by ID
- [x] All tools support `dry_run` where applicable
- [x] Invalid frequency value returns clear error message
- [x] `uv run pytest` passes, `uv run mypy src/` clean, `uv run ruff check .` clean

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
- [x] [iter 1] No findings — all models, client methods, and tools follow established patterns; frequency validation covers all 13 YNAB values; subtransaction deleted filtering correct

### Security
<!-- appended by /dev-security, tagged [iter N] -->
- [x] [iter 1] No findings — all write tools have dry_run, all inputs validated (UUIDs, amounts, dates, frequency whitelist), no path injection risk

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added full CRUD for scheduled transactions: 5 new MCP tools (list, get, create, update, delete), 7 new Pydantic models, and 5 new client methods. Frequency values are validated against the 13 YNAB enum values and displayed with human-readable labels. The update model omits `id` since scheduled transactions use PUT on a single resource (ID in path) rather than bulk PATCH.
