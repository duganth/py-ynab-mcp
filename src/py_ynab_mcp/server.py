"""py-ynab-mcp: MCP server for YNAB."""

import json
import re
from decimal import Decimal, InvalidOperation

from mcp.server.fastmcp import FastMCP

from py_ynab_mcp.client import YNABClient, YNABError
from py_ynab_mcp.models import (
    Transaction,
    TransactionUpdate,
    TransactionWrite,
    dollars_to_milliunits,
)

mcp = FastMCP("py-ynab-mcp")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_BUDGET_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{12}$|^last-used$"
)
_CLEARED_VALUES = {"cleared", "uncleared", "reconciled"}
_RATE_LIMIT_THRESHOLD = 20


def _format_dollars(amount: Decimal) -> str:
    """Format a dollar amount with proper negative sign placement."""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def _parse_amount(amount: str) -> tuple[Decimal, int] | str:
    """Parse a dollar amount string to (Decimal, milliunits) or error."""
    try:
        d = Decimal(amount)
    except (InvalidOperation, ValueError):
        return (
            f"Invalid amount: {amount!r}. "
            "Provide a number like '42.50' or '-10.00'."
        )
    if d.is_nan() or d.is_infinite():
        return (
            f"Invalid amount: {amount!r}. "
            "Must be a finite number."
        )
    return (d, dollars_to_milliunits(d))


def _validate_date(date: str) -> str | None:
    """Validate YYYY-MM-DD date format. Returns error or None."""
    if not _DATE_RE.match(date):
        return f"Invalid date: {date!r}. Use YYYY-MM-DD format."
    return None


def _validate_uuid(value: str, name: str) -> str | None:
    """Validate UUID format. Returns error or None."""
    if not _UUID_RE.match(value):
        return f"Invalid {name}: {value!r}. Must be a UUID."
    return None


def _validate_budget_id(budget_id: str) -> str | None:
    """Validate budget_id format. Returns error or None."""
    if not _BUDGET_ID_RE.match(budget_id):
        return (
            f"Invalid budget_id: {budget_id!r}. "
            "Must be a UUID or 'last-used'."
        )
    return None


def _validate_cleared(cleared: str) -> str | None:
    """Validate cleared status. Returns error or None."""
    if cleared not in _CLEARED_VALUES:
        return (
            f"Invalid cleared value: {cleared!r}. "
            "Must be 'cleared', 'uncleared', or 'reconciled'."
        )
    return None


def _rate_limit_warning(client: YNABClient) -> str:
    """Return rate limit warning string if near threshold."""
    remaining = client.rate_limit_remaining
    if remaining is not None and remaining <= _RATE_LIMIT_THRESHOLD:
        return (
            f"\n\n⚠️ Rate limit: {remaining}/200 "
            "requests remaining this hour."
        )
    return ""


def _format_transaction(txn: Transaction) -> str:
    """Format a transaction for display."""
    parts = [f"**{_format_dollars(txn.amount)}**"]
    if txn.payee_name:
        parts.append(f"to {txn.payee_name}")
    if txn.category_name:
        parts.append(f"({txn.category_name})")
    parts.append(f"on {txn.date}")
    if txn.memo:
        parts.append(f'— "{txn.memo}"')
    return " ".join(parts)


@mcp.tool()
async def list_accounts(budget_id: str | None = None) -> str:
    """List all accounts for a YNAB budget with balances.

    Args:
        budget_id: Budget ID to list accounts for.
            If not provided, uses the default budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        accounts = await client.get_accounts(bid)

        if not accounts:
            return "No open accounts found."

        lines: list[str] = []
        for acct in accounts:
            bal = _format_dollars(acct.balance)
            cleared = _format_dollars(acct.cleared_balance)
            lines.append(
                f"- **{acct.name}** ({acct.type}): "
                f"{bal} (cleared: {cleared})\n"
                f"  ID: `{acct.id}`"
            )
        return "\n".join(lines)
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


@mcp.tool()
async def list_categories(budget_id: str | None = None) -> str:
    """List all categories for a YNAB budget, grouped by category group.

    Returns category names and IDs needed for creating transactions.

    Args:
        budget_id: Budget ID to list categories for.
            If not provided, uses the default budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        groups = await client.get_categories(bid)

        if not groups:
            return "No categories found."

        lines: list[str] = []
        for group in groups:
            if not group.categories:
                continue
            lines.append(f"**{group.name}**")
            for cat in group.categories:
                bal = _format_dollars(cat.balance)
                lines.append(
                    f"  - {cat.name}: {bal}\n"
                    f"    ID: `{cat.id}`"
                )
        if not lines:
            return "No categories found."
        return "\n".join(lines)
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


