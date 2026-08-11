---
feature: category-targets
status: implementing
created: 2026-08-04
updated: 2026-08-05
iteration: 3
---

## Overview

Bring category writes up to date with the current YNAB API by supporting category creation and target configuration. This replaces the stale assumption that categories cannot be created, exposes target details for verification, and stops advertising `hidden` as writable when YNAB treats it as read-only.

## Requirements

- [x] Add a `create_category` MCP tool accepting a category group, name, optional note, and optional target configuration.
- [x] Extend `update_category` to set `category_group_id`, `goal_target`, `goal_target_date`, `goal_needs_whole_amount`, and `goal_frequency` through user-friendly parameters.
- [x] Support target frequencies `monthly`, `weekly`, and `yearly`; require a target amount with frequency and reject frequency combined with a target date.
- [x] Convert target dollar strings to milliunits with `Decimal`, rejecting non-positive and over-precision values before API calls.
- [x] Expose target amount, date, type, and whole-amount behavior in category response models and `get_category` output.
- [x] Show category-group IDs in `list_categories` so callers can create or move categories without another lookup.
- [x] Remove writable `hidden` from `CategoryUpdate` and the `update_category` tool because it is not part of the current YNAB save-category contract.
- [x] Update project documentation that incorrectly says categories cannot be created.
- [x] Preserve dry-run previews, input validation, rate-limit warnings, and existing error handling patterns.
- [x] Add an explicit `clear_category_target` tool that removes a category target by sending JSON nulls for nullable target fields without touching category metadata or assigned money.
- [x] Keep the documented `target_frequency` write parameter for monthly, weekly, and yearly recurrence without advertising unsupported arbitrary or non-repeating cadence writes.
- [x] Expose target underfunding and cadence response metadata so MCP reads can explain the same target state shown in the YNAB UI.

## Technical Design

The implementation follows the existing model → async client → FastMCP tool layering.

- `src/py_ynab_mcp/models.py`
  - Add optional target response fields to `Category`, converting target money fields from milliunits to `Decimal`.
  - Add `CategoryWrite` for category creation.
  - Expand `CategoryUpdate` with the current save-category fields and remove `hidden`.
  - Model `goal_frequency` as `Literal["monthly", "weekly", "yearly"]`.
- `src/py_ynab_mcp/client.py`
  - Add `create_category()` using `POST /budgets/{budget_id}/categories`; YNAB documents `/plans`, while the `/budgets` alias remains supported for backward compatibility and matches the rest of this client.
  - Continue using `PATCH /budgets/{budget_id}/categories/{category_id}` for updates with only non-`None` fields serialized.
  - Clear targets with a dedicated PATCH that deliberately includes JSON nulls for all nullable target fields.
- `src/py_ynab_mcp/server.py`
  - Add `create_category` with `dry_run`.
  - Extend `update_category` with `category_group_id`, `target_amount`, `target_date`, `target_needs_whole_amount`, and `target_frequency`.
  - Add `clear_category_target` with `dry_run`.
  - Share target validation/building logic between create and update.
  - Display target metadata in `get_category` and `get_month`, and group IDs in `list_categories`.
- `tests/test_models.py`, `tests/test_client.py`, `tests/test_server.py`
  - Cover request serialization, milliunit conversion, endpoint paths, validation combinations, dry runs, successful writes, target readback, and error paths.
- `README.md`, `docs/ai/charter.md`, `CHANGELOG.md`
  - Document the new coverage and remove stale API limitations.

The API fields map as follows:

| MCP argument | YNAB field |
|---|---|
| `target_amount` | `goal_target` (milliunits) |
| `target_date` | `goal_target_date` |
| `target_needs_whole_amount` | `goal_needs_whole_amount` |
| `target_frequency` | `goal_frequency` |

Target configuration is additive/update-only through `create_category` and `update_category`. Target deletion uses the separate `clear_category_target` operation because optional MCP parameters cannot distinguish omission from JSON `null`.

## Acceptance Criteria

