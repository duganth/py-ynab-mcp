"""py-ynab-mcp: MCP server for YNAB."""

import datetime
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from py_ynab_mcp.client import YNABClient, YNABError
from py_ynab_mcp.models import (
    CategoryBudgetWrite,
    CategoryUpdate,
    PayeeUpdate,
    ScheduledTransactionUpdate,
    ScheduledTransactionWrite,
    Transaction,
    TransactionUpdate,
    TransactionWrite,
    dollars_to_milliunits,
)

# Type alias for tool context — avoids repeating generic params.
ToolContext = Context[Any, dict[str, YNABClient], Any]


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, YNABClient]]:
    """Manage a shared YNAB client across all tool calls."""
    client = YNABClient()
    try:
        yield {"ynab_client": client}
    finally:
        await client.close()


mcp = FastMCP("py-ynab-mcp", lifespan=lifespan)


def _get_client(ctx: ToolContext) -> YNABClient:
    """Get the shared YNAB client from the lifespan context."""
    client: YNABClient = ctx.request_context.lifespan_context["ynab_client"]
    return client

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_BUDGET_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{12}$|^last-used$|^default$"
)
_CLEARED_VALUES = {"cleared", "uncleared", "reconciled"}
_TRANSACTION_TYPE_VALUES = {"uncategorized", "unapproved"}
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
    try:
        return (d, dollars_to_milliunits(d))
    except ValueError:
        return (
            f"Invalid amount: {amount!r}. "
            "Too many decimal places (max 3)."
        )


def _validate_date(date: str) -> str | None:
    """Validate YYYY-MM-DD date format and calendar value."""
    if not _DATE_RE.match(date):
        return f"Invalid date: {date!r}. Use YYYY-MM-DD format."
    try:
        year, month, day = date.split("-")
        datetime.date(int(year), int(month), int(day))
    except ValueError:
        return f"Invalid date: {date!r}. Not a valid calendar date."
    return None


def _validate_uuid(value: object, name: str) -> str | None:
    """Validate UUID format. Returns error or None."""
    if not isinstance(value, str) or not _UUID_RE.match(value):
        return f"Invalid {name}: {value!r}. Must be a UUID."
    return None


def _validate_budget_id(budget_id: str) -> str | None:
    """Validate budget_id format. Returns error or None."""
    if not _BUDGET_ID_RE.match(budget_id):
        return (
            f"Invalid budget_id: {budget_id!r}. "
            "Must be a UUID, 'last-used', or 'default'."
        )
    return None