@mcp.tool()
async def list_payees(budget_id: str | None = None) -> str:
    """List all payees for a YNAB budget.

    Returns payee names and IDs.

    Args:
        budget_id: Budget ID to list payees for.
            If not provided, uses the default budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        payees = await client.get_payees(bid)

        if not payees:
            return "No payees found."

        lines: list[str] = []
        for payee in payees:
            lines.append(
                f"- {payee.name}\n"
                f"  ID: `{payee.id}`"
            )
        return "\n".join(lines)
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


@mcp.tool()
async def create_transaction(
    account_id: str,
    amount: str,
    date: str,
    payee_name: str | None = None,
    category_id: str | None = None,
    memo: str | None = None,
    cleared: str | None = None,
    approved: bool | None = None,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Create a transaction in YNAB.

    Args:
        account_id: Account UUID.
        amount: Dollar amount ("-42.50" for outflow, "100.00" for inflow).
        date: Transaction date (YYYY-MM-DD).
        payee_name: Payee name (YNAB auto-creates new payees).
        category_id: Category UUID.
        memo: Transaction memo.
        cleared: "cleared", "uncleared", or "reconciled".
        approved: Whether the transaction is approved.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without creating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(account_id, "account_id")
    if err:
        return err
    parsed = _parse_amount(amount)
    if isinstance(parsed, str):
        return parsed
    amount_decimal, milliunits = parsed
    err = _validate_date(date)
    if err:
        return err
    if category_id:
        err = _validate_uuid(category_id, "category_id")
        if err:
            return err
    if cleared:
        err = _validate_cleared(cleared)
        if err:
            return err

    txn = TransactionWrite(
        account_id=account_id,
        date=date,
        amount=milliunits,
        payee_name=payee_name,
        category_id=category_id,
        memo=memo,
        cleared=cleared,
        approved=approved,
    )

    if dry_run:
        lines = [
            "[DRY RUN] Would create transaction:",
            f"  Account: {account_id}",
            f"  Amount: {_format_dollars(amount_decimal)}"
            f" ({milliunits} milliunits)",
            f"  Date: {date}",
        ]
        if payee_name:
            lines.append(f"  Payee: {payee_name}")
        if category_id:
            lines.append(f"  Category: {category_id}")
        if memo:
            lines.append(f"  Memo: {memo}")
        if cleared:
            lines.append(f"  Cleared: {cleared}")
        if approved is not None:
            lines.append(f"  Approved: {approved}")
        return "\n".join(lines)

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        created = await client.create_transaction(bid, txn)
        response = (
            f"Created transaction {created.id}: "
            f"{_format_transaction(created)}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


@mcp.tool()
async def create_transactions(
    transactions_json: str,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Create multiple transactions in YNAB in a single API call.

    Preferred over create_transaction when creating multiple transactions
    to minimize rate limit usage.

    Args:
        transactions_json: JSON array of transactions. Each element:
            {"account_id", "amount", "date", "payee_name"?, "category_id"?,
             "memo"?, "cleared"?, "approved"?}.
            Amounts are in dollars (e.g. "-42.50").
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without creating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        raw_list = json.loads(transactions_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    if not isinstance(raw_list, list) or not raw_list:
        return "Expected a non-empty JSON array of transactions."

    writes: list[TransactionWrite] = []
    previews: list[str] = []

    for i, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            return f"Transaction {i}: expected an object, got {type(raw).__name__}."

        account_id = raw.get("account_id", "")
        err = _validate_uuid(account_id, f"transaction {i} account_id")
        if err:
            return err

        amount_str = str(raw.get("amount", ""))
        parsed = _parse_amount(amount_str)
        if isinstance(parsed, str):
            return f"Transaction {i}: {parsed}"
        amount_decimal, milliunits = parsed

        date_str = str(raw.get("date", ""))
        err = _validate_date(date_str)
        if err:
            return f"Transaction {i}: {err}"

        category_id = raw.get("category_id")
        if category_id:
            err = _validate_uuid(
                category_id, f"transaction {i} category_id"
            )
            if err:
                return err

        cleared_val = raw.get("cleared")
        if cleared_val:
            err = _validate_cleared(str(cleared_val))
            if err:
                return f"Transaction {i}: {err}"

        writes.append(TransactionWrite(
            account_id=account_id,
            date=date_str,
            amount=milliunits,
            payee_name=raw.get("payee_name"),
            category_id=category_id,
            memo=raw.get("memo"),
            cleared=raw.get("cleared"),
            approved=raw.get("approved"),
        ))

        previews.append(
            f"  {i + 1}. {_format_dollars(amount_decimal)}"
            f" on {date_str}"
            + (f" to {raw.get('payee_name')}"
               if raw.get("payee_name") else "")
        )

    if dry_run:
        header = (
            f"[DRY RUN] Would create {len(writes)} transactions:"
        )
        return header + "\n" + "\n".join(previews)

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        result = await client.create_transactions(bid, writes)
        lines = [
            f"Created {len(result.transaction_ids)} transactions."
        ]
        if result.duplicate_import_ids:
            lines.append(
                f"Duplicates skipped: "
                f"{len(result.duplicate_import_ids)}"
            )
        lines.append(
            f"IDs: {', '.join(result.transaction_ids)}"
        )
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


@mcp.tool()
async def update_transaction(
    transaction_id: str,
    account_id: str | None = None,
    amount: str | None = None,
    date: str | None = None,
    payee_name: str | None = None,
    category_id: str | None = None,
    memo: str | None = None,
    cleared: str | None = None,
    approved: bool | None = None,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Update fields of an existing YNAB transaction.

    Only provide the fields you want to change.

    Args:
        transaction_id: Transaction UUID to update.
        account_id: New account UUID.
        amount: New dollar amount ("-42.50" for outflow).
        date: New date (YYYY-MM-DD).
        payee_name: New payee name.
        category_id: New category UUID.
        memo: New memo.
        cleared: "cleared", "uncleared", or "reconciled".
        approved: Whether the transaction is approved.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(transaction_id, "transaction_id")
    if err:
        return err

    update_fields: dict[str, object] = {"id": transaction_id}
    preview_lines: list[str] = []

    if account_id is not None:
        err = _validate_uuid(account_id, "account_id")
        if err:
            return err
        update_fields["account_id"] = account_id
        preview_lines.append(f"  Account: {account_id}")

    if amount is not None:
        parsed = _parse_amount(amount)
        if isinstance(parsed, str):
            return parsed
        amount_decimal, milliunits = parsed
        update_fields["amount"] = milliunits
        preview_lines.append(
            f"  Amount: {_format_dollars(amount_decimal)}"
            f" ({milliunits} milliunits)"
        )

    if date is not None:
        err = _validate_date(date)
        if err:
            return err
        update_fields["date"] = date
        preview_lines.append(f"  Date: {date}")

    if payee_name is not None:
        update_fields["payee_name"] = payee_name
        preview_lines.append(f"  Payee: {payee_name}")

    if category_id is not None:
        err = _validate_uuid(category_id, "category_id")
        if err:
            return err
        update_fields["category_id"] = category_id
        preview_lines.append(f"  Category: {category_id}")

    if memo is not None:
        update_fields["memo"] = memo
        preview_lines.append(f"  Memo: {memo}")

    if cleared is not None:
        err = _validate_cleared(cleared)
        if err:
            return err
        update_fields["cleared"] = cleared
        preview_lines.append(f"  Cleared: {cleared}")

    if approved is not None:
        update_fields["approved"] = approved
        preview_lines.append(f"  Approved: {approved}")

    if not preview_lines:
        return "No fields to update."

    txn_update = TransactionUpdate(**update_fields)  # type: ignore[arg-type]

    if dry_run:
        header = (
            f"[DRY RUN] Would update transaction "
            f"{transaction_id}:"
        )
        return header + "\n" + "\n".join(preview_lines)

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        updated = await client.update_transaction(bid, txn_update)
        response = (
            f"Updated transaction {updated.id}: "
            f"{_format_transaction(updated)}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


@mcp.tool()
async def delete_transaction(
    transaction_id: str,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Delete a transaction from YNAB.

    Args:
        transaction_id: Transaction UUID to delete.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without deleting.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(transaction_id, "transaction_id")
    if err:
        return err

    if dry_run:
        return (
            f"[DRY RUN] Would delete transaction "
            f"{transaction_id}."
        )

    try:
        client = YNABClient()
    except ValueError:
        return (
            "Configuration error: YNAB access token not found. "
            "Set the YNAB_ACCESS_TOKEN environment variable."
        )

    try:
        await client.delete_transaction(bid, transaction_id)
        response = f"Deleted transaction {transaction_id}."
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception:
        return "An unexpected error occurred."
    finally:
        await client.close()


def main() -> None:
    """Run the MCP server."""
    mcp.run()
