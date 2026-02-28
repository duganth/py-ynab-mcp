---
feature: months
status: complete
created: 2026-02-28
updated: 2026-02-28
iteration: 1
---

## Overview

Add `list_months` and `get_month` MCP tools to expose YNAB budget month data. `list_months` returns a summary of all months (income, budgeted, activity, to-be-budgeted, age of money). `get_month` returns a single month's detail with per-category breakdowns. Together these power "how's my budget this month?" conversations.

## Requirements

- [x] Add `MonthSummary` Pydantic model with milliunit conversion for `income`, `budgeted`, `activity`, `to_be_budgeted` fields; `age_of_money` as `int | None`; `month` as `str`; `note` as `str | None`; `deleted` as `bool`
- [x] Add `MonthDetail` Pydantic model extending `MonthSummary` with `categories: list[Category]`
- [x] Add `MonthsResponse` and `MonthDetailResponse` wrapper models
- [x] Add `get_months(budget_id)` client method — `GET /budgets/{budget_id}/months`, returns `list[MonthSummary]`, filters deleted
- [x] Add `get_month(budget_id, month)` client method — `GET /budgets/{budget_id}/months/{month}`, returns `MonthDetail`
- [x] Add `list_months` MCP tool — optional `budget_id` param, displays each month with income/budgeted/activity/to-be-budgeted/age-of-money, formatted with `_format_month()` and `_format_dollars()`
- [x] Add `get_month` MCP tool — required `month` param (YYYY-MM-DD or "current"), optional `budget_id`, displays month summary + per-category breakdown (flat list, no grouping — API doesn't include group names)
- [x] Add tests for new models (milliunit conversion, optional fields)
- [x] Add tests for client methods (happy path, validation)
- [x] Add tests for both MCP tools (formatting, empty results, validation, error handling)

## Technical Design

### Models (`src/py_ynab_mcp/models.py`)

```python
class MonthSummary(BaseModel):
    month: str
    note: str | None
    income: Decimal
    budgeted: Decimal
    activity: Decimal
    to_be_budgeted: Decimal
    age_of_money: int | None
    deleted: bool

    @field_validator("income", "budgeted", "activity", "to_be_budgeted", mode="before")
    # milliunit conversion

class MonthDetail(MonthSummary):
    categories: list[Category]

class MonthsResponse(BaseModel):
    months: list[MonthSummary]

class MonthDetailResponse(BaseModel):
    month: MonthDetail
```

### Client (`src/py_ynab_mcp/client.py`)

- `get_months(budget_id)` — GET `/budgets/{budget_id}/months`, parse with `MonthsResponse`, filter deleted
- `get_month(budget_id, month)` — GET `/budgets/{budget_id}/months/{month}`, parse with `MonthDetailResponse`. The `month` param accepts YYYY-MM-DD or `"current"` (YNAB API supports both).

### Server (`src/py_ynab_mcp/server.py`)

- `list_months` tool: Format each month as a summary line with income/budgeted/activity/available/age-of-money. Reuse `_format_month()` and `_format_dollars()`.
- `get_month` tool: Show month headline summary, then categories grouped by category group (reuse `Category` model). Validate `month` param: must match YYYY-MM-DD or be `"current"`. Filter deleted categories from display.

### Validation

- `month` parameter on `get_month`: accept YYYY-MM-DD format or literal `"current"`. Add `_validate_month()` helper or extend `_validate_date()`.
- Budget ID validation via existing `_validate_budget_id()`.

## Acceptance Criteria

- [x] `list_months` returns formatted summary for all non-deleted months
- [x] `get_month` with a YYYY-MM-DD date returns month detail with category breakdown
- [x] `get_month` with `"current"` returns the current month
- [x] All money fields display as formatted dollars (via `_format_dollars`)
- [x] Month dates display as "Mon YYYY" (via `_format_month`)
- [x] Invalid month format returns a clear error message
- [x] `uv run pytest` passes, `uv run mypy src/` clean, `uv run ruff check .` clean

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
- [x] [iter 1] Fixed `get_month` docstring — said "grouped by category group" but implementation uses flat list (API doesn't return group names)

### Security
<!-- appended by /dev-security, tagged [iter N] -->
- [x] [iter 1] No findings — both tools are read-only, month param validated against regex or literal "current", no path injection risk

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added `list_months` and `get_month` MCP tools with supporting `MonthSummary`/`MonthDetail` models and client methods. Categories in `get_month` are displayed as a flat list rather than grouped — the YNAB API doesn't return group names in the month detail response, so grouping by opaque UUID would be unhelpful.
