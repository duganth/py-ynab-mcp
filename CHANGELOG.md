# Changelog

## [Unreleased]

## [0.3.0] - 2026-09-02

### Added
- Split transaction support — `create_transaction` and `update_transaction` take `subtransactions_json`, recording one card charge against several categories instead of forcing two hand-entered rows that no longer match the statement line. Legs are validated to sum to the parent amount before the call, and `get_transaction`/`list_transactions` now display existing splits
- `create_category` tool and category target configuration support via `create_category` and `update_category`
- Category target metadata in `get_category` output and category-group IDs in `list_categories`
- `clear_category_target` tool for removing targets without changing assigned money

### Fixed
- Transaction IDs — `get_transaction`, `update_transaction`, and `delete_transaction` rejected the `<uuid>_<YYYY-MM-DD>` IDs that YNAB returns for auto-entered scheduled occurrences, so rows `list_transactions` printed could not be read back or deleted
- `list_categories` no longer presents "Inflow: Ready to Assign" as a spendable balance — that figure is cumulative net income, not money left to assign, and reading it as the latter overstates available funds by the whole month's assignments. Other category balances are now labelled "available"
- `list_months` and `get_month` label `to_be_budgeted` as "Ready to Assign" instead of "Available", which collided with per-category available amounts in the same output
- `list_transactions` rows now flag `uncleared`/`reconciled`, `unapproved`, and `scheduled` status — previously an auto-entered scheduled transaction was indistinguishable from a hand-entered one, making it easy to duplicate a charge when reconciling against a bank statement
- Category reads now expose target underfunding and cadence metadata; recurring target frequency writes are validated against YNAB's documented monthly, weekly, and yearly values

## [0.2.1] - 2026-08-03

### Fixed
- Pin `mcp[cli]>=1.2,<2` — mcp 2.0.0 removed `mcp.server.fastmcp`, so fresh installs crashed on import with `ModuleNotFoundError`

## [0.2.0] - 2026-02-28

### Added
- Single-resource GET tools — `get_user`, `get_budget_settings`, `get_account`, `get_category`, `get_payee`, `get_transaction` with detailed output and deleted/closed status indicators
- Scheduled transaction CRUD — `list_scheduled_transactions`, `get_scheduled_transaction`, `create_scheduled_transaction`, `update_scheduled_transaction`, `delete_scheduled_transaction` with frequency validation and dry-run support
- `list_months` MCP tool — budget month summaries with income, budgeted, activity, available, and age of money
- `get_month` MCP tool — single month detail with per-category breakdown, supports "current" shorthand
- `update_category_budget` MCP tool — set budgeted amount for a category in a specific month
- `update_category` MCP tool — update category metadata with dry-run support
- `list_budgets` MCP tool — lists all budgets with names, IDs, date ranges, and last modified dates
- Shared YNAB client via FastMCP lifespan for connection pooling across tool calls
- `list_transactions` MCP tool — query transactions with required `since_date` and optional account/category/payee/type filters, routes to correct YNAB endpoint
- Query parameter support in YNAB client `_request()` method
- Transaction CRUD tools — `create_transaction`, `create_transactions` (bulk), `update_transaction`, `delete_transaction` with dry-run support and input validation
- `list_categories` MCP tool — lists category groups with names, balances, and IDs
- `list_payees` MCP tool — lists payees with names and IDs
- `update_payee` tool — rename payees via YNAB PATCH endpoint with dry-run support
- Rate limit tracking from YNAB `X-Rate-Limit` headers with warning when approaching 200/hr ceiling
- Account UUIDs now shown in `list_accounts` output for use with write tools

### Fixed
- Bulk create response model — was expecting a `bulk` wrapper that YNAB doesn't send, causing `ValidationError` on every `create_transactions` call
- `dollars_to_milliunits` now rejects amounts with >3 decimal places instead of silently truncating
- Date validation rejects impossible calendar dates (Feb 31, Apr 31, etc.) using `datetime.date()`
- Accept `"default"` as valid `budget_id` alongside `"last-used"` and UUIDs
- `list_budgets` now includes rate limit warning like all other tools
- Exception handlers include exception type name for debuggability
- `cleared` field in bulk `create_transactions` stores coerced string instead of raw JSON value
- GitHub URLs consistent across README, CONTRIBUTING, and pyproject.toml
- README competitor table now states facts only, no subjective judgments

## [0.1.0] - 2026-02-25

### Added
- `list_accounts` MCP tool — lists YNAB accounts with balances (name, type, balance, cleared balance)
- YNAB API client with async httpx, auth via `YNAB_ACCESS_TOKEN` env var
- Pydantic models for accounts and budgets with milliunit-to-Decimal conversion
- Graceful error handling for auth failures, rate limits, network errors, and malformed responses
- Input validation on `budget_id` parameter (UUID format or `last-used`)
- GitHub Actions CI workflow — ruff, mypy strict, pytest across Python 3.11/3.12/3.13
- PyPI publish workflow — tag-triggered pipeline with TestPyPI validation, Trusted Publishers OIDC, and auto GitHub Releases

### Changed
- Migrated dev dependencies from `[project.optional-dependencies]` to `[dependency-groups]` (PEP 735)
