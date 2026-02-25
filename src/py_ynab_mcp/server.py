"""py-ynab-mcp: MCP server for YNAB."""

from decimal import Decimal

from mcp.server.fastmcp import FastMCP

from py_ynab_mcp.client import YNABClient, YNABError

mcp = FastMCP("py-ynab-mcp")


def _format_dollars(amount: Decimal) -> str:
    """Format a dollar amount with proper negative sign placement."""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


@mcp.tool()
async def list_accounts(budget_id: str | None = None) -> str:
    """List all accounts for a YNAB budget with balances.

    Args:
        budget_id: Budget ID to list accounts for.
            If not provided, uses the default budget.
    """
    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        bid = budget_id or "last-used"
        accounts = await client.get_accounts(bid)

        if not accounts:
            return "No open accounts found."

        lines: list[str] = []
        for acct in accounts:
            bal = _format_dollars(acct.balance)
            cleared = _format_dollars(acct.cleared_balance)
            lines.append(
                f"- **{acct.name}** ({acct.type}): "
                f"{bal} (cleared: {cleared})"
            )
        return "\n".join(lines)
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


def main() -> None:
    """Run the MCP server."""
    mcp.run()