def _validate_transaction_type(type_val: str) -> str | None:
    """Validate transaction type filter. Returns error or None."""
    if type_val not in _TRANSACTION_TYPE_VALUES:
        return (
            f"Invalid type: {type_val!r}. "
            "Must be 'uncategorized' or 'unapproved'."
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


def _format_month(date_str: str) -> str:
    """Format a YYYY-MM-DD date as 'Mon YYYY' (e.g. 'Jan 2024')."""
    try:
        year, month, _day = date_str.split("-")
        months = [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        return f"{months[int(month)]} {year}"
    except (ValueError, IndexError):
        return date_str


@mcp.tool()
async def list_budgets(ctx: ToolContext) -> str:
    """List all budgets for the authenticated YNAB user.

    Returns budget names, IDs, date ranges, and last modified dates.
    Use the budget ID with other tools to target a specific budget.
    """
    try:
        client = _get_client(ctx)
        budgets = await client.get_budgets()

        if not budgets:
            return "No budgets found."

        lines: list[str] = []
        for b in budgets:
            modified = b.last_modified_on[:10]
            first = _format_month(b.first_month)
            last = _format_month(b.last_month)
            lines.append(
                f"- **{b.name}** "
                f"(last modified: {modified})\n"
                f"  {first} \u2013 {last}\n"
                f"  ID: `{b.id}`"
            )
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def list_accounts(
    ctx: ToolContext, budget_id: str | None = None
) -> str:
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
        client = _get_client(ctx)
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
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def list_categories(
    ctx: ToolContext, budget_id: str | None = None
) -> str:
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
        client = _get_client(ctx)
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
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def list_payees(
    ctx: ToolContext, budget_id: str | None = None
) -> str:
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
        client = _get_client(ctx)
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
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def list_months(
    ctx: ToolContext, budget_id: str | None = None
) -> str:
    """List all budget months with summary figures.

    Returns each month's income, budgeted, activity, available
    (to-be-budgeted), and age of money.

    Args:
        budget_id: Budget ID. If not provided, uses the default budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        client = _get_client(ctx)
        months = await client.get_months(bid)

        if not months:
            return "No months found."

        lines: list[str] = []
        for m in months:
            age = (
                f"{m.age_of_money} days"
                if m.age_of_money is not None
                else "N/A"
            )
            line = (
                f"- **{_format_month(m.month)}**: "
                f"Income {_format_dollars(m.income)} | "
                f"Budgeted {_format_dollars(m.budgeted)} | "
                f"Activity {_format_dollars(m.activity)} | "
                f"Available {_format_dollars(m.to_be_budgeted)} | "
                f"Age of Money: {age}"
            )
            if m.note:
                line += f'\n  Note: "{m.note}"'
            lines.append(line)
        return "\n".join(lines)
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


def _validate_month(month: str) -> str | None:
    """Validate month param: YYYY-MM-DD or 'current'."""
    if month == "current":
        return None
    return _validate_date(month)


@mcp.tool()
async def get_month(
    ctx: ToolContext,
    month: str,
    budget_id: str | None = None,
) -> str:
    """Get a single budget month with per-category breakdown.

    Returns the month summary (income, budgeted, activity, available)
    plus every category's budgeted/activity/balance.

    Args:
        month: Month to retrieve (YYYY-MM-DD, first of month,
            e.g. "2026-03-01") or "current" for the current month.
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_month(month)
    if err:
        return err

    try:
        client = _get_client(ctx)
        detail = await client.get_month(bid, month=month)

        age = (
            f"{detail.age_of_money} days"
            if detail.age_of_money is not None
            else "N/A"
        )
        lines: list[str] = [
            f"## {_format_month(detail.month)}",
            "",
            f"- Income: {_format_dollars(detail.income)}",
            f"- Budgeted: {_format_dollars(detail.budgeted)}",
            f"- Activity: {_format_dollars(detail.activity)}",
            f"- Available: {_format_dollars(detail.to_be_budgeted)}",
            f"- Age of Money: {age}",
        ]
        if detail.note:
            lines.append(f'- Note: "{detail.note}"')

        # List categories (YNAB returns them in group order).
        cats = [c for c in detail.categories if not c.deleted]
        if cats:
            lines.append("")
            lines.append("### Categories")
            for cat in cats:
                lines.append(
                    f"- {cat.name}: "
                    f"Budgeted {_format_dollars(cat.budgeted)} | "
                    f"Activity {_format_dollars(cat.activity)} | "
                    f"Balance {_format_dollars(cat.balance)}"
                )

        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def list_transactions(
    ctx: ToolContext,
    since_date: str,
    account_id: str | None = None,
    category_id: str | None = None,
    payee_id: str | None = None,
    type: str | None = None,
    budget_id: str | None = None,
) -> str:
    """List transactions from YNAB with optional filters.

    Returns transactions since the given date. Optionally filter by
    one of: account, category, or payee (mutually exclusive).

    Args:
        since_date: Start date (YYYY-MM-DD). Required.
        account_id: Filter by account UUID.
        category_id: Filter by category UUID.
        payee_id: Filter by payee UUID.
        type: Filter by "uncategorized" or "unapproved".
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    err = _validate_date(since_date)
    if err:
        return err

    # Validate mutual exclusivity of filter IDs.
    filter_count = sum(
        1 for f in (account_id, category_id, payee_id)
        if f is not None
    )
    if filter_count > 1:
        return (
            "Only one of account_id, category_id, or "
            "payee_id may be provided."
        )

    if account_id:
        err = _validate_uuid(account_id, "account_id")
        if err:
            return err
    if category_id:
        err = _validate_uuid(category_id, "category_id")
        if err:
            return err
    if payee_id:
        err = _validate_uuid(payee_id, "payee_id")
        if err:
            return err
    if type:
        err = _validate_transaction_type(type)
        if err:
            return err

    try:
        client = _get_client(ctx)
        transactions = await client.get_transactions(
            bid,
            since_date=since_date,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee_id,
            type=type,
        )

        if not transactions:
            return f"No transactions found since {since_date}."

        total = sum(
            (t.amount for t in transactions), Decimal(0)
        )
        lines: list[str] = [
            f"Transactions since {since_date} "
            f"({len(transactions)} found):",
            "",
        ]
        for i, txn in enumerate(transactions, 1):
            lines.append(
                f"{i}. {txn.date}: "
                f"{_format_transaction(txn)}\n"
                f"   ID: `{txn.id}`"
            )
        lines.append("")
        lines.append(
            f"Total: {_format_dollars(total)} "
            f"({len(transactions)} transactions)"
        )

        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {e.__class__.__name__}"


@mcp.tool()
async def create_transaction(
    ctx: ToolContext,
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
        client = _get_client(ctx)
        created = await client.create_transaction(bid, txn)
        response = (
            f"Created transaction {created.id}: "
            f"{_format_transaction(created)}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def create_transactions(
    ctx: ToolContext,
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
        if cleared_val is not None:
            cleared_str = str(cleared_val)
            err = _validate_cleared(cleared_str)
            if err:
                return f"Transaction {i}: {err}"
        else:
            cleared_str = None

        writes.append(TransactionWrite(
            account_id=account_id,
            date=date_str,
            amount=milliunits,
            payee_name=raw.get("payee_name"),
            category_id=category_id,
            memo=raw.get("memo"),
            cleared=cleared_str,
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
        client = _get_client(ctx)
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
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def update_transaction(
    ctx: ToolContext,
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
        client = _get_client(ctx)
        updated = await client.update_transaction(bid, txn_update)
        response = (
            f"Updated transaction {updated.id}: "
            f"{_format_transaction(updated)}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def delete_transaction(
    ctx: ToolContext,
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
        client = _get_client(ctx)
        await client.delete_transaction(bid, transaction_id)
        response = f"Deleted transaction {transaction_id}."
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def update_category_budget(
    ctx: ToolContext,
    category_id: str,
    month: str,
    amount: str,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Set the budgeted (assigned) amount for a category in a specific month.

    Args:
        category_id: Category UUID.
        month: Month to update (YYYY-MM-DD, first of month, e.g. "2026-03-01").
        amount: Dollar amount to assign (e.g. "500.00").
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(category_id, "category_id")
    if err:
        return err
    err = _validate_date(month)
    if err:
        return err
    parsed = _parse_amount(amount)
    if isinstance(parsed, str):
        return parsed
    amount_decimal, milliunits = parsed

    if dry_run:
        return (
            f"[DRY RUN] Would set budget for category "
            f"{category_id} in {month}: "
            f"{_format_dollars(amount_decimal)}"
            f" ({milliunits} milliunits)"
        )

    try:
        client = _get_client(ctx)
        budget_write = CategoryBudgetWrite(budgeted=milliunits)
        updated = await client.update_category_budget(
            bid, month, category_id, budget_write
        )
        response = (
            f"Updated budget for {updated.name} "
            f"({_format_month(month)}): "
            f"{_format_dollars(updated.budgeted)}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def update_category(
    ctx: ToolContext,
    category_id: str,
    name: str | None = None,
    note: str | None = None,
    hidden: bool | None = None,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Update category metadata in YNAB.

    Only provide the fields you want to change.

    Args:
        category_id: Category UUID.
        name: New category name.
        note: New category note.
        hidden: Whether to hide the category.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(category_id, "category_id")
    if err:
        return err

    changes: list[str] = []
    if name is not None:
        changes.append(f'name \u2192 "{name}"')
    if note is not None:
        changes.append(f'note \u2192 "{note}"')
    if hidden is not None:
        changes.append(
            f'hidden \u2192 {"yes" if hidden else "no"}'
        )

    if not changes:
        return "No fields to update."

    update = CategoryUpdate(
        name=name, note=note, hidden=hidden
    )

    if dry_run:
        return (
            f"[DRY RUN] Would update category "
            f"{category_id}: {', '.join(changes)}"
        )

    try:
        client = _get_client(ctx)
        updated = await client.update_category(
            bid, category_id, update
        )
        response = (
            f"Updated category {updated.name}: "
            f"{', '.join(changes)}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


# --- Scheduled transaction tools ---

_FREQUENCY_VALUES = {
    "never", "daily", "weekly", "everyOtherWeek",
    "twiceAMonth", "every4Weeks", "monthly",
    "everyOtherMonth", "every3Months", "every4Months",
    "twiceAYear", "yearly", "everyOtherYear",
}

_FREQUENCY_LABELS: dict[str, str] = {
    "never": "Never",
    "daily": "Daily",
    "weekly": "Weekly",
    "everyOtherWeek": "Every other week",
    "twiceAMonth": "Twice a month",
    "every4Weeks": "Every 4 weeks",
    "monthly": "Monthly",
    "everyOtherMonth": "Every other month",
    "every3Months": "Every 3 months",
    "every4Months": "Every 4 months",
    "twiceAYear": "Twice a year",
    "yearly": "Yearly",
    "everyOtherYear": "Every other year",
}


def _format_frequency(frequency: str) -> str:
    """Convert YNAB frequency value to human-readable label."""
    return _FREQUENCY_LABELS.get(frequency, frequency)


def _validate_frequency(frequency: str) -> str | None:
    """Validate frequency value. Returns error or None."""
    if frequency not in _FREQUENCY_VALUES:
        return (
            f"Invalid frequency: {frequency!r}. "
            f"Must be one of: {', '.join(sorted(_FREQUENCY_VALUES))}."
        )
    return None


@mcp.tool()
async def list_scheduled_transactions(
    ctx: ToolContext, budget_id: str | None = None
) -> str:
    """List all scheduled transactions for a YNAB budget.

    Returns each scheduled transaction with its frequency, next date,
    amount, payee, and category.

    Args:
        budget_id: Budget ID. If not provided, uses the default budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        client = _get_client(ctx)
        scheduled = await client.get_scheduled_transactions(
            bid
        )

        if not scheduled:
            return "No scheduled transactions found."

        # Sort by next date.
        scheduled.sort(key=lambda st: st.date_next)

        lines: list[str] = []
        for st in scheduled:
            parts = [
                f"**{_format_dollars(st.amount)}**",
                f"{_format_frequency(st.frequency)}",
            ]
            if st.payee_name:
                parts.append(f"to {st.payee_name}")
            if st.category_name:
                parts.append(f"({st.category_name})")
            parts.append(f"— next: {st.date_next}")
            if st.memo:
                parts.append(f'"{st.memo}"')
            line = (
                f"- {' '.join(parts)}\n"
                f"  ID: `{st.id}`"
            )
            lines.append(line)
        return "\n".join(lines)
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_scheduled_transaction(
    ctx: ToolContext,
    scheduled_transaction_id: str,
    budget_id: str | None = None,
) -> str:
    """Get details of a single scheduled transaction.

    Returns full detail including subtransactions if present.

    Args:
        scheduled_transaction_id: Scheduled transaction UUID.
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(
        scheduled_transaction_id, "scheduled_transaction_id"
    )
    if err:
        return err

    try:
        client = _get_client(ctx)
        st = await client.get_scheduled_transaction(
            bid, scheduled_transaction_id
        )

        lines: list[str] = [
            f"**{_format_dollars(st.amount)}** "
            f"{_format_frequency(st.frequency)}",
            "",
            f"- Account: {st.account_name}",
            f"- First date: {st.date_first}",
            f"- Next date: {st.date_next}",
        ]
        if st.payee_name:
            lines.append(f"- Payee: {st.payee_name}")
        if st.category_name:
            lines.append(f"- Category: {st.category_name}")
        if st.memo:
            lines.append(f'- Memo: "{st.memo}"')
        if st.flag_color:
            lines.append(f"- Flag: {st.flag_color}")
        lines.append(f"- ID: `{st.id}`")

        subs = [
            s for s in st.subtransactions if not s.deleted
        ]
        if subs:
            lines.append("")
            lines.append("### Subtransactions")
            for sub in subs:
                sub_parts = [
                    f"  - {_format_dollars(sub.amount)}"
                ]
                if sub.memo:
                    sub_parts.append(f'"{sub.memo}"')
                lines.append(" ".join(sub_parts))

        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def create_scheduled_transaction(
    ctx: ToolContext,
    account_id: str,
    amount: str,
    date: str,
    frequency: str,
    payee_name: str | None = None,
    category_id: str | None = None,
    memo: str | None = None,
    flag_color: str | None = None,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Create a scheduled (recurring) transaction in YNAB.

    Args:
        account_id: Account UUID.
        amount: Dollar amount ("-42.50" for outflow, "100.00" for inflow).
        date: First occurrence date (YYYY-MM-DD).
        frequency: Recurrence frequency (e.g. "monthly", "weekly",
            "everyOtherWeek", "yearly"). See YNAB docs for all values.
        payee_name: Payee name.
        category_id: Category UUID.
        memo: Transaction memo.
        flag_color: Flag color.
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
    err = _validate_frequency(frequency)
    if err:
        return err
    if category_id:
        err = _validate_uuid(category_id, "category_id")
        if err:
            return err

    txn = ScheduledTransactionWrite(
        account_id=account_id,
        date=date,
        amount=milliunits,
        frequency=frequency,
        payee_name=payee_name,
        category_id=category_id,
        memo=memo,
        flag_color=flag_color,
    )

    if dry_run:
        lines = [
            "[DRY RUN] Would create scheduled transaction:",
            f"  Account: {account_id}",
            f"  Amount: {_format_dollars(amount_decimal)}"
            f" ({milliunits} milliunits)",
            f"  Date: {date}",
            f"  Frequency: {_format_frequency(frequency)}",
        ]
        if payee_name:
            lines.append(f"  Payee: {payee_name}")
        if category_id:
            lines.append(f"  Category: {category_id}")
        if memo:
            lines.append(f"  Memo: {memo}")
        if flag_color:
            lines.append(f"  Flag: {flag_color}")
        return "\n".join(lines)

    try:
        client = _get_client(ctx)
        created = (
            await client.create_scheduled_transaction(
                bid, txn
            )
        )
        response = (
            f"Created scheduled transaction {created.id}: "
            f"{_format_dollars(created.amount)} "
            f"{_format_frequency(created.frequency)} "
            f"starting {created.date_first}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def update_scheduled_transaction(
    ctx: ToolContext,
    scheduled_transaction_id: str,
    account_id: str | None = None,
    amount: str | None = None,
    date: str | None = None,
    frequency: str | None = None,
    payee_name: str | None = None,
    category_id: str | None = None,
    memo: str | None = None,
    flag_color: str | None = None,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Update fields of an existing scheduled transaction.

    Only provide the fields you want to change.

    Args:
        scheduled_transaction_id: Scheduled transaction UUID.
        account_id: New account UUID.
        amount: New dollar amount.
        date: New first date (YYYY-MM-DD).
        frequency: New frequency.
        payee_name: New payee name.
        category_id: New category UUID.
        memo: New memo.
        flag_color: New flag color.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(
        scheduled_transaction_id, "scheduled_transaction_id"
    )
    if err:
        return err

    update_fields: dict[str, object] = {}
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

    if frequency is not None:
        err = _validate_frequency(frequency)
        if err:
            return err
        update_fields["frequency"] = frequency
        preview_lines.append(
            f"  Frequency: {_format_frequency(frequency)}"
        )

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

    if flag_color is not None:
        update_fields["flag_color"] = flag_color
        preview_lines.append(f"  Flag: {flag_color}")

    if not preview_lines:
        return "No fields to update."

    update = ScheduledTransactionUpdate(
        **update_fields  # type: ignore[arg-type]
    )

    if dry_run:
        header = (
            f"[DRY RUN] Would update scheduled transaction "
            f"{scheduled_transaction_id}:"
        )
        return header + "\n" + "\n".join(preview_lines)

    try:
        client = _get_client(ctx)
        updated = (
            await client.update_scheduled_transaction(
                bid, scheduled_transaction_id, update
            )
        )
        response = (
            f"Updated scheduled transaction {updated.id}: "
            f"{_format_dollars(updated.amount)} "
            f"{_format_frequency(updated.frequency)} "
            f"next: {updated.date_next}"
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def delete_scheduled_transaction(
    ctx: ToolContext,
    scheduled_transaction_id: str,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Delete a scheduled transaction from YNAB.

    Args:
        scheduled_transaction_id: Scheduled transaction UUID.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without deleting.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(
        scheduled_transaction_id, "scheduled_transaction_id"
    )
    if err:
        return err

    if dry_run:
        return (
            f"[DRY RUN] Would delete scheduled transaction "
            f"{scheduled_transaction_id}."
        )

    try:
        client = _get_client(ctx)
        await client.delete_scheduled_transaction(
            bid, scheduled_transaction_id
        )
        response = (
            f"Deleted scheduled transaction "
            f"{scheduled_transaction_id}."
        )
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_user(ctx: ToolContext) -> str:
    """Get the authenticated YNAB user.

    Returns the user ID.
    """
    try:
        client = _get_client(ctx)
        user = await client.get_user()
        response = f"User ID: `{user.id}`"
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_budget_settings(
    ctx: ToolContext, budget_id: str | None = None
) -> str:
    """Get budget settings including date and currency format.

    Args:
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err

    try:
        client = _get_client(ctx)
        settings = await client.get_budget_settings(bid)

        df = settings.date_format
        cf = settings.currency_format
        lines = [
            "**Date Format**",
            f"  Format: {df.format}",
            "",
            "**Currency Format**",
            f"  ISO code: {cf.iso_code}",
            f"  Symbol: {cf.currency_symbol}"
            f" ({'before' if cf.symbol_first else 'after'})",
            f"  Example: {cf.example_format}",
            f"  Decimals: {cf.decimal_digits}",
            f"  Decimal separator: {cf.decimal_separator!r}",
            f"  Group separator: {cf.group_separator!r}",
        ]
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_account(
    ctx: ToolContext,
    account_id: str,
    budget_id: str | None = None,
) -> str:
    """Get a single YNAB account with full details.

    Returns balance, type, on-budget status, note, and more.

    Args:
        account_id: Account UUID.
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(account_id, "account_id")
    if err:
        return err

    try:
        client = _get_client(ctx)
        acct = await client.get_account(bid, account_id)

        bal = _format_dollars(acct.balance)
        cleared = _format_dollars(acct.cleared_balance)
        uncleared = _format_dollars(acct.uncleared_balance)
        status_parts: list[str] = []
        if acct.closed:
            status_parts.append("CLOSED")
        if acct.deleted:
            status_parts.append("DELETED")
        status_suffix = (
            f" [{', '.join(status_parts)}]"
            if status_parts else ""
        )
        lines = [
            f"**{acct.name}** ({acct.type}){status_suffix}",
            f"  Balance: {bal}",
            f"  Cleared: {cleared}",
            f"  Uncleared: {uncleared}",
            f"  On budget: {'Yes' if acct.on_budget else 'No'}",
        ]
        if acct.note:
            lines.append(f"  Note: {acct.note}")
        if acct.transfer_payee_id:
            lines.append(
                f"  Transfer payee ID: `{acct.transfer_payee_id}`"
            )
        lines.append(f"  ID: `{acct.id}`")
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_category(
    ctx: ToolContext,
    category_id: str,
    budget_id: str | None = None,
) -> str:
    """Get a single YNAB category with budget details.

    Returns budgeted, activity, balance, and metadata.

    Args:
        category_id: Category UUID.
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(category_id, "category_id")
    if err:
        return err

    try:
        client = _get_client(ctx)
        cat = await client.get_category(bid, category_id)

        deleted_tag = " [DELETED]" if cat.deleted else ""
        lines = [
            f"**{cat.name}**{deleted_tag}",
            f"  Budgeted: {_format_dollars(cat.budgeted)}",
            f"  Activity: {_format_dollars(cat.activity)}",
            f"  Balance: {_format_dollars(cat.balance)}",
        ]
        if cat.note:
            lines.append(f"  Note: {cat.note}")
        if cat.hidden:
            lines.append("  Hidden: Yes")
        if cat.category_group_id:
            lines.append(
                f"  Group ID: `{cat.category_group_id}`"
            )
        lines.append(f"  ID: `{cat.id}`")
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_payee(
    ctx: ToolContext,
    payee_id: str,
    budget_id: str | None = None,
) -> str:
    """Get a single YNAB payee.

    Args:
        payee_id: Payee UUID.
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(payee_id, "payee_id")
    if err:
        return err

    try:
        client = _get_client(ctx)
        payee = await client.get_payee(bid, payee_id)

        deleted_tag = " [DELETED]" if payee.deleted else ""
        lines = [f"**{payee.name}**{deleted_tag}"]
        if payee.transfer_account_id:
            lines.append(
                f"  Transfer account ID: "
                f"`{payee.transfer_account_id}`"
            )
        lines.append(f"  ID: `{payee.id}`")
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def update_payee(
    ctx: ToolContext,
    payee_id: str,
    name: str,
    budget_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Update a YNAB payee (rename).

    Args:
        payee_id: Payee UUID.
        name: New name for the payee.
        budget_id: Budget ID. Defaults to last-used budget.
        dry_run: Validate and preview without updating.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(payee_id, "payee_id")
    if err:
        return err
    if not name or not name.strip():
        return "Payee name cannot be empty."

    if dry_run:
        return (
            f"[DRY RUN] Would rename payee {payee_id} "
            f"to {name!r}."
        )

    try:
        client = _get_client(ctx)
        payee = await client.update_payee(
            bid, payee_id, PayeeUpdate(name=name.strip())
        )
        response = f"Renamed payee to **{payee.name}**."
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


@mcp.tool()
async def get_transaction(
    ctx: ToolContext,
    transaction_id: str,
    budget_id: str | None = None,
) -> str:
    """Get a single YNAB transaction with full details.

    Args:
        transaction_id: Transaction UUID.
        budget_id: Budget ID. Defaults to last-used budget.
    """
    bid = budget_id or "last-used"
    err = _validate_budget_id(bid)
    if err:
        return err
    err = _validate_uuid(transaction_id, "transaction_id")
    if err:
        return err

    try:
        client = _get_client(ctx)
        txn = await client.get_transaction(bid, transaction_id)

        deleted_tag = " [DELETED]" if txn.deleted else ""
        lines = [
            _format_transaction(txn) + deleted_tag,
            f"  Account: {txn.account_name}",
            f"  Status: {txn.cleared}"
            f" ({'approved' if txn.approved else 'unapproved'})",
        ]
        if txn.payee_id:
            lines.append(f"  Payee ID: `{txn.payee_id}`")
        if txn.category_id:
            lines.append(
                f"  Category ID: `{txn.category_id}`"
            )
        lines.append(f"  Account ID: `{txn.account_id}`")
        lines.append(f"  ID: `{txn.id}`")
        response = "\n".join(lines)
        response += _rate_limit_warning(client)
        return response
    except YNABError as e:
        return f"YNAB API error: {e.detail}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__}"


def main() -> None:
    """Run the MCP server."""
    mcp.run()
