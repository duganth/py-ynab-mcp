---
feature: category-updates
status: complete
created: 2026-02-28
updated: 2026-02-28
iteration: 1
---

## Overview

Add MCP tools for updating YNAB categories: (1) set the budgeted amount for a category in a given month, and (2) update category metadata (name, note, hidden). These enable budget management conversations like "assign $500 to rent for March" and "rename Dining Out to Restaurants".

## Requirements

- [x] Add `update_category_budget` MCP tool — set the budgeted (assigned) amount for a category in a specific month
- [x] Add `update_category` MCP tool — update category metadata (name, note, hidden)
- [x] Add `CategoryBudgetWrite` model for the month budget request body (budgeted amount in milliunits)
- [x] Add `CategoryUpdate` model for the metadata request body (name, note, hidden — all optional)
- [x] Expand `Category` model response to include `note`, `hidden`, `category_group_id`
- [x] Add client methods: `update_category_budget()` and `update_category()`
- [x] Both tools support `dry_run` for previewing changes
- [x] Input validation: category_id (UUID), budget_id, month (YYYY-MM-DD), amount (Decimal)
- [x] Follow existing patterns (shared client, error handling, rate limit warnings)

## Technical Design

### YNAB API endpoints

**Update monthly budget:**
`PATCH /budgets/{budget_id}/months/{month}/categories/{category_id}`
- Request: `{"category": {"budgeted": <milliunits>}}`
- Only `budgeted` field is accepted; all others ignored
- Month format: `YYYY-MM-DD` (first of month, e.g. `2026-03-01`)

**Update category metadata:**
`PATCH /budgets/{budget_id}/categories/{category_id}`
- Request: `{"category": {"name": ..., "note": ..., "hidden": ...}}`
- All fields optional, only provided fields are updated

**Both return:** `SaveCategoryResponse` with full updated `Category` object

### Files to modify

- `src/py_ynab_mcp/models.py` — Add `CategoryBudgetWrite`, `CategoryUpdate` models; expand `Category` with `note`, `hidden`, `category_group_id`; add `CategoryResponse` wrapper
- `src/py_ynab_mcp/client.py` — Add `update_category_budget()` and `update_category()` methods
- `src/py_ynab_mcp/server.py` — Add `update_category_budget` and `update_category` tool functions
- `tests/test_server.py` — Add test classes for both tools
- `tests/test_client.py` — Add tests for both client methods
- `tests/test_models.py` — Add tests for new models

### Tool signatures

```python
@mcp.tool()
async def update_category_budget(
    ctx: ToolContext,
    category_id: str,
    month: str,
    amount: str,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Set the budgeted (assigned) amount for a category in a specific month.

    Args:
        category_id: Category UUID.
        month: Month to update (YYYY-MM-DD, first of month).
        amount: Dollar amount to assign (e.g. "500.00").
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """

@mcp.tool()
async def update_category(
    ctx: ToolContext,
    category_id: str,
    name: str | None = None,
    note: str | None = None,
    hidden: bool | None = None,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Update category metadata in YNAB.

    Only provide the fields you want to change.

    Args:
        category_id: Category UUID.
        name: New category name.
        note: New category note.
        hidden: Whether to hide the category.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """
```

### Output format

`update_category_budget`:
```
Updated budget for Groceries (Mar 2026): $500.00
```

`update_category`:
```
Updated category Groceries: name → "Restaurants", note → "Eating out"
```

## Acceptance Criteria

- [x] `update_category_budget` sets budgeted amount and returns confirmation with category name and formatted amount
- [x] `update_category` updates metadata fields and returns confirmation listing what changed
- [x] `update_category` returns error if no fields provided
- [x] Both tools validate all inputs (UUID, date, amount, budget_id)
- [x] Both tools support dry_run previews
- [x] Rate limit warnings shown when near threshold
- [x] All tests pass, mypy clean, ruff clean

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
[iter 1] No findings. All acceptance criteria met. Test coverage: both tools have validation tests (category_id, budget_id, date, amount), dry_run, rate limit, API error, unexpected error, and happy path with confirmation output. Models tested for field presence and exclude_none serialization.

### Security
<!-- appended by /dev-security, tagged [iter N] -->
[iter 1] No findings. All user inputs (category_id, budget_id, month, amount) validated against strict patterns before URL interpolation — no path injection possible. Write operations are reversible and support dry_run preview. Request bodies use exclude_none to send only explicit fields.

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added two category write tools: `update_category_budget` for assigning dollar amounts to categories for specific months, and `update_category` for updating category metadata (name, note, hidden). Expanded the `Category` model with `note`, `hidden`, and `category_group_id` fields. Both tools follow the existing write pattern with dry_run support, input validation, and rate limit warnings.
