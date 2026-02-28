# Changelog

## [Unreleased]

### Added
- `update_payee` tool — rename payees via YNAB PATCH endpoint with dry-run support

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

### Added
- Single-resource GET tools — `get_user`, `get_budget_settings`, `get_account`, `get_category`, `get_payee`, `get_transaction` with detailed output and deleted/closed status indicators
- Scheduled transaction CRUD — `list_scheduled_transactions`, `get_scheduled_transaction`, `create_scheduled_transaction`, `update_scheduled_transaction`, `delete_scheduled_transaction` with frequency validation and dry-run support
- `list_months` MCP tool — budget month summaries with income, budgeted, activity, available, and age of money
- `get_month` MCP tool — single month detail with per-category breakdown, supports "current" shorthand
- `update_category_budget` MCP tool — set budgeted amount for a category in a specific month
- `update_category` MCP tool — update category metadata (name, note, hidden) with dry-run support
- `list_budgets` MCP tool — lists all budgets with names, IDs, date ranges, and last modified dates
- Shared YNAB client via FastMCP lifespan for connection pooling across tool calls
- `list_transactions` MCP tool — query transactions with required `since_date` and optional account/category/payee/type filters, routes to correct YNAB endpoint
- Query parameter support in YNAB client `_request()` method
- Transaction CRUD tools — `create_transaction`, `create_transactions` (bulk), `update_transaction`, `delete_transaction` with dry-run support and input validation
- `list_categories` MCP tool — lists category groups with names, balances, and IDs
- `list_payees` MCP tool — lists payees with names and IDs
- Rate limit tracking from YNAB `X-Rate-Limit` headers with warning when approaching 200/hr ceiling
- Account UUIDs now shown in `list_accounts` output for use with write tools
- PyPI publish workflow — tag-triggered pipeline with TestPyPI validation, Trusted Publishers OIDC, and auto GitHub Releases
- `list_accounts` MCP tool — lists YNAB accounts with balances (name, type, balance, cleared balance)
- YNAB API client with async httpx, auth via `YNAB_ACCESS_TOKEN` env var
- Pydantic models for accounts and budgets with milliunit-to-Decimal conversion
- Graceful error handling for auth failures, rate limits, network errors, and malformed responses
- Input validation on `budget_id` parameter (UUID format or `last-used`)
- GitHub Actions CI workflow — ruff, mypy strict, pytest across Python 3.11/3.12/3.13

### Changed
- Migrated dev dependencies from `[project.optional-dependencies]` to `[dependency-groups]` (PEP 735)
