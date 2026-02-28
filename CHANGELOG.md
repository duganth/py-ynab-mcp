# Changelog

## [Unreleased]

### Added
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
