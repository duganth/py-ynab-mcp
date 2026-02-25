# Changelog

## [Unreleased]

### Added
- `list_accounts` MCP tool — lists YNAB accounts with balances (name, type, balance, cleared balance)
- YNAB API client with async httpx, auth via `YNAB_ACCESS_TOKEN` env var
- Pydantic models for accounts and budgets with milliunit-to-Decimal conversion
- Graceful error handling for auth failures, rate limits, network errors, and malformed responses
- Input validation on `budget_id` parameter (UUID format or `last-used`)