- [x] `create_category` sends the documented request body and returns the created category name and ID.
- [x] `update_category` can create or replace a category target using amount/date or amount/frequency.
- [x] Invalid UUIDs, dates, amounts, and target field combinations fail locally without an API call.
- [x] Dry runs display category and target changes without an API call.
- [x] `get_category` displays configured target information with formatted dollars.
- [x] The MCP schema no longer claims categories can be hidden through `update_category`.
- [x] Unit tests, ruff, and strict mypy pass.
- [x] Clearing a target preserves the category and its budgeted/available money while removing the target configuration.
- [x] Supported recurring cadence writes are validated, while unsupported arbitrary cadence writes are not exposed.
- [x] Category/month output makes an underfunded target visible without requiring a UI screenshot.

## Findings

### Implementation Blockers

### QA

- [x] [iter 1] `_build_target_configuration` rejects standalone `target_date` and `target_needs_whole_amount` updates unless `target_amount` is also supplied, even though the spec and YNAB save-category contract only require an amount with `target_frequency`. This prevents changing an existing target's date or rollover behavior independently. Restrict the amount dependency to frequency, or use operation-specific validation if creation needs stricter rules, and add update tests for standalone date and whole-amount writes.
- [x] [iter 3] `create_category` accepts `target_date` or `target_needs_whole_amount` without `target_amount`, even though a new category has no existing target and YNAB only creates one when `goal_target` is supplied. Add create-specific validation requiring `target_amount` whenever either dependent target field is provided, while continuing to allow those standalone fields in `update_category`, and add no-API-call tests for both invalid create combinations.

### Security

### User Notes

- [x] [iter 3] A target created with only `goal_target` defaults to a monthly NEED target. This made the one-time Pihl's Computer bucket request another $1,500 in September. `goal_needs_whole_amount=false` does not solve the future-month display because YNAB intentionally does not apply rollover to a future month's refill target until that month begins. The MCP needs target clearing and accurate underfunding readback.
- [x] [iter 3] Live readback confirmed `target_frequency="yearly"` created cadence `Yearly (13)`, and the official SaveCategory schema documents `goal_frequency` for monthly, weekly, and yearly recurrence. Restore that supported write surface; arbitrary or non-repeating cadence remains read-only.

## Pipeline Log

- [iter 1] implement: complete — Implemented category creation, target configuration/readback, validation, group IDs, and documentation updates; 640 tests, ruff, and mypy pass.
- [iter 1] qa: complete — 1 actionable finding: standalone target date and rollover updates were over-constrained.
- [iter 1] security: complete — No security findings; validation, URL construction, JSON encoding, dry runs, and token handling are sound.
- [iter 2] implement: complete — Allowed standalone target date and whole-amount updates while preserving the target-frequency amount requirement; 644 tests, ruff, and mypy pass.
- [iter 2] qa: complete — Iteration 1 finding verified fixed; no new findings; 644 tests, ruff, and mypy pass.
- [iter 2] security: complete — No security findings or regressions in validation, request construction, write safety, or token handling.
- [iter 3] implement: complete — Added explicit target clearing, removed unsupported cadence writes, exposed underfunding/cadence readback, and passed 653 tests plus ruff and strict mypy.
- [iter 3] qa: complete — 1 actionable finding: create-category target-dependent fields need amount validation; 653 tests, ruff, and strict mypy pass.
- [iter 3] security: complete — No findings; fixed endpoint construction, identifier validation, explicit target-only null fields, and token handling are sound.
- [iter 3] implement correction: complete — Restored documented monthly/weekly/yearly `goal_frequency`, added create-only dependent-field validation, retained target clearing/readback, and passed 663 tests plus ruff and strict mypy.
- [iter 3] qa correction: complete — Frequency restoration and create validation verified; 663 tests, ruff, and strict mypy pass. Proposed `goal_frequency: null` clear finding rejected because the official SaveCategory schema does not make that field nullable, `goal_target: null` removes the target, and live readback after clearing Pihl's monthly target showed no remaining cadence or underfunding.
- [iter 3] security correction: complete — No findings; frequency allowlisting, create validation, identifier validation, explicit target clearing, and token handling are sound.
