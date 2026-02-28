# py-ynab-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) server for [YNAB (You Need A Budget)](https://www.ynab.com/). Talk to your budget from Claude, Cursor, or any MCP client.

## Features

- Query budgets, accounts, categories, transactions, payees, and months
- Get single-resource details (account, category, payee, transaction)
- Create, update, and delete transactions (single and bulk)
- Update category budgets and metadata
- Rename payees
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

There are several YNAB MCP servers out there:

| Project | Language | License |
|---|---|---|
| [calebl/ynab-mcp-server](https://github.com/calebl/ynab-mcp-server) | TypeScript | MIT |
| [mattweg/ynab-mcp](https://github.com/mattweg/ynab-mcp) | JavaScript | MIT |
| [chrisguidry/you-need-an-mcp](https://github.com/chrisguidry/you-need-an-mcp) | Python | No license |
| **py-ynab-mcp** | Python | MIT |

We wanted an MIT-licensed Python implementation with full API coverage and thorough test coverage. At the time of writing, the only Python option had no OSS license, so we built this one.

## YNAB API Coverage

### Read
- User info, budget settings
- Budgets, accounts, categories, payees, months (list and single)
- Transactions with filtering by account, category, or payee
- Scheduled transactions (list and single)

### Write
- Create, update, delete transactions (single and bulk)
- Update category budgets and metadata
- Rename payees
- Create, update, delete scheduled transactions

### Not available in YNAB API
- Create/delete budgets, categories, or accounts
- Create/delete payees (auto-created via transactions)
- Transaction import

## Development

```bash
# Clone and install
git clone https://github.com/duganth/py-ynab-mcp.git
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
