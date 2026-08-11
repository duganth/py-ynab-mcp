---
feature: transaction-transfer-payees
status: implementing
created: 2026-08-07
updated: 2026-08-07
iteration: 1
---

## Overview

Expose YNAB transaction `payee_id` fields through the MCP transaction tools so callers can create proper linked account transfers, including credit-card payments. YNAB requires the destination account's `transfer_payee_id`; internal transfer names cannot be supplied through `payee_name`.

## Requirements

- [x] Add optional `payee_id` support to `create_transaction` and validate it as a UUID.
- [x] Add optional `payee_id` support to every entry accepted by `create_transactions` and validate it as a UUID.
- [x] Add optional `payee_id` support to `update_transaction` and validate it as a UUID.
- [x] Reject requests that supply both `payee_id` and `payee_name` before calling YNAB.
- [x] Include `payee_id` in dry-run previews when supplied.
- [x] Preserve existing `payee_name` behavior and requests that omit both payee fields.

## Technical Design

Update the MCP-facing functions in `src/py_ynab_mcp/server.py`; the existing `TransactionWrite` and `TransactionUpdate` models and `YNABClient` serialization already support `payee_id`.

For single create and update, add `payee_id: str | None = None` beside `payee_name`. Validate non-null values with `_validate_uuid`, reject simultaneous ID and name inputs with a clear error, pass the ID into the existing Pydantic request model, and display it in dry-run output.

For bulk create, read and validate each entry's optional `payee_id`, reject entries containing both payee fields, and pass the ID into `TransactionWrite`. Keep the existing JSON interface and transaction batching behavior unchanged.

Add focused coverage in `tests/test_server.py` for successful transfer-payee propagation, dry-run output, invalid UUIDs, mutual exclusion, and unchanged name-based behavior. No client or model changes should be necessary.

## Acceptance Criteria

- [x] A caller can create a transaction using an account's `transfer_payee_id`, producing the API payload needed for a YNAB transfer.
- [x] Single and bulk transaction creation reject invalid or ambiguous payee input without making an API call.
- [x] Transaction updates can set a validated `payee_id`.
- [x] Existing transaction tests pass along with the new focused tests.
- [x] Ruff and strict mypy checks pass.

## Findings

### Implementation Blockers

### QA

### Security

### User Notes

## Pipeline Log

- [iter 1] implement: pending — awaiting implementation
- [iter 1] qa: pending — awaiting review
- [iter 1] security: pending — awaiting review
- [iter 1] implement: complete — added validated mutually exclusive payee_id support; 687 tests, Ruff, and mypy passed
- [iter 1] qa: complete — no findings; 687 tests, Ruff, mypy, and MCP schema inspection passed
- [iter 1] security: complete — no findings; UUID validation and write boundaries reviewed
