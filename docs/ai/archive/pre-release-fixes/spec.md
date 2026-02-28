---
feature: pre-release-fixes
status: complete
created: 2026-02-28
updated: 2026-02-28
iteration: 1
---

## Overview

Fix bugs and correctness issues found during independent code reviews (Claude agent + Codex) before cutting the first release. Covers a runtime-breaking response model bug, input validation gaps, and documentation inaccuracies.

## Requirements

### Critical — runtime bugs

- [x] Fix bulk create response model — YNAB API returns `data.transaction_ids` and `data.duplicate_import_ids` directly, NOT wrapped in `data.bulk`. Current model causes `ValidationError` on every `create_transactions` call. Also make `duplicate_import_ids` optional (API may omit it).
  - Files: `models.py` (BulkResult, BulkCreateResponse), `client.py` (create_transactions), tests.

- [x] Fix `dollars_to_milliunits` silent truncation — `int(dollars * 1000)` truncates amounts with >3 decimal places (e.g. `1.2345` → `1234` instead of error). Should reject or round. Both reviewers flagged this.
  - Files: `models.py` (dollars_to_milliunits), `server.py` (_parse_amount), tests.

### Important — validation & correctness

- [x] Fix date validation to reject impossible calendar dates — current check allows Feb 31, Apr 31, etc. Use `datetime.date()` for proper validation.
  - Files: `server.py` (_validate_date), tests.

- [x] Accept `"default"` as valid budget_id — YNAB API accepts it alongside `"last-used"` and UUIDs. Our regex rejects it.
  - Files: `server.py` (_BUDGET_ID_RE), `client.py` (_BUDGET_ID_RE), tests.

- [x] Add `update_payee` tool — PATCH /budgets/{id}/payees/{id} exists (accepts `name` field). We incorrectly claimed it doesn't exist. Add client method, server tool, and update charter/README.
  - Files: `models.py`, `client.py`, `server.py`, `charter.md`, `README.md`, tests.

- [x] Fix `list_budgets` missing rate limit warning — only tool that doesn't call `_rate_limit_warning()`. Inconsistent.
  - Files: `server.py` (list_budgets).

- [x] Fix bare `except Exception` to include exception type — all ~20 tools return "An unexpected error occurred." with zero context. Add `type(e).__name__` at minimum.
  - Files: `server.py` (all tool functions).

- [x] Fix `cleared` field in `create_transactions` passing raw non-string — validated with `str()` coercion but stored as raw JSON value. Should store the coerced string.
  - Files: `server.py` (create_transactions).

### Documentation

- [x] Fix GitHub URL mismatch — `pyproject.toml` says `duganth/py-ynab-mcp`, README says `duges/py-ynab-mcp`. Verify which is correct and align.
  - Files: `pyproject.toml`, `README.md`.

- [x] Update charter and README to reflect payee update exists — remove "payee update" from "not available" lists, add to write operations.
  - Files: `charter.md`, `README.md`.

## Technical Design

### Bulk response model fix (models.py)
Replace `BulkResult` + `BulkCreateResponse` with a flat model:
```python
class BulkCreateResponse(BaseModel):
    transaction_ids: list[str]
    duplicate_import_ids: list[str] = []
```
Update `client.py` `create_transactions()` to use `parsed.transaction_ids` / `parsed.duplicate_import_ids` directly instead of `parsed.bulk.*`.

### dollars_to_milliunits fix (models.py)
Check that the result has no fractional part after multiplication:
```python
result = dollars * Decimal(1000)
if result != result.to_integral_value():
    raise ValueError("Amount has more than 3 decimal places")
return int(result)
```
Update `_parse_amount` in server.py to catch this ValueError and return a user-friendly error.

### Date validation fix (server.py)
Replace month/day range check with:
```python
import datetime
datetime.date(int(year), int(month), int(day))
```
This catches Feb 31, leap year issues, etc.

### budget_id regex fix
Change `_BUDGET_ID_RE` in both files to: `^[0-9a-f-]{36}$|^last-used$|^default$`

### update_payee tool
- Model: `PayeeUpdate` with `name: str` (only field YNAB accepts)
- Client: `update_payee(budget_id, payee_id, update)` → PATCH with `{"payee": {"name": ...}}`
- Server: `update_payee(ctx, payee_id, name, budget_id?, dry_run?)` tool

### Exception context
Change all bare `except Exception:` to `except Exception as e:` and return `f"Unexpected error: {type(e).__name__}"`.

## Acceptance Criteria

- [x] `create_transactions` works against the real YNAB response shape (flat, no bulk wrapper)
- [x] Amounts with >3 decimal places are rejected with a clear error
- [x] `2026-02-31` is rejected as an invalid date
- [x] `budget_id="default"` is accepted
- [x] `update_payee` tool works with dry_run support
- [x] All tools include exception type in unexpected error messages
- [x] `list_budgets` includes rate limit warning
- [x] GitHub URLs are consistent across pyproject.toml and README
- [x] Charter and README accurately list payee update as available
- [x] All existing tests still pass
- [x] New tests cover all fixes
- [x] mypy strict passes
- [x] ruff passes

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
- [x] [iter 1] CONTRIBUTING.md line 8 still had old GitHub URL (`duges` → `duganth`) — fixed
- [x] [iter 1] `_validate_budget_id` error message didn't mention `"default"` as valid option — fixed

### Security
<!-- appended by /dev-security, tagged [iter N] -->
- [iter 1] No findings. All input validation, error handling, decimal precision, and path interpolation reviewed as secure.

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Fixed 10 bugs and correctness issues identified by independent Claude and Codex reviews. Critical fixes: bulk create response model (was broken at runtime) and monetary precision loss in `dollars_to_milliunits`. Added `update_payee` tool after discovering YNAB's PATCH endpoint exists. Neutralized subjective competitor claims in README. 600 tests passing, all clean on ruff and mypy.
