---
project: py-ynab-mcp
created: 2026-02-24
updated: 2026-02-24
---

## Overview

A Python MCP server that exposes YNAB (You Need A Budget) data to AI assistants. The goal is to enable financial conversations with Claude — asking about spending, tracking goals, managing budgets — and to power automation like transaction categorization via local LLMs.

### Why build another one?

Several YNAB MCP servers exist but none are suitable:
- **chrisguidry/you-need-an-mcp** — best code quality, but has no OSS license
- **calebl/ynab-mcp-server** (TS) — full CRUD but inconsistent code quality
- **mattweg/ynab-mcp** (JS) — known bugs, dormant since mid-2025

We need a properly licensed, well-tested Python implementation with full API coverage.

### End goals

1. **Financial conversations** — ask Claude about budgets, spending patterns, goal progress
2. **Goal tracking** — Claude helps plan and monitor progress toward financial goals
3. **Automation** — powers `/ynab-sync` skill for privacy-first transaction categorization (Ollama handles categorization locally, financial data stays off cloud APIs)

## Architecture

### Stack
- **Language**: Python 3.11+
- **MCP SDK**: FastMCP (`mcp[cli]`)
- **HTTP client**: httpx
- **Models**: Pydantic
- **Money**: Decimal (never floats) — YNAB uses milliunits ($10.00 = 10000)
- **Package management**: uv + hatch
- **Distribution**: PyPI, installed via `uvx py-ynab-mcp`

### Components
```
py-ynab-mcp/
├── src/py_ynab_mcp/
│   ├── server.py      # MCP tool definitions
│   ├── client.py      # YNAB API client (httpx)
│   └── models.py      # Pydantic models for API responses
└── tests/
```

### Data flow
```
MCP Client (Claude) → MCP Server → YNAB API v1 (https://api.ynab.com/v1)
                                  ← JSON responses → Pydantic models → MCP tool results
```

### Auth
- YNAB Personal Access Token via `YNAB_ACCESS_TOKEN` env var
- Full read/write access (no granular scoping in YNAB API)

## YNAB API Coverage

### Read operations
| Resource | Endpoints | Delta sync |
|---|---|---|
| User | get | no |
| Budgets | list, get, settings | yes |
| Accounts | list, get | yes |
| Categories | list, get, get by month | yes |
| Payees | list, get | yes |
| Payee Locations | list, get, get by payee | no |
| Months | list, get | yes |
| Transactions | list (by account/category/payee/month), get | yes |
| Scheduled Transactions | list, get | yes |

### Write operations
| Resource | Operations |
|---|---|
| Accounts | create |
| Categories | update, update monthly budget |
| Payees | update |
| Transactions | create (single/bulk), update (single/bulk), delete, import |
| Scheduled Transactions | create, update, delete |

### Not available in YNAB API
- Create/delete budgets
- Create/delete categories
- Create payees (auto-created via transactions)
- Delete accounts

## Roadmap

1. **steelthread** — List accounts with balances for a budget. Proves auth + API + MCP wiring.
2. Remaining read tools (budgets, categories, transactions, payees, months)
3. Transaction queries with filtering (by account, category, payee, date range)
4. Write tools (create/update/delete transactions)
5. Category budget updates
6. Scheduled transactions
7. Delta sync support
8. CI/CD pipeline (GitHub Actions: lint, test, publish to PyPI)

Priority after the steel thread will be driven organically by usage.

## Invariants

- **Money is Decimal, never float.** All YNAB amounts are milliunits.
- **Auth token never logged or exposed.** Only read from env var.
- **Rate limit awareness.** 200 requests/hour per token. Use delta sync where possible.
- **No financial data in error messages or logs.**

## QA Focus Areas

- **Milliunit conversion** — easy to get wrong, causes real budget errors
- **Rate limiting** — 200 req/hr is tight for chatty conversations; delta sync is critical
- **Stale data** — Claude may reference outdated balances from earlier in a conversation
- **Bulk operations** — creating/updating many transactions at once must be reliable
- **Error handling** — YNAB API errors should surface clearly, not swallowed

## Security Focus Areas

- **Write safety** — creating/updating/deleting transactions affects real financial data with no undo API
- **Token handling** — personal access token has full account access, must never be exposed
- **Privacy** — financial data flows through Claude's API during MCP tool calls; users should understand this tradeoff
- **Input validation** — amounts, dates, IDs must be validated before hitting the API

## Conventions

- 4-space indentation (Python)
- `ruff` for linting and formatting, `mypy` strict for types
- Pydantic models for all API request/response shapes
- httpx for async HTTP calls
- Tests with pytest, targeting high coverage on API client and tool logic
