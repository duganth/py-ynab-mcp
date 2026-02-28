# py-ynab-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) server for [YNAB (You Need A Budget)](https://www.ynab.com/). Talk to your budget from Claude, Cursor, or any MCP client.

## Features

- Query budgets, accounts, categories, transactions, payees, and months
- Get single-resource details (account, category, payee, transaction)
- Create, update, and delete transactions (single and bulk)
- Update category budgets and metadata
- Manage scheduled transactions (full CRUD)
- Budget settings and user info

## Install

```bash
uvx py-ynab-mcp
```

Or with pip:

```bash
pip install py-ynab-mcp
```

## Setup

1. Get a YNAB [Personal Access Token](https://app.ynab.com/settings/developer)
2. Add to your MCP client config:

```json
{
  "mcpServers": {
    "ynab": {
      "command": "uvx",
      "args": ["py-ynab-mcp"],
      "env": {
        "YNAB_ACCESS_TOKEN": "your-token-here"
      }
    }
  }
}
```

## Why this project?

There are several YNAB MCP servers out there. Here's why we built another one:

| Project | Language | Notes |
|---|---|---|
| [calebl/ynab-mcp-server](https://github.com/calebl/ynab-mcp-server) | TypeScript | Full CRUD, but inconsistent code quality |
| [mattweg/ynab-mcp](https://github.com/mattweg/ynab-mcp) | JavaScript | Has known bugs (amount parsing), dormant since mid-2025 |
| [chrisguidry/you-need-an-mcp](https://github.com/chrisguidry/you-need-an-mcp) | Python | Excellent code quality, but no OSS license |
| **py-ynab-mcp** | Python | MIT licensed, full API coverage, actively maintained |

We wanted a Python MCP server for YNAB that is properly licensed, well-tested, and covers the full YNAB API — including write operations for transaction management. The best existing implementation had no license, making it unsuitable for use or contribution. So here we are.

## YNAB API Coverage

### Read
- User info, budget settings
- Budgets, accounts, categories, payees, months (list and single)
- Transactions with filtering by account, category, or payee
- Scheduled transactions (list and single)

### Write
- Create, update, delete transactions (single and bulk)
- Update category budgets and metadata
- Create, update, delete scheduled transactions

### Not available in YNAB API
- Create/delete budgets, categories, or accounts
- Create/update/delete payees (auto-created via transactions)
- Transaction import

## Development

```bash
# Clone and install
git clone https://github.com/duges/py-ynab-mcp.git
cd py-ynab-mcp
uv sync

# Run tests
uv run pytest

# Lint and type check
uv run ruff check .
uv run mypy src/
```

## License

MIT
