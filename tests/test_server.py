"""Tests for MCP server tool integration."""

import inspect
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from py_ynab_mcp.client import YNABError
from py_ynab_mcp.models import (
    Account,
    AccountDetail,
    BudgetSettings,
    BudgetSummary,
    BulkCreateResponse,
    Category,
    CategoryGroup,
    CurrencyFormat,
    DateFormat,
    MonthDetail,
    MonthSummary,
    Payee,
    PayeeDetail,
    ScheduledSubTransaction,
    ScheduledTransaction,
    Transaction,
    User,
)
from py_ynab_mcp.server import (
    clear_category_target,
    create_category,
    create_scheduled_transaction,
    create_transaction,
    create_transactions,
    delete_scheduled_transaction,
    delete_transaction,
    get_account,
    get_budget_settings,
    get_category,
    get_month,
    get_payee,
    get_scheduled_transaction,
    get_transaction,
    get_user,
    list_accounts,
    list_budgets,
    list_categories,
    list_months,
    list_payees,
    list_scheduled_transactions,
    list_transactions,
    update_category,
    update_category_budget,
    update_payee,
    update_scheduled_transaction,
    update_transaction,
)

_VALID_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_VALID_UUID_2 = "11111111-2222-3333-4444-555555555555"


def _mock_ctx(client: AsyncMock | None = None) -> MagicMock:
    """Create a mock MCP Context with an optional mock YNAB client."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "ynab_client": client or AsyncMock(),
    }
    return ctx


def _make_account(
    name: str = "Checking",
    acct_type: str = "checking",
    balance: Decimal = Decimal("100.00"),
    cleared: Decimal = Decimal("95.00"),
) -> Account:
    return Account(
        id="test-id",
        name=name,
        type=acct_type,
        balance=balance,
        cleared_balance=cleared,
        closed=False,
        deleted=False,
    )


def _make_transaction(
    txn_id: str = "txn-1",
    amount: Decimal = Decimal("-42.50"),
    payee_name: str | None = "Costco",
    category_name: str | None = "Groceries",
    memo: str | None = "Weekly shop",
    cleared: str = "cleared",
    approved: bool = True,
) -> Transaction:
    return Transaction(
        id=txn_id,
        account_id=_VALID_UUID,
        account_name="Checking",
        date="2026-02-25",
        amount=amount,
        payee_id=None,
        payee_name=payee_name,
        category_id=None,
        category_name=category_name,
        memo=memo,
        cleared=cleared,
        approved=approved,
        deleted=False,
    )


def _make_budget(
    name: str = "My Budget",
    budget_id: str = _VALID_UUID,
    last_modified: str = "2026-02-28T12:00:00+00:00",
    first_month: str = "2024-01-01",
    last_month: str = "2026-02-01",
) -> BudgetSummary:
    return BudgetSummary(
        id=budget_id,
        name=name,
        last_modified_on=last_modified,
        first_month=first_month,
        last_month=last_month,
    )


class TestListBudgets:
    @pytest.mark.anyio
    async def test_returns_formatted_budgets(self) -> None:
        budgets = [
            _make_budget("My Budget", _VALID_UUID),
            _make_budget(
                "Shared Budget", _VALID_UUID_2,
                first_month="2025-06-01",
                last_month="2026-03-01",
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_budgets.return_value = budgets
        mock_client.rate_limit_remaining = None

        result = await list_budgets(ctx=_mock_ctx(mock_client))

        assert "My Budget" in result
        assert _VALID_UUID in result
        assert "Jan 2024" in result
        assert "Feb 2026" in result
        assert "Shared Budget" in result
        assert _VALID_UUID_2 in result
        assert "Jun 2025" in result
        assert "Mar 2026" in result

    @pytest.mark.anyio
    async def test_single_budget(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budgets.return_value = [
            _make_budget()
        ]
        mock_client.rate_limit_remaining = None

        result = await list_budgets(ctx=_mock_ctx(mock_client))

        assert "My Budget" in result
        assert "ID:" in result

    @pytest.mark.anyio
    async def test_no_budgets(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budgets.return_value = []

        result = await list_budgets(ctx=_mock_ctx(mock_client))

        assert "No budgets found" in result

    @pytest.mark.anyio
    async def test_includes_last_modified_date(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budgets.return_value = [
            _make_budget(
                last_modified="2026-02-15T08:30:00+00:00"
            )
        ]
        mock_client.rate_limit_remaining = None

        result = await list_budgets(ctx=_mock_ctx(mock_client))

        assert "2026-02-15" in result

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budgets.side_effect = YNABError(
            401, "Invalid access token"
        )

        result = await list_budgets(ctx=_mock_ctx(mock_client))

        assert "Invalid access token" in result

    @pytest.mark.anyio
    async def test_unexpected_error_caught(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budgets.side_effect = (
            RuntimeError("something broke")
        )

        result = await list_budgets(ctx=_mock_ctx(mock_client))

        assert "Unexpected error" in result
        assert "RuntimeError" in result


class TestListAccounts:
    @pytest.mark.anyio
    async def test_returns_formatted_accounts(self) -> None:
        accounts = [
            _make_account(
                "Checking", "checking",
                Decimal("1500.50"), Decimal("1400"),
            ),
            _make_account(
                "Savings", "savings",
                Decimal("10000"), Decimal("10000"),
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = accounts

        result = await list_accounts(ctx=_mock_ctx(mock_client))

        assert "Checking" in result
        assert "$1,500.50" in result
        assert "Savings" in result
        assert "$10,000.00" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id_returns_error(
        self,
    ) -> None:
        result = await list_accounts(
            ctx=_mock_ctx(), budget_id="../../evil"
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_includes_account_ids(self) -> None:
        accounts = [
            Account(
                id=_VALID_UUID,
                name="Checking",
                type="checking",
                balance=Decimal("100"),
                cleared_balance=Decimal("100"),
                closed=False,
                deleted=False,
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = accounts

        result = await list_accounts(ctx=_mock_ctx(mock_client))

        assert _VALID_UUID in result
        assert "ID:" in result

    @pytest.mark.anyio
    async def test_negative_balance_formatting(self) -> None:
        accounts = [
            _make_account(
                "Credit Card", "creditCard",
                Decimal("-1500"), Decimal("-1200"),
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = accounts

        result = await list_accounts(ctx=_mock_ctx(mock_client))

        assert "-$1,500.00" in result
        assert "-$1,200.00" in result

    @pytest.mark.anyio
    async def test_passes_budget_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = []

        await list_accounts(
            ctx=_mock_ctx(mock_client), budget_id=_VALID_UUID
        )

        mock_client.get_accounts.assert_called_once_with(
            _VALID_UUID
        )

    @pytest.mark.anyio
    async def test_default_budget_uses_last_used(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = []

        await list_accounts(ctx=_mock_ctx(mock_client))

        mock_client.get_accounts.assert_called_once_with(
            "last-used"
        )

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_accounts.side_effect = YNABError(
            401, "Invalid access token"
        )

        result = await list_accounts(
            ctx=_mock_ctx(mock_client)
        )

        assert "Invalid access token" in result

    @pytest.mark.anyio
    async def test_no_accounts(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = []

        result = await list_accounts(
            ctx=_mock_ctx(mock_client)
        )

        assert "No open accounts found" in result

    @pytest.mark.anyio
    async def test_unexpected_error_caught(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_accounts.side_effect = (
            RuntimeError("something broke")
        )

        result = await list_accounts(
            ctx=_mock_ctx(mock_client)
        )

        assert "Unexpected error" in result


class TestListCategories:
    @pytest.mark.anyio
    async def test_invalid_budget_id_returns_error(
        self,
    ) -> None:
        result = await list_categories(
            ctx=_mock_ctx(), budget_id="../../evil"
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_returns_groups_with_categories(self) -> None:
        groups = [
            CategoryGroup(
                id="group-1",
                name="Monthly Bills",
                deleted=False,
                categories=[
                    Category(
                        id=_VALID_UUID,
                        name="Rent",
                        budgeted=Decimal("1500"),
                        activity=Decimal("-1500"),
                        balance=Decimal("0"),
                        deleted=False,
                    ),
                ],
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_categories.return_value = groups

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "Monthly Bills" in result
        assert "Rent" in result
        assert _VALID_UUID in result
        assert "ID:" in result
        assert "Group ID: `group-1`" in result

    @pytest.mark.anyio
    async def test_skips_empty_groups(self) -> None:
        groups = [
            CategoryGroup(
                id="group-1",
                name="Empty Group",
                deleted=False,
                categories=[],
            ),
            CategoryGroup(
                id="group-2",
                name="Has Stuff",
                deleted=False,
                categories=[
                    Category(
                        id=_VALID_UUID,
                        name="Groceries",
                        budgeted=Decimal("500"),
                        activity=Decimal("-200"),
                        balance=Decimal("300"),
                        deleted=False,
                    ),
                ],
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_categories.return_value = groups

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "Empty Group" not in result
        assert "Has Stuff" in result
        assert "Groceries" in result

    @pytest.mark.anyio
    async def test_no_categories(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_categories.return_value = []

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "No categories found" in result

    @pytest.mark.anyio
    async def test_passes_budget_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_categories.return_value = []

        await list_categories(
            ctx=_mock_ctx(mock_client),
            budget_id=_VALID_UUID,
        )

        mock_client.get_categories.assert_called_once_with(
            _VALID_UUID
        )

    @pytest.mark.anyio
    async def test_default_budget_uses_last_used(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_categories.return_value = []

        await list_categories(ctx=_mock_ctx(mock_client))

        mock_client.get_categories.assert_called_once_with(
            "last-used"
        )

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_categories.side_effect = YNABError(
            401, "Invalid access token"
        )

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "Invalid access token" in result

    @pytest.mark.anyio
    async def test_unexpected_error_caught(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_categories.side_effect = (
            RuntimeError("something broke")
        )

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "Unexpected error" in result


class TestListPayees:
    @pytest.mark.anyio
    async def test_invalid_budget_id_returns_error(
        self,
    ) -> None:
        result = await list_payees(
            ctx=_mock_ctx(), budget_id="../../evil"
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_returns_payees_with_ids(self) -> None:
        payees = [
            Payee(id=_VALID_UUID, name="Costco", deleted=False),
            Payee(
                id=_VALID_UUID_2, name="Target", deleted=False
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_payees.return_value = payees

        result = await list_payees(
            ctx=_mock_ctx(mock_client)
        )

        assert "Costco" in result
        assert _VALID_UUID in result
        assert "Target" in result
        assert _VALID_UUID_2 in result
        assert "ID:" in result

    @pytest.mark.anyio
    async def test_no_payees(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payees.return_value = []

        result = await list_payees(
            ctx=_mock_ctx(mock_client)
        )

        assert "No payees found" in result

    @pytest.mark.anyio
    async def test_passes_budget_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payees.return_value = []

        await list_payees(
            ctx=_mock_ctx(mock_client),
            budget_id=_VALID_UUID,
        )

        mock_client.get_payees.assert_called_once_with(
            _VALID_UUID
        )

    @pytest.mark.anyio
    async def test_default_budget_uses_last_used(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payees.return_value = []

        await list_payees(ctx=_mock_ctx(mock_client))

        mock_client.get_payees.assert_called_once_with(
            "last-used"
        )

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payees.side_effect = YNABError(
            401, "Invalid access token"
        )

        result = await list_payees(
            ctx=_mock_ctx(mock_client)
        )

        assert "Invalid access token" in result

    @pytest.mark.anyio
    async def test_unexpected_error_caught(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payees.side_effect = (
            RuntimeError("something broke")
        )

        result = await list_payees(
            ctx=_mock_ctx(mock_client)
        )

        assert "Unexpected error" in result


def _make_month_summary(
    month: str = "2026-02-01",
    income: Decimal = Decimal("5000"),
    budgeted: Decimal = Decimal("4000"),
    activity: Decimal = Decimal("-3500"),
    to_be_budgeted: Decimal = Decimal("1000"),
    age_of_money: int | None = 45,
    note: str | None = None,
) -> MonthSummary:
    return MonthSummary(
        month=month,
        note=note,
        income=income,
        budgeted=budgeted,
        activity=activity,
        to_be_budgeted=to_be_budgeted,
        age_of_money=age_of_money,
        deleted=False,
    )


def _make_month_detail(
    month: str = "2026-02-01",
    categories: list[Category] | None = None,
    age_of_money: int | None = 45,
    note: str | None = None,
) -> MonthDetail:
    return MonthDetail(
        month=month,
        note=note,
        income=Decimal("5000"),
        budgeted=Decimal("4000"),
        activity=Decimal("-3500"),
        to_be_budgeted=Decimal("1000"),
        age_of_money=age_of_money,
        deleted=False,
        categories=categories or [],
    )


class TestListMonths:
    @pytest.mark.anyio
    async def test_returns_formatted_months(self) -> None:
        months = [
            _make_month_summary("2026-01-01"),
            _make_month_summary(
                "2026-02-01", age_of_money=50,
                note="Good month",
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_months.return_value = months

        result = await list_months(ctx=_mock_ctx(mock_client))

        assert "Jan 2026" in result
        assert "Feb 2026" in result
        assert "$5,000.00" in result
        assert "$4,000.00" in result
        assert "-$3,500.00" in result
        assert "$1,000.00" in result
        assert "45 days" in result
        assert "Good month" in result

    @pytest.mark.anyio
    async def test_empty_months(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_months.return_value = []

        result = await list_months(ctx=_mock_ctx(mock_client))

        assert "No months found" in result

    @pytest.mark.anyio
    async def test_age_of_money_none(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_months.return_value = [
            _make_month_summary(age_of_money=None)
        ]

        result = await list_months(ctx=_mock_ctx(mock_client))

        assert "N/A" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await list_months(
            ctx=_mock_ctx(), budget_id="bad"
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_months.side_effect = YNABError(
            500, "Server error"
        )

        result = await list_months(
            ctx=_mock_ctx(mock_client)
        )

        assert "Server error" in result

    @pytest.mark.anyio
    async def test_unexpected_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_months.side_effect = RuntimeError(
            "boom"
        )

        result = await list_months(
            ctx=_mock_ctx(mock_client)
        )

        assert "Unexpected error" in result

    @pytest.mark.anyio
    async def test_uses_budget_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_months.return_value = []

        await list_months(
            ctx=_mock_ctx(mock_client),
            budget_id=_VALID_UUID,
        )

        mock_client.get_months.assert_called_once_with(
            _VALID_UUID
        )

    @pytest.mark.anyio
    async def test_defaults_to_last_used(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_months.return_value = []

        await list_months(ctx=_mock_ctx(mock_client))

        mock_client.get_months.assert_called_once_with(
            "last-used"
        )


class TestGetMonth:
    @pytest.mark.anyio
    async def test_returns_formatted_detail(self) -> None:
        cats = [
            _make_category("Groceries"),
            _make_category("Rent"),
        ]
        detail = _make_month_detail(categories=cats)
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )

        assert "Feb 2026" in result
        assert "$5,000.00" in result
        assert "Groceries" in result
        assert "Rent" in result
        assert "Categories" in result

    @pytest.mark.anyio
    async def test_shows_target_underfunding_and_cadence(
        self,
    ) -> None:
        category = _make_category("Pihl's Computer")
        category.goal_under_funded = Decimal("1500")
        category.goal_cadence = 1
        category.goal_cadence_frequency = 1
        detail = _make_month_detail(categories=[category])
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-09-01"
        )

        assert "Underfunded $1,500.00" in result
        assert "Target cadence Monthly (1)" in result
        assert "frequency 1" in result

    @pytest.mark.anyio
    async def test_current_month(self) -> None:
        detail = _make_month_detail()
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="current"
        )

        mock_client.get_month.assert_called_once_with(
            "last-used", month="current"
        )
        assert "Feb 2026" in result

    @pytest.mark.anyio
    async def test_no_categories(self) -> None:
        detail = _make_month_detail(categories=[])
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )

        assert "Categories" not in result
        assert "$5,000.00" in result

    @pytest.mark.anyio
    async def test_filters_deleted_categories(self) -> None:
        cats = [
            _make_category("Groceries"),
            Category(
                id="cat-del",
                name="Deleted Cat",
                budgeted=Decimal("0"),
                activity=Decimal("0"),
                balance=Decimal("0"),
                deleted=True,
            ),
        ]
        detail = _make_month_detail(categories=cats)
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )

        assert "Groceries" in result
        assert "Deleted Cat" not in result

    @pytest.mark.anyio
    async def test_age_of_money_none(self) -> None:
        detail = _make_month_detail(age_of_money=None)
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )

        assert "N/A" in result

    @pytest.mark.anyio
    async def test_with_note(self) -> None:
        detail = _make_month_detail(note="Budget tight")
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )

        assert "Budget tight" in result

    @pytest.mark.anyio
    async def test_invalid_month_format(self) -> None:
        result = await get_month(
            ctx=_mock_ctx(), month="feb-2026"
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await get_month(
            ctx=_mock_ctx(), month="2026-02-01",
            budget_id="bad",
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_month.side_effect = YNABError(
            404, "Month not found"
        )
        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )
        assert "Month not found" in result

    @pytest.mark.anyio
    async def test_unexpected_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_month.side_effect = RuntimeError(
            "boom"
        )
        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )
        assert "Unexpected error" in result

    @pytest.mark.anyio
    async def test_uses_budget_id(self) -> None:
        detail = _make_month_detail()
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = None

        await get_month(
            ctx=_mock_ctx(mock_client),
            month="2026-02-01",
            budget_id=_VALID_UUID,
        )

        mock_client.get_month.assert_called_once_with(
            _VALID_UUID, month="2026-02-01"
        )

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        detail = _make_month_detail()
        mock_client = AsyncMock()
        mock_client.get_month.return_value = detail
        mock_client.rate_limit_remaining = 10

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-02-01"
        )

        assert "Rate limit" in result


class TestListTransactions:
    @pytest.mark.anyio
    async def test_returns_formatted_list(self) -> None:
        txns = [
            _make_transaction("txn-1", Decimal("-42.50")),
            _make_transaction(
                "txn-2", Decimal("100.00"),
                payee_name="Employer",
                category_name="Income",
                memo="Paycheck",
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = txns
        mock_client.rate_limit_remaining = None

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "2 found" in result
        assert "txn-1" in result
        assert "txn-2" in result
        assert "Costco" in result
        assert "Employer" in result
        assert "Total:" in result

    @pytest.mark.anyio
    async def test_no_transactions(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = []

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "No transactions found" in result

    @pytest.mark.anyio
    async def test_invalid_since_date(self) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(), since_date="bad-date"
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_invalid_account_id(self) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(),
            since_date="2026-02-01",
            account_id="bad-id",
        )
        assert "Invalid account_id" in result

    @pytest.mark.anyio
    async def test_invalid_category_id(self) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(),
            since_date="2026-02-01",
            category_id="bad-id",
        )
        assert "Invalid category_id" in result

    @pytest.mark.anyio
    async def test_invalid_payee_id(self) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(),
            since_date="2026-02-01",
            payee_id="bad-id",
        )
        assert "Invalid payee_id" in result

    @pytest.mark.anyio
    async def test_invalid_type(self) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(),
            since_date="2026-02-01",
            type="invalid",
        )
        assert "Invalid type" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(),
            since_date="2026-02-01",
            budget_id="../../evil",
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_multiple_filters_returns_error(
        self,
    ) -> None:
        result = await list_transactions(
            ctx=_mock_ctx(),
            since_date="2026-02-01",
            account_id=_VALID_UUID,
            category_id=_VALID_UUID_2,
        )
        assert "Only one of" in result

    @pytest.mark.anyio
    async def test_passes_account_filter(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = []

        await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
            account_id=_VALID_UUID,
        )

        mock_client.get_transactions.assert_called_once_with(
            "last-used",
            since_date="2026-02-01",
            account_id=_VALID_UUID,
            category_id=None,
            payee_id=None,
            type=None,
        )

    @pytest.mark.anyio
    async def test_passes_type_filter(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = []

        await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
            type="unapproved",
        )

        call_kwargs = (
            mock_client.get_transactions.call_args[1]
        )
        assert call_kwargs["type"] == "unapproved"

    @pytest.mark.anyio
    async def test_total_in_output(self) -> None:
        txns = [
            _make_transaction("t1", Decimal("-42.50")),
            _make_transaction("t2", Decimal("-7.50")),
        ]
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = txns
        mock_client.rate_limit_remaining = None

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "-$50.00" in result
        assert "2 transactions" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        txns = [_make_transaction()]
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = txns
        mock_client.rate_limit_remaining = 10

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "Rate limit" in result
        assert "10/200" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transactions.side_effect = (
            YNABError(401, "Invalid access token")
        )

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "Invalid access token" in result

    @pytest.mark.anyio
    async def test_unexpected_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transactions.side_effect = (
            RuntimeError("boom")
        )

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "Unexpected error" in result

    @pytest.mark.anyio
    async def test_transaction_ids_in_output(self) -> None:
        txns = [_make_transaction("txn-abc-123")]
        mock_client = AsyncMock()
        mock_client.get_transactions.return_value = txns
        mock_client.rate_limit_remaining = None

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-02-01",
        )

        assert "txn-abc-123" in result
        assert "ID:" in result


class TestCreateTransaction:
    @pytest.mark.anyio
    async def test_creates_and_returns_confirmation(
        self,
    ) -> None:
        txn = _make_transaction()
        mock_client = AsyncMock()
        mock_client.create_transaction.return_value = txn
        mock_client.rate_limit_remaining = None

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
            payee_name="Costco",
        )

        assert "txn-1" in result
        assert "Costco" in result
        write = mock_client.create_transaction.call_args.args[1]
        assert write.payee_name == "Costco"
        assert write.payee_id is None

    @pytest.mark.anyio
    async def test_creates_with_transfer_payee_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_transaction.return_value = _make_transaction()
        mock_client.rate_limit_remaining = None

        await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-973.51",
            date="2026-08-07",
            payee_id=_VALID_UUID_2,
        )

        write = mock_client.create_transaction.call_args.args[1]
        assert write.payee_id == _VALID_UUID_2
        assert write.payee_name is None
        payload = write.model_dump(exclude_none=True)
        assert payload["payee_id"] == _VALID_UUID_2
        assert "payee_name" not in payload

    @pytest.mark.anyio
    async def test_invalid_payee_id_skips_api(self) -> None:
        mock_client = AsyncMock()

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-973.51",
            date="2026-08-07",
            payee_id="bad-id",
        )

        assert "Invalid payee_id" in result
        mock_client.create_transaction.assert_not_awaited()

    @pytest.mark.anyio
    async def test_rejects_payee_id_with_name(self) -> None:
        mock_client = AsyncMock()

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-973.51",
            date="2026-08-07",
            payee_name="Transfer",
            payee_id=_VALID_UUID_2,
        )

        assert "mutually exclusive" in result
        mock_client.create_transaction.assert_not_awaited()

    @pytest.mark.anyio
    async def test_invalid_amount_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="not-a-number",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_nan_amount_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="NaN",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_empty_amount_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_infinity_amount_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="Infinity",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_invalid_date_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="not-a-date",
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_impossible_date_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-13-40",
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_invalid_account_id_returns_error(
        self,
    ) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id="bad-id",
            amount="-42.50",
            date="2026-02-25",
        )
        assert "Invalid account_id" in result

    @pytest.mark.anyio
    async def test_invalid_category_id_returns_error(
        self,
    ) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
            category_id="bad-id",
        )
        assert "Invalid category_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id_returns_error(
        self,
    ) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
            budget_id="../../evil",
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_invalid_cleared_returns_error(
        self,
    ) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
            cleared="invalid",
        )
        assert "Invalid cleared" in result

    @pytest.mark.anyio
    async def test_dry_run_returns_preview(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
            payee_name="Costco",
            memo="Groceries",
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "-$42.50" in result
        assert "-42500 milliunits" in result
        assert "Costco" in result
        assert "Groceries" in result

    @pytest.mark.anyio
    async def test_dry_run_shows_payee_id(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-973.51",
            date="2026-08-07",
            payee_id=_VALID_UUID_2,
            dry_run=True,
        )

        assert "[DRY RUN]" in result
        assert f"Payee ID: {_VALID_UUID_2}" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning_shown(self) -> None:
        txn = _make_transaction()
        mock_client = AsyncMock()
        mock_client.create_transaction.return_value = txn
        mock_client.rate_limit_remaining = 15

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
        )

        assert "Rate limit" in result
        assert "15/200" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning_hidden(self) -> None:
        txn = _make_transaction()
        mock_client = AsyncMock()
        mock_client.create_transaction.return_value = txn
        mock_client.rate_limit_remaining = 150

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
        )

        assert "Rate limit" not in result

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_transaction.side_effect = (
            YNABError(400, "Bad request")
        )

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
        )

        assert "Bad request" in result


class TestCreateTransactions:
    @pytest.mark.anyio
    async def test_bulk_create(self) -> None:
        bulk = BulkCreateResponse(
            transaction_ids=["txn-1", "txn-2"],
            duplicate_import_ids=[],
        )
        mock_client = AsyncMock()
        mock_client.create_transactions.return_value = bulk
        mock_client.rate_limit_remaining = None

        result = await create_transactions(
            ctx=_mock_ctx(mock_client),
            transactions_json=(
                f'[{{"account_id": "{_VALID_UUID}",'
                f' "amount": "-42.50",'
                f' "date": "2026-02-25",'
                f' "payee_name": "Costco"}},'
                f'{{"account_id": "{_VALID_UUID}",'
                f' "amount": "-15.00",'
                f' "date": "2026-02-25"}}]'
            ),
        )

        assert "Created 2 transactions" in result
        assert "txn-1" in result

    @pytest.mark.anyio
    async def test_bulk_create_with_transfer_payee_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_transactions.return_value = BulkCreateResponse(
            transaction_ids=["txn-1"],
            duplicate_import_ids=[],
        )
        mock_client.rate_limit_remaining = None

        await create_transactions(
            ctx=_mock_ctx(mock_client),
            transactions_json=json.dumps(
                [
                    {
                        "account_id": _VALID_UUID,
                        "amount": "-973.51",
                        "date": "2026-08-07",
                        "payee_id": _VALID_UUID_2,
                    }
                ]
            ),
        )

        writes = mock_client.create_transactions.call_args.args[1]
        assert writes[0].payee_id == _VALID_UUID_2
        assert writes[0].payee_name is None

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("payee_fields", "message"),
        [
            ({"payee_id": "bad-id"}, "Invalid transaction 0 payee_id"),
            (
                {
                    "payee_id": _VALID_UUID_2,
                    "payee_name": "Transfer",
                },
                "mutually exclusive",
            ),
        ],
    )
    async def test_invalid_bulk_payee_skips_api(
        self,
        payee_fields: dict[str, str],
        message: str,
    ) -> None:
        mock_client = AsyncMock()
        transaction = {
            "account_id": _VALID_UUID,
            "amount": "-973.51",
            "date": "2026-08-07",
            **payee_fields,
        }

        result = await create_transactions(
            ctx=_mock_ctx(mock_client),
            transactions_json=json.dumps([transaction]),
        )

        assert message in result
        mock_client.create_transactions.assert_not_awaited()

    @pytest.mark.anyio
    async def test_invalid_json(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json="not json",
        )
        assert "Invalid JSON" in result

    @pytest.mark.anyio
    async def test_empty_array(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json="[]",
        )
        assert "non-empty" in result

    @pytest.mark.anyio
    async def test_not_array(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json='{"not": "array"}',
        )
        assert "non-empty JSON array" in result

    @pytest.mark.anyio
    async def test_invalid_amount_in_bulk(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json=(
                f'[{{"account_id": "{_VALID_UUID}",'
                f' "amount": "bad",'
                f' "date": "2026-02-25"}}]'
            ),
        )
        assert "Transaction 0" in result
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json=(
                f'[{{"account_id": "{_VALID_UUID}",'
                f' "amount": "-42.50",'
                f' "date": "2026-02-25",'
                f' "payee_name": "Costco"}}]'
            ),
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "-$42.50" in result
        assert "Costco" in result

    @pytest.mark.anyio
    async def test_dry_run_preview_shows_payee_id(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json=json.dumps(
                [
                    {
                        "account_id": _VALID_UUID,
                        "amount": "-973.51",
                        "date": "2026-08-07",
                        "payee_id": _VALID_UUID_2,
                    }
                ]
            ),
            dry_run=True,
        )

        assert "[DRY RUN]" in result
        assert f"payee ID {_VALID_UUID_2}" in result

    @pytest.mark.anyio
    async def test_non_string_account_id(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json=(
                '[{"account_id": 123,'
                ' "amount": "-42.50",'
                ' "date": "2026-02-25"}]'
            ),
        )
        assert "Invalid" in result
        assert "account_id" in result

    @pytest.mark.anyio
    async def test_non_string_category_id(self) -> None:
        result = await create_transactions(
            ctx=_mock_ctx(),
            transactions_json=(
                f'[{{"account_id": "{_VALID_UUID}",'
                f' "amount": "-42.50",'
                f' "date": "2026-02-25",'
                f' "category_id": 456}}]'
            ),
        )
        assert "Invalid" in result
        assert "category_id" in result

    @pytest.mark.anyio
    async def test_duplicates_reported(self) -> None:
        bulk = BulkCreateResponse(
            transaction_ids=["txn-1"],
            duplicate_import_ids=["dup-1"],
        )
        mock_client = AsyncMock()
        mock_client.create_transactions.return_value = bulk
        mock_client.rate_limit_remaining = None

        result = await create_transactions(
            ctx=_mock_ctx(mock_client),
            transactions_json=(
                f'[{{"account_id": "{_VALID_UUID}",'
                f' "amount": "-10.00",'
                f' "date": "2026-02-25"}}]'
            ),
        )

        assert "Duplicates skipped: 1" in result


class TestUpdateTransaction:
    @pytest.mark.anyio
    async def test_updates_and_returns_confirmation(
        self,
    ) -> None:
        txn = _make_transaction(memo="Updated memo")
        mock_client = AsyncMock()
        mock_client.update_transaction.return_value = txn
        mock_client.rate_limit_remaining = None

        result = await update_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
            memo="Updated memo",
        )

        assert "Updated transaction" in result
        assert "Updated memo" in result

    @pytest.mark.anyio
    async def test_updates_transfer_payee_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_transaction.return_value = _make_transaction()
        mock_client.rate_limit_remaining = None

        await update_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
            payee_id=_VALID_UUID_2,
        )

        update = mock_client.update_transaction.call_args.args[1]
        assert update.payee_id == _VALID_UUID_2
        assert update.payee_name is None

    @pytest.mark.anyio
    async def test_invalid_payee_id_skips_update(self) -> None:
        mock_client = AsyncMock()

        result = await update_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
            payee_id="bad-id",
        )

        assert "Invalid payee_id" in result
        mock_client.update_transaction.assert_not_awaited()

    @pytest.mark.anyio
    async def test_rejects_payee_id_with_name(self) -> None:
        mock_client = AsyncMock()

        result = await update_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
            payee_name="Transfer",
            payee_id=_VALID_UUID_2,
        )

        assert "mutually exclusive" in result
        mock_client.update_transaction.assert_not_awaited()

    @pytest.mark.anyio
    async def test_no_fields_returns_error(self) -> None:
        result = await update_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
        )
        assert "No fields to update" in result

    @pytest.mark.anyio
    async def test_invalid_transaction_id(self) -> None:
        result = await update_transaction(
            ctx=_mock_ctx(),
            transaction_id="bad-id",
            memo="test",
        )
        assert "Invalid transaction_id" in result

    @pytest.mark.anyio
    async def test_invalid_amount(self) -> None:
        result = await update_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
            amount="not-a-number",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_invalid_date(self) -> None:
        result = await update_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
            date="bad-date",
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        result = await update_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
            amount="-50.00",
            memo="Changed",
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "-$50.00" in result
        assert "Changed" in result

    @pytest.mark.anyio
    async def test_dry_run_preview_shows_payee_id(self) -> None:
        result = await update_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
            payee_id=_VALID_UUID_2,
            dry_run=True,
        )

        assert "[DRY RUN]" in result
        assert f"Payee ID: {_VALID_UUID_2}" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        txn = _make_transaction()
        mock_client = AsyncMock()
        mock_client.update_transaction.return_value = txn
        mock_client.rate_limit_remaining = 10

        result = await update_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
            memo="test",
        )

        assert "Rate limit" in result
        assert "10/200" in result


class TestDeleteTransaction:
    @pytest.mark.anyio
    async def test_deletes_and_returns_confirmation(
        self,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None

        result = await delete_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
        )

        assert "Deleted transaction" in result
        assert _VALID_UUID in result

    @pytest.mark.anyio
    async def test_invalid_transaction_id(self) -> None:
        result = await delete_transaction(
            ctx=_mock_ctx(),
            transaction_id="bad-id",
        )
        assert "Invalid transaction_id" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        result = await delete_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert _VALID_UUID in result

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        mock_client = AsyncMock()
        mock_client.delete_transaction.side_effect = (
            YNABError(404, "Transaction not found")
        )

        result = await delete_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
        )

        assert "Transaction not found" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = 5

        result = await delete_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
        )

        assert "Rate limit" in result
        assert "5/200" in result


def _make_category(
    name: str = "Groceries",
    budgeted: Decimal = Decimal("500.00"),
    activity: Decimal = Decimal("-200.00"),
    balance: Decimal = Decimal("300.00"),
    note: str | None = None,
    hidden: bool = False,
) -> Category:
    return Category(
        id=_VALID_UUID,
        name=name,
        category_group_id=_VALID_UUID_2,
        budgeted=budgeted,
        activity=activity,
        balance=balance,
        note=note,
        hidden=hidden,
        deleted=False,
    )


class TestUpdateCategoryBudget:
    @pytest.mark.anyio
    async def test_updates_and_returns_confirmation(
        self,
    ) -> None:
        cat = _make_category(budgeted=Decimal("500.00"))
        mock_client = AsyncMock()
        mock_client.update_category_budget.return_value = cat
        mock_client.rate_limit_remaining = None

        result = await update_category_budget(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="500.00",
        )

        assert "Updated budget" in result
        assert "Groceries" in result
        assert "$500.00" in result
        assert "Mar 2026" in result

    @pytest.mark.anyio
    async def test_invalid_category_id(self) -> None:
        result = await update_category_budget(
            ctx=_mock_ctx(),
            category_id="bad-id",
            month="2026-03-01",
            amount="500.00",
        )
        assert "Invalid category_id" in result

    @pytest.mark.anyio
    async def test_invalid_month(self) -> None:
        result = await update_category_budget(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            month="bad-date",
            amount="500.00",
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_invalid_amount(self) -> None:
        result = await update_category_budget(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="not-a-number",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await update_category_budget(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="500.00",
            budget_id="../../evil",
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        result = await update_category_budget(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="500.00",
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "$500.00" in result
        assert "500000 milliunits" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        cat = _make_category()
        mock_client = AsyncMock()
        mock_client.update_category_budget.return_value = cat
        mock_client.rate_limit_remaining = 10

        result = await update_category_budget(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="500.00",
        )

        assert "Rate limit" in result
        assert "10/200" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category_budget.side_effect = (
            YNABError(404, "Category not found")
        )

        result = await update_category_budget(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="500.00",
        )

        assert "Category not found" in result

    @pytest.mark.anyio
    async def test_unexpected_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category_budget.side_effect = (
            RuntimeError("boom")
        )

        result = await update_category_budget(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            month="2026-03-01",
            amount="500.00",
        )

        assert "Unexpected error" in result
        assert "RuntimeError" in result


class TestUpdateCategory:
    def test_schema_does_not_expose_hidden(self) -> None:
        assert "hidden" not in inspect.signature(
            update_category
        ).parameters

    @pytest.mark.anyio
    async def test_updates_name_and_returns_confirmation(
        self,
    ) -> None:
        cat = _make_category(name="Restaurants")
        mock_client = AsyncMock()
        mock_client.update_category.return_value = cat
        mock_client.rate_limit_remaining = None

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            name="Restaurants",
        )

        assert "Updated category" in result
        assert "Restaurants" in result
        assert 'name' in result

    @pytest.mark.anyio
    async def test_updates_multiple_fields(self) -> None:
        cat = _make_category(
            name="Restaurants", note="Eating out"
        )
        mock_client = AsyncMock()
        mock_client.update_category.return_value = cat
        mock_client.rate_limit_remaining = None

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            name="Restaurants",
            note="Eating out",
        )

        assert "Restaurants" in result
        assert "Eating out" in result

    @pytest.mark.anyio
    async def test_updates_target_with_date(self) -> None:
        cat = _make_category()
        mock_client = AsyncMock()
        mock_client.update_category.return_value = cat
        mock_client.rate_limit_remaining = None

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            target_amount="2500.00",
            target_date="2026-10-01",
            target_needs_whole_amount=True,
        )

        assert "$2,500.00" in result
        assert "2026-10-01" in result
        update = mock_client.update_category.call_args.args[2]
        assert update.goal_target == 2500000
        assert update.goal_target_date == "2026-10-01"
        assert update.goal_needs_whole_amount is True

    @pytest.mark.anyio
    async def test_updates_target_with_frequency(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category.return_value = _make_category()
        mock_client.rate_limit_remaining = None

        await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            target_amount="100.00",
            target_frequency="monthly",
        )

        update = mock_client.update_category.call_args.args[2]
        assert update.goal_target == 100000
        assert update.goal_frequency == "monthly"

    @pytest.mark.anyio
    async def test_updates_target_date_without_amount(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category.return_value = _make_category()
        mock_client.rate_limit_remaining = None

        await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            target_date="2026-11-01",
        )

        update = mock_client.update_category.call_args.args[2]
        assert update.goal_target is None
        assert update.goal_target_date == "2026-11-01"

    @pytest.mark.anyio
    async def test_updates_whole_amount_without_amount(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category.return_value = _make_category()
        mock_client.rate_limit_remaining = None

        await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            target_needs_whole_amount=False,
        )

        update = mock_client.update_category.call_args.args[2]
        assert update.goal_target is None
        assert update.goal_needs_whole_amount is False

    @pytest.mark.anyio
    async def test_moves_category_group(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category.return_value = _make_category()
        mock_client.rate_limit_remaining = None

        await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            category_group_id=_VALID_UUID_2,
        )

        update = mock_client.update_category.call_args.args[2]
        assert update.category_group_id == _VALID_UUID_2

    @pytest.mark.anyio
    async def test_no_fields_returns_error(self) -> None:
        result = await update_category(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
        )
        assert "No fields to update" in result

    @pytest.mark.anyio
    async def test_invalid_category_id(self) -> None:
        result = await update_category(
            ctx=_mock_ctx(),
            category_id="bad-id",
            name="Test",
        )
        assert "Invalid category_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await update_category(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            name="Test",
            budget_id="../../evil",
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        mock_client = AsyncMock()
        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            name="Restaurants",
            note="Eating out",
            target_amount="2500",
            target_frequency="yearly",
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "Restaurants" in result
        assert "Eating out" in result
        assert "$2,500.00" in result
        assert "yearly" in result
        mock_client.update_category.assert_not_awaited()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"target_amount": "0"}, "greater than zero"),
            ({"target_amount": "-1"}, "greater than zero"),
            ({"target_amount": "1.0001"}, "decimal places"),
            (
                {"target_frequency": "monthly"},
                "target_amount is required",
            ),
            (
                {
                    "target_amount": "100",
                    "target_frequency": "daily",
                },
                "Invalid target_frequency",
            ),
            (
                {
                    "target_amount": "100",
                    "target_frequency": "monthly",
                    "target_date": "2026-10-01",
                },
                "cannot be combined",
            ),
            (
                {
                    "target_amount": "100",
                    "target_date": "2026-02-30",
                },
                "Invalid target_date",
            ),
        ],
    )
    async def test_invalid_target_skips_api(
        self, kwargs: dict[str, object], message: str
    ) -> None:
        mock_client = AsyncMock()

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            **kwargs,  # type: ignore[arg-type]
        )

        assert message in result
        mock_client.update_category.assert_not_awaited()

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        cat = _make_category()
        mock_client = AsyncMock()
        mock_client.update_category.return_value = cat
        mock_client.rate_limit_remaining = 10

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            name="Test",
        )

        assert "Rate limit" in result
        assert "10/200" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category.side_effect = (
            YNABError(404, "Category not found")
        )

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            name="Test",
        )

        assert "Category not found" in result

    @pytest.mark.anyio
    async def test_unexpected_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_category.side_effect = (
            RuntimeError("boom")
        )

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            name="Test",
        )

        assert "Unexpected error" in result
        assert "RuntimeError" in result


class TestClearCategoryTarget:
    @pytest.mark.anyio
    async def test_clears_target(self) -> None:
        mock_client = AsyncMock()
        mock_client.clear_category_target.return_value = _make_category(
            name="Pihl's Computer",
            budgeted=Decimal("0"),
            balance=Decimal("1500"),
        )
        mock_client.rate_limit_remaining = None

        result = await clear_category_target(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
        )

        mock_client.clear_category_target.assert_awaited_once_with(
            "last-used", _VALID_UUID
        )
        assert "Cleared target" in result
        assert "Pihl's Computer" in result
        assert "Assigned and available money were not changed" in result

    @pytest.mark.anyio
    async def test_dry_run_skips_api(self) -> None:
        mock_client = AsyncMock()

        result = await clear_category_target(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            dry_run=True,
        )

        assert "[DRY RUN]" in result
        assert "Assigned and available money" in result
        mock_client.clear_category_target.assert_not_awaited()

    @pytest.mark.anyio
    async def test_invalid_category_id_skips_api(self) -> None:
        mock_client = AsyncMock()

        result = await clear_category_target(
            ctx=_mock_ctx(mock_client), category_id="bad-id"
        )

        assert "Invalid category_id" in result
        mock_client.clear_category_target.assert_not_awaited()

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.clear_category_target.side_effect = YNABError(
            400, "Target could not be cleared"
        )

        result = await clear_category_target(
            ctx=_mock_ctx(mock_client), category_id=_VALID_UUID
        )

        assert "Target could not be cleared" in result


class TestCreateCategory:
    @pytest.mark.anyio
    async def test_creates_category_with_target(self) -> None:
        created = _make_category(name="Arizona Trip")
        mock_client = AsyncMock()
        mock_client.create_category.return_value = created
        mock_client.rate_limit_remaining = None

        result = await create_category(
            ctx=_mock_ctx(mock_client),
            category_group_id=_VALID_UUID_2,
            name="Arizona Trip",
            note="October",
            target_amount="2500.00",
            target_date="2026-10-01",
            target_needs_whole_amount=True,
        )

        assert "Created category Arizona Trip" in result
        assert _VALID_UUID in result
        category = mock_client.create_category.call_args.args[1]
        assert category.category_group_id == _VALID_UUID_2
        assert category.name == "Arizona Trip"
        assert category.note == "October"
        assert category.goal_target == 2500000
        assert category.goal_target_date == "2026-10-01"
        assert category.goal_needs_whole_amount is True

    @pytest.mark.anyio
    async def test_dry_run_skips_api(self) -> None:
        mock_client = AsyncMock()

        result = await create_category(
            ctx=_mock_ctx(mock_client),
            category_group_id=_VALID_UUID_2,
            name="Arizona Trip",
            target_amount="500",
            target_frequency="monthly",
            dry_run=True,
        )

        assert "[DRY RUN]" in result
        assert "Arizona Trip" in result
        assert "$500.00" in result
        assert "monthly" in result
        mock_client.create_category.assert_not_awaited()

    def test_schema_offers_target_frequency(self) -> None:
        assert (
            "target_frequency"
            in inspect.signature(create_category).parameters
        )

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"target_date": "2026-10-01"},
            {"target_needs_whole_amount": False},
        ],
    )
    async def test_dependent_target_field_requires_amount(
        self, kwargs: dict[str, object]
    ) -> None:
        mock_client = AsyncMock()

        result = await create_category(
            ctx=_mock_ctx(mock_client),
            category_group_id=_VALID_UUID_2,
            name="Trip",
            **kwargs,  # type: ignore[arg-type]
        )

        assert "target_amount is required" in result
        mock_client.create_category.assert_not_awaited()

    @pytest.mark.anyio
    async def test_invalid_group_skips_api(self) -> None:
        mock_client = AsyncMock()

        result = await create_category(
            ctx=_mock_ctx(mock_client),
            category_group_id="bad-id",
            name="Trip",
        )

        assert "Invalid category_group_id" in result
        mock_client.create_category.assert_not_awaited()

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_category.side_effect = YNABError(
            400, "Invalid category"
        )

        result = await create_category(
            ctx=_mock_ctx(mock_client),
            category_group_id=_VALID_UUID_2,
            name="Trip",
        )

        assert "Invalid category" in result


# --- Scheduled transaction test helpers ---


def _make_scheduled_txn(
    st_id: str = "st-1",
    amount: Decimal = Decimal("-150"),
    frequency: str = "monthly",
    payee_name: str | None = "Landlord",
    category_name: str | None = "Rent",
    memo: str | None = None,
    date_next: str = "2026-04-01",
    subtransactions: list[ScheduledSubTransaction] | None = None,
) -> ScheduledTransaction:
    return ScheduledTransaction(
        id=st_id,
        date_first="2026-03-01",
        date_next=date_next,
        frequency=frequency,
        amount=amount,
        memo=memo,
        flag_color=None,
        account_id=_VALID_UUID,
        account_name="Checking",
        payee_id=None,
        payee_name=payee_name,
        category_id=None,
        category_name=category_name,
        transfer_account_id=None,
        subtransactions=subtransactions or [],
        deleted=False,
    )


class TestListScheduledTransactions:
    @pytest.mark.anyio
    async def test_returns_formatted_list(self) -> None:
        scheduled = [
            _make_scheduled_txn(
                "st-1", date_next="2026-04-01"
            ),
            _make_scheduled_txn(
                "st-2",
                amount=Decimal("-50"),
                frequency="weekly",
                payee_name="Netflix",
                category_name="Entertainment",
                date_next="2026-03-05",
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_scheduled_transactions.return_value = (
            scheduled
        )

        result = await list_scheduled_transactions(
            ctx=_mock_ctx(mock_client)
        )

        assert "Landlord" in result
        assert "Netflix" in result
        assert "Monthly" in result
        assert "Weekly" in result
        assert "-$150.00" in result
        assert "st-1" in result

    @pytest.mark.anyio
    async def test_sorted_by_date_next(self) -> None:
        scheduled = [
            _make_scheduled_txn(
                "st-later", date_next="2026-06-01"
            ),
            _make_scheduled_txn(
                "st-sooner", date_next="2026-03-01"
            ),
        ]
        mock_client = AsyncMock()
        mock_client.get_scheduled_transactions.return_value = (
            scheduled
        )

        result = await list_scheduled_transactions(
            ctx=_mock_ctx(mock_client)
        )

        sooner_pos = result.index("st-sooner")
        later_pos = result.index("st-later")
        assert sooner_pos < later_pos

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_scheduled_transactions.return_value = []

        result = await list_scheduled_transactions(
            ctx=_mock_ctx(mock_client)
        )

        assert "No scheduled transactions" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await list_scheduled_transactions(
            ctx=_mock_ctx(), budget_id="bad"
        )
        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_scheduled_transactions.side_effect = (
            YNABError(500, "Server error")
        )

        result = await list_scheduled_transactions(
            ctx=_mock_ctx(mock_client)
        )

        assert "Server error" in result

    @pytest.mark.anyio
    async def test_with_memo(self) -> None:
        scheduled = [
            _make_scheduled_txn(memo="Auto-pay")
        ]
        mock_client = AsyncMock()
        mock_client.get_scheduled_transactions.return_value = (
            scheduled
        )

        result = await list_scheduled_transactions(
            ctx=_mock_ctx(mock_client)
        )

        assert "Auto-pay" in result


class TestGetScheduledTransaction:
    @pytest.mark.anyio
    async def test_returns_detail(self) -> None:
        st = _make_scheduled_txn(memo="Rent payment")
        mock_client = AsyncMock()
        mock_client.get_scheduled_transaction.return_value = st
        mock_client.rate_limit_remaining = None

        result = await get_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "-$150.00" in result
        assert "Monthly" in result
        assert "Landlord" in result
        assert "Rent" in result
        assert "Rent payment" in result

    @pytest.mark.anyio
    async def test_with_subtransactions(self) -> None:
        sub = ScheduledSubTransaction(
            id="sub-1",
            scheduled_transaction_id="st-1",
            amount=Decimal("-75"),
            memo="Half",
            payee_id=None,
            category_id=None,
            transfer_account_id=None,
            deleted=False,
        )
        st = _make_scheduled_txn(subtransactions=[sub])
        mock_client = AsyncMock()
        mock_client.get_scheduled_transaction.return_value = st
        mock_client.rate_limit_remaining = None

        result = await get_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "Subtransactions" in result
        assert "-$75.00" in result
        assert "Half" in result

    @pytest.mark.anyio
    async def test_filters_deleted_subtransactions(
        self,
    ) -> None:
        sub_active = ScheduledSubTransaction(
            id="sub-1",
            scheduled_transaction_id="st-1",
            amount=Decimal("-75"),
            memo="Active",
            payee_id=None,
            category_id=None,
            transfer_account_id=None,
            deleted=False,
        )
        sub_deleted = ScheduledSubTransaction(
            id="sub-2",
            scheduled_transaction_id="st-1",
            amount=Decimal("-25"),
            memo="Deleted",
            payee_id=None,
            category_id=None,
            transfer_account_id=None,
            deleted=True,
        )
        st = _make_scheduled_txn(
            subtransactions=[sub_active, sub_deleted]
        )
        mock_client = AsyncMock()
        mock_client.get_scheduled_transaction.return_value = st
        mock_client.rate_limit_remaining = None

        result = await get_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "Active" in result
        assert "Deleted" not in result

    @pytest.mark.anyio
    async def test_invalid_id(self) -> None:
        result = await get_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id="bad",
        )
        assert "Invalid scheduled_transaction_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_scheduled_transaction.side_effect = (
            YNABError(404, "Not found")
        )

        result = await get_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "Not found" in result


class TestCreateScheduledTransaction:
    @pytest.mark.anyio
    async def test_creates(self) -> None:
        created = _make_scheduled_txn("st-new")
        mock_client = AsyncMock()
        mock_client.create_scheduled_transaction.return_value = (
            created
        )
        mock_client.rate_limit_remaining = None

        result = await create_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-150.00",
            date="2026-03-01",
            frequency="monthly",
            payee_name="Landlord",
        )

        assert "st-new" in result
        assert "-$150.00" in result
        assert "Monthly" in result

    @pytest.mark.anyio
    async def test_dry_run(self) -> None:
        result = await create_scheduled_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-150.00",
            date="2026-03-01",
            frequency="monthly",
            payee_name="Landlord",
            dry_run=True,
        )

        assert "DRY RUN" in result
        assert "-$150.00" in result
        assert "Monthly" in result
        assert "Landlord" in result

    @pytest.mark.anyio
    async def test_invalid_frequency(self) -> None:
        result = await create_scheduled_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-150.00",
            date="2026-03-01",
            frequency="biweekly",
        )

        assert "Invalid frequency" in result

    @pytest.mark.anyio
    async def test_multiword_frequency_blocked_preflight(self) -> None:
        # YNAB's API rejects every multi-word camelCase frequency on
        # both create and update. Validate before round-tripping so the
        # caller gets an actionable error.
        result = await create_scheduled_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-150.00",
            date="2026-03-01",
            frequency="twiceAMonth",
        )

        assert "rejected by YNAB" in result
        assert "YNAB UI" in result

    @pytest.mark.anyio
    async def test_invalid_amount(self) -> None:
        result = await create_scheduled_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="not-a-number",
            date="2026-03-01",
            frequency="monthly",
        )

        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_invalid_date(self) -> None:
        result = await create_scheduled_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-150.00",
            date="march",
            frequency="monthly",
        )

        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_invalid_account_id(self) -> None:
        result = await create_scheduled_transaction(
            ctx=_mock_ctx(),
            account_id="bad",
            amount="-150.00",
            date="2026-03-01",
            frequency="monthly",
        )

        assert "Invalid account_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_scheduled_transaction.side_effect = (
            YNABError(400, "Bad request")
        )

        result = await create_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-150.00",
            date="2026-03-01",
            frequency="monthly",
        )

        assert "Bad request" in result


class TestUpdateScheduledTransaction:
    @pytest.mark.anyio
    async def test_updates(self) -> None:
        updated = _make_scheduled_txn()
        mock_client = AsyncMock()
        mock_client.update_scheduled_transaction.return_value = (
            updated
        )
        mock_client.rate_limit_remaining = None

        result = await update_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
            amount="-200.00",
        )

        assert "Updated" in result

    @pytest.mark.anyio
    async def test_dry_run(self) -> None:
        result = await update_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id=_VALID_UUID,
            amount="-200.00",
            frequency="weekly",
            dry_run=True,
        )

        assert "DRY RUN" in result
        assert "-$200.00" in result
        assert "Weekly" in result

    @pytest.mark.anyio
    async def test_no_fields(self) -> None:
        result = await update_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "No fields to update" in result

    @pytest.mark.anyio
    async def test_invalid_id(self) -> None:
        result = await update_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id="bad",
            amount="-100",
        )

        assert "Invalid scheduled_transaction_id" in result

    @pytest.mark.anyio
    async def test_invalid_frequency(self) -> None:
        result = await update_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id=_VALID_UUID,
            frequency="biweekly",
        )

        assert "Invalid frequency" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_scheduled_transaction.side_effect = (
            YNABError(404, "Not found")
        )

        result = await update_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
            amount="-200.00",
        )

        assert "Not found" in result


class TestDeleteScheduledTransaction:
    @pytest.mark.anyio
    async def test_deletes(self) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None

        result = await delete_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "Deleted" in result
        assert _VALID_UUID in result

    @pytest.mark.anyio
    async def test_dry_run(self) -> None:
        result = await delete_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id=_VALID_UUID,
            dry_run=True,
        )

        assert "DRY RUN" in result
        assert _VALID_UUID in result

    @pytest.mark.anyio
    async def test_invalid_id(self) -> None:
        result = await delete_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id="bad",
        )

        assert "Invalid scheduled_transaction_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.delete_scheduled_transaction.side_effect = (
            YNABError(404, "Not found")
        )

        result = await delete_scheduled_transaction(
            ctx=_mock_ctx(mock_client),
            scheduled_transaction_id=_VALID_UUID,
        )

        assert "Not found" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await delete_scheduled_transaction(
            ctx=_mock_ctx(),
            scheduled_transaction_id=_VALID_UUID,
            budget_id="bad",
        )

        assert "Invalid budget_id" in result


# --- get_user ---


class TestGetUser:
    @pytest.mark.anyio
    async def test_returns_user_id(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_user.return_value = User(
            id="user-abc-123"
        )
        mock_client.rate_limit_remaining = None

        result = await get_user(ctx=_mock_ctx(mock_client))

        assert "user-abc-123" in result
        mock_client.get_user.assert_called_once()

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_user.side_effect = YNABError(
            401, "Invalid access token"
        )

        result = await get_user(ctx=_mock_ctx(mock_client))

        assert "Invalid access token" in result


# --- get_budget_settings ---


def _make_budget_settings() -> BudgetSettings:
    return BudgetSettings(
        date_format=DateFormat(format="MM/DD/YYYY"),
        currency_format=CurrencyFormat(
            iso_code="USD",
            example_format="123,456.78",
            decimal_digits=2,
            decimal_separator=".",
            symbol_first=True,
            group_separator=",",
            currency_symbol="$",
            display_symbol=True,
        ),
    )


class TestGetBudgetSettings:
    @pytest.mark.anyio
    async def test_returns_settings(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budget_settings.return_value = (
            _make_budget_settings()
        )
        mock_client.rate_limit_remaining = None

        result = await get_budget_settings(
            ctx=_mock_ctx(mock_client)
        )

        assert "MM/DD/YYYY" in result
        assert "USD" in result
        assert "$" in result
        assert "before" in result

    @pytest.mark.anyio
    async def test_symbol_after(self) -> None:
        mock_client = AsyncMock()
        settings = _make_budget_settings()
        settings.currency_format.symbol_first = False
        mock_client.get_budget_settings.return_value = (
            settings
        )
        mock_client.rate_limit_remaining = None

        result = await get_budget_settings(
            ctx=_mock_ctx(mock_client)
        )

        assert "after" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await get_budget_settings(
            ctx=_mock_ctx(), budget_id="bad"
        )

        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budget_settings.side_effect = (
            YNABError(404, "Not found")
        )

        result = await get_budget_settings(
            ctx=_mock_ctx(mock_client)
        )

        assert "Not found" in result


# --- get_account ---


def _make_account_detail(
    name: str = "Checking",
    on_budget: bool = True,
    note: str | None = "Main account",
) -> AccountDetail:
    return AccountDetail(
        id=_VALID_UUID,
        name=name,
        type="checking",
        balance=Decimal("150.00"),
        cleared_balance=Decimal("120.00"),
        closed=False,
        deleted=False,
        on_budget=on_budget,
        note=note,
        uncleared_balance=Decimal("30.00"),
        transfer_payee_id="payee-1",
    )


class TestGetAccount:
    @pytest.mark.anyio
    async def test_returns_detail(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_account.return_value = (
            _make_account_detail()
        )
        mock_client.rate_limit_remaining = None

        result = await get_account(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
        )

        assert "Checking" in result
        assert "$150.00" in result
        assert "$120.00" in result
        assert "$30.00" in result
        assert "Yes" in result  # on_budget
        assert "Main account" in result

    @pytest.mark.anyio
    async def test_no_note(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_account.return_value = (
            _make_account_detail(note=None)
        )
        mock_client.rate_limit_remaining = None

        result = await get_account(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
        )

        assert "Note" not in result

    @pytest.mark.anyio
    async def test_off_budget(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_account.return_value = (
            _make_account_detail(on_budget=False)
        )
        mock_client.rate_limit_remaining = None

        result = await get_account(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
        )

        assert "No" in result

    @pytest.mark.anyio
    async def test_invalid_account_id(self) -> None:
        result = await get_account(
            ctx=_mock_ctx(),
            account_id="bad",
        )

        assert "Invalid account_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await get_account(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            budget_id="bad",
        )

        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_account.side_effect = YNABError(
            404, "Not found"
        )

        result = await get_account(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
        )

        assert "Not found" in result


# --- get_category ---


def _make_category_detail(
    note: str | None = "Weekly groceries",
    hidden: bool = False,
    goal_target: Decimal | None = None,
    goal_target_date: str | None = None,
    goal_type: str | None = None,
    goal_needs_whole_amount: bool | None = None,
    goal_under_funded: Decimal | None = None,
    goal_cadence: int | None = None,
    goal_cadence_frequency: int | None = None,
    goal_day: int | None = None,
    goal_percentage_complete: int | None = None,
    goal_months_to_budget: int | None = None,
    goal_overall_funded: Decimal | None = None,
    goal_overall_left: Decimal | None = None,
) -> Category:
    return Category(
        id=_VALID_UUID,
        name="Groceries",
        category_group_id="group-1",
        budgeted=Decimal("500.00"),
        activity=Decimal("-250.00"),
        balance=Decimal("250.00"),
        note=note,
        hidden=hidden,
        goal_target=goal_target,
        goal_target_date=goal_target_date,
        goal_type=goal_type,
        goal_needs_whole_amount=goal_needs_whole_amount,
        goal_under_funded=goal_under_funded,
        goal_cadence=goal_cadence,
        goal_cadence_frequency=goal_cadence_frequency,
        goal_day=goal_day,
        goal_percentage_complete=goal_percentage_complete,
        goal_months_to_budget=goal_months_to_budget,
        goal_overall_funded=goal_overall_funded,
        goal_overall_left=goal_overall_left,
        deleted=False,
    )


class TestGetCategory:
    @pytest.mark.anyio
    async def test_returns_category(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_category.return_value = (
            _make_category_detail()
        )
        mock_client.rate_limit_remaining = None

        result = await get_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
        )

        assert "Groceries" in result
        assert "$500.00" in result
        assert "-$250.00" in result
        assert "$250.00" in result
        assert "Weekly groceries" in result

    @pytest.mark.anyio
    async def test_hidden_category(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_category.return_value = (
            _make_category_detail(hidden=True)
        )
        mock_client.rate_limit_remaining = None

        result = await get_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
        )

        assert "Hidden: Yes" in result

    @pytest.mark.anyio
    async def test_target_metadata(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_category.return_value = (
            _make_category_detail(
                goal_target=Decimal("2500"),
                goal_target_date="2026-10-01",
                goal_type="TB",
                goal_needs_whole_amount=True,
                goal_under_funded=Decimal("250"),
                goal_cadence=1,
                goal_cadence_frequency=2,
                goal_day=30,
                goal_percentage_complete=50,
                goal_months_to_budget=2,
                goal_overall_funded=Decimal("1000"),
                goal_overall_left=Decimal("1500"),
            )
        )
        mock_client.rate_limit_remaining = None

        result = await get_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
        )

        assert "Target amount: $2,500.00" in result
        assert "Target date: 2026-10-01" in result
        assert "Target type: TB" in result
        assert "Needs whole amount: Yes" in result
        assert "Underfunded this month: $250.00" in result
        assert "Target cadence: Monthly (1)" in result
        assert "Target cadence frequency: 2" in result
        assert "Target day: 30" in result
        assert "Target complete: 50%" in result
        assert "Months left in target period: 2" in result
        assert "Funded in target period: $1,000.00" in result
        assert "Remaining in target period: $1,500.00" in result

    @pytest.mark.anyio
    async def test_no_note(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_category.return_value = (
            _make_category_detail(note=None)
        )
        mock_client.rate_limit_remaining = None

        result = await get_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
        )

        assert "Note" not in result

    @pytest.mark.anyio
    async def test_invalid_category_id(self) -> None:
        result = await get_category(
            ctx=_mock_ctx(),
            category_id="bad",
        )

        assert "Invalid category_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await get_category(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            budget_id="bad",
        )

        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_category.side_effect = YNABError(
            404, "Not found"
        )

        result = await get_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
        )

        assert "Not found" in result


# --- get_payee ---


class TestGetPayee:
    @pytest.mark.anyio
    async def test_returns_payee(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payee.return_value = PayeeDetail(
            id=_VALID_UUID,
            name="Costco",
            deleted=False,
            transfer_account_id="acct-2",
        )
        mock_client.rate_limit_remaining = None

        result = await get_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
        )

        assert "Costco" in result
        assert "acct-2" in result

    @pytest.mark.anyio
    async def test_no_transfer_account(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payee.return_value = PayeeDetail(
            id=_VALID_UUID,
            name="Costco",
            deleted=False,
            transfer_account_id=None,
        )
        mock_client.rate_limit_remaining = None

        result = await get_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
        )

        assert "Costco" in result
        assert "Transfer" not in result

    @pytest.mark.anyio
    async def test_invalid_payee_id(self) -> None:
        result = await get_payee(
            ctx=_mock_ctx(),
            payee_id="bad",
        )

        assert "Invalid payee_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await get_payee(
            ctx=_mock_ctx(),
            payee_id=_VALID_UUID,
            budget_id="bad",
        )

        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_payee.side_effect = YNABError(
            404, "Not found"
        )

        result = await get_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
        )

        assert "Not found" in result


# --- get_transaction ---


def _make_transaction_detail() -> Transaction:
    return Transaction(
        id=_VALID_UUID,
        account_id="acct-1",
        account_name="Checking",
        date="2026-02-25",
        amount=Decimal("-42.50"),
        payee_id="payee-1",
        payee_name="Costco",
        category_id="cat-1",
        category_name="Groceries",
        memo="Weekly shop",
        cleared="cleared",
        approved=True,
        deleted=False,
    )


class TestGetTransaction:
    @pytest.mark.anyio
    async def test_returns_transaction(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transaction.return_value = (
            _make_transaction_detail()
        )
        mock_client.rate_limit_remaining = None

        result = await get_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
        )

        assert "-$42.50" in result
        assert "Costco" in result
        assert "Checking" in result
        assert "cleared" in result
        assert "approved" in result

    @pytest.mark.anyio
    async def test_unapproved(self) -> None:
        mock_client = AsyncMock()
        txn = _make_transaction_detail()
        txn.approved = False
        mock_client.get_transaction.return_value = txn
        mock_client.rate_limit_remaining = None

        result = await get_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
        )

        assert "unapproved" in result

    @pytest.mark.anyio
    async def test_invalid_transaction_id(self) -> None:
        result = await get_transaction(
            ctx=_mock_ctx(),
            transaction_id="bad",
        )

        assert "Invalid transaction_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await get_transaction(
            ctx=_mock_ctx(),
            transaction_id=_VALID_UUID,
            budget_id="bad",
        )

        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_transaction.side_effect = YNABError(
            404, "Not found"
        )

        result = await get_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_VALID_UUID,
        )

        assert "Not found" in result


# --- update_payee ---


class TestUpdatePayee:
    @pytest.mark.anyio
    async def test_renames_payee(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_payee.return_value = PayeeDetail(
            id=_VALID_UUID,
            name="Costco Wholesale",
            deleted=False,
            transfer_account_id=None,
        )
        mock_client.rate_limit_remaining = None

        result = await update_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
            name="Costco Wholesale",
        )

        assert "Renamed" in result
        assert "Costco Wholesale" in result

    @pytest.mark.anyio
    async def test_dry_run(self) -> None:
        result = await update_payee(
            ctx=_mock_ctx(),
            payee_id=_VALID_UUID,
            name="New Name",
            dry_run=True,
        )

        assert "[DRY RUN]" in result
        assert "New Name" in result

    @pytest.mark.anyio
    async def test_invalid_payee_id(self) -> None:
        result = await update_payee(
            ctx=_mock_ctx(),
            payee_id="bad",
            name="Test",
        )

        assert "Invalid payee_id" in result

    @pytest.mark.anyio
    async def test_invalid_budget_id(self) -> None:
        result = await update_payee(
            ctx=_mock_ctx(),
            payee_id=_VALID_UUID,
            name="Test",
            budget_id="bad",
        )

        assert "Invalid budget_id" in result

    @pytest.mark.anyio
    async def test_empty_name(self) -> None:
        result = await update_payee(
            ctx=_mock_ctx(),
            payee_id=_VALID_UUID,
            name="",
        )

        assert "empty" in result

    @pytest.mark.anyio
    async def test_whitespace_name(self) -> None:
        result = await update_payee(
            ctx=_mock_ctx(),
            payee_id=_VALID_UUID,
            name="   ",
        )

        assert "empty" in result

    @pytest.mark.anyio
    async def test_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_payee.side_effect = YNABError(
            404, "Payee not found"
        )

        result = await update_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
            name="Test",
        )

        assert "Payee not found" in result

    @pytest.mark.anyio
    async def test_unexpected_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_payee.side_effect = (
            RuntimeError("boom")
        )

        result = await update_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
            name="Test",
        )

        assert "Unexpected error" in result
        assert "RuntimeError" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        mock_client = AsyncMock()
        mock_client.update_payee.return_value = PayeeDetail(
            id=_VALID_UUID,
            name="New",
            deleted=False,
            transfer_account_id=None,
        )
        mock_client.rate_limit_remaining = 10

        result = await update_payee(
            ctx=_mock_ctx(mock_client),
            payee_id=_VALID_UUID,
            name="New",
        )

        assert "Rate limit" in result
        assert "10/200" in result


# --- pre-release fix validation tests ---


class TestDefaultBudgetId:
    @pytest.mark.anyio
    async def test_default_budget_id_accepted(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_accounts.return_value = []

        result = await list_accounts(
            ctx=_mock_ctx(mock_client),
            budget_id="default",
        )

        assert "No open accounts" in result
        mock_client.get_accounts.assert_called_once_with(
            "default"
        )


class TestFeb31Rejected:
    @pytest.mark.anyio
    async def test_feb_31_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-31",
        )
        assert "Invalid date" in result
        assert "valid calendar date" in result

    @pytest.mark.anyio
    async def test_apr_31_returns_error(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-04-31",
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_valid_feb_28(self) -> None:
        """Feb 28 should pass date validation (hit API)."""
        mock_client = AsyncMock()
        txn = _make_transaction()
        mock_client.create_transaction.return_value = txn
        mock_client.rate_limit_remaining = None

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-28",
        )

        assert "Created transaction" in result


class TestTooManyDecimalPlaces:
    @pytest.mark.anyio
    async def test_four_decimal_places_rejected(self) -> None:
        result = await create_transaction(
            ctx=_mock_ctx(),
            account_id=_VALID_UUID,
            amount="-42.1234",
            date="2026-02-25",
        )

        assert "Invalid amount" in result
        assert "decimal" in result.lower()

    @pytest.mark.anyio
    async def test_three_decimal_places_accepted(self) -> None:
        mock_client = AsyncMock()
        txn = _make_transaction()
        mock_client.create_transaction.return_value = txn
        mock_client.rate_limit_remaining = None

        result = await create_transaction(
            ctx=_mock_ctx(mock_client),
            account_id=_VALID_UUID,
            amount="-42.123",
            date="2026-02-25",
        )

        assert "Created transaction" in result


class TestListBudgetsRateLimit:
    @pytest.mark.anyio
    async def test_rate_limit_warning_shown(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_budgets.return_value = [
            BudgetSummary(
                id="b-1",
                name="My Budget",
                last_modified_on="2026-02-28T12:00:00+00:00",
                first_month="2024-01-01",
                last_month="2026-02-01",
            ),
        ]
        mock_client.rate_limit_remaining = 10

        result = await list_budgets(
            ctx=_mock_ctx(mock_client)
        )

        assert "Rate limit" in result
        assert "10/200" in result


_SCHEDULED_TXN_ID = f"{_VALID_UUID}_2026-08-09"


class TestScheduledOccurrenceIds:
    """YNAB returns auto-entered scheduled rows as <uuid>_<date>.

    list_transactions prints those ids, so every tool that takes a
    transaction_id has to accept them back.
    """

    @pytest.mark.anyio
    async def test_get_transaction_accepts_occurrence_id(
        self,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_transaction.return_value = (
            _make_transaction(txn_id=_SCHEDULED_TXN_ID)
        )

        result = await get_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_SCHEDULED_TXN_ID,
        )

        assert "Invalid transaction_id" not in result
        mock_client.get_transaction.assert_awaited_once()

    @pytest.mark.anyio
    async def test_delete_transaction_accepts_occurrence_id(
        self,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None

        result = await delete_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_SCHEDULED_TXN_ID,
        )

        assert "Invalid transaction_id" not in result
        mock_client.delete_transaction.assert_awaited_once()

    @pytest.mark.anyio
    async def test_update_transaction_accepts_occurrence_id(
        self,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.update_transaction.return_value = (
            _make_transaction(txn_id=_SCHEDULED_TXN_ID)
        )

        result = await update_transaction(
            ctx=_mock_ctx(mock_client),
            transaction_id=_SCHEDULED_TXN_ID,
            memo="touched",
        )

        assert "Invalid transaction_id" not in result

    @pytest.mark.anyio
    async def test_still_rejects_junk_ids(self) -> None:
        for bad in (
            "../../evil",
            f"{_VALID_UUID}_not-a-date",
            f"{_VALID_UUID}_2026-08-09_extra",
            "_2026-08-09",
        ):
            result = await get_transaction(
                ctx=_mock_ctx(), transaction_id=bad
            )
            assert "Invalid transaction_id" in result, bad


class TestTransactionStatusFlags:
    @pytest.mark.anyio
    async def test_cleared_approved_row_has_no_flags(
        self,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_transactions.return_value = [
            _make_transaction()
        ]

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-08-01",
        )

        assert "[" not in result.split("ID:")[0]

    @pytest.mark.anyio
    async def test_uncleared_and_unapproved_are_flagged(
        self,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_transactions.return_value = [
            _make_transaction(
                cleared="uncleared", approved=False
            )
        ]

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-08-01",
        )

        assert "[uncleared, unapproved]" in result

    @pytest.mark.anyio
    async def test_reconciled_is_flagged(self) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_transactions.return_value = [
            _make_transaction(cleared="reconciled")
        ]

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-08-01",
        )

        assert "[reconciled]" in result

    @pytest.mark.anyio
    async def test_scheduled_occurrence_is_flagged(self) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_transactions.return_value = [
            _make_transaction(txn_id=_SCHEDULED_TXN_ID)
        ]

        result = await list_transactions(
            ctx=_mock_ctx(mock_client),
            since_date="2026-08-01",
        )

        assert "[scheduled]" in result


class TestReadyToAssignPresentation:
    @pytest.mark.anyio
    async def test_rta_category_is_not_labelled_available(
        self,
    ) -> None:
        groups = [
            CategoryGroup(
                id="internal-1",
                name="Internal Master Category",
                deleted=False,
                categories=[
                    Category(
                        id=_VALID_UUID,
                        name="Inflow: Ready to Assign",
                        budgeted=Decimal("0"),
                        activity=Decimal("43204.59"),
                        balance=Decimal("43204.59"),
                        deleted=False,
                    ),
                ],
            ),
        ]
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_categories.return_value = groups

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "net income" in result
        assert "NOT Ready to Assign" in result
        assert "get_month" in result
        assert "$43,204.59 available" not in result

    @pytest.mark.anyio
    async def test_normal_category_balance_is_labelled(
        self,
    ) -> None:
        groups = [
            CategoryGroup(
                id="group-1",
                name="Monthly Bills",
                deleted=False,
                categories=[
                    Category(
                        id=_VALID_UUID,
                        name="Rent",
                        budgeted=Decimal("1500"),
                        activity=Decimal("-1200"),
                        balance=Decimal("300"),
                        deleted=False,
                    ),
                ],
            ),
        ]
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_categories.return_value = groups

        result = await list_categories(
            ctx=_mock_ctx(mock_client)
        )

        assert "$300.00 available" in result
        assert "NOT Ready to Assign" not in result

    @pytest.mark.anyio
    async def test_get_month_labels_to_be_budgeted(self) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_month.return_value = MonthDetail(
            month="2026-08-01",
            income=Decimal("46537.21"),
            budgeted=Decimal("24925.62"),
            activity=Decimal("-1634.26"),
            to_be_budgeted=Decimal("5577.49"),
            age_of_money=0,
            note=None,
            deleted=False,
            categories=[],
        )

        result = await get_month(
            ctx=_mock_ctx(mock_client), month="2026-08-01"
        )

        assert "Ready to Assign: $5,577.49" in result
        assert "- Available:" not in result

    @pytest.mark.anyio
    async def test_list_months_labels_to_be_budgeted(self) -> None:
        mock_client = AsyncMock()
        mock_client.rate_limit_remaining = None
        mock_client.get_months.return_value = [
            _make_month_summary(
                to_be_budgeted=Decimal("5577.49")
            )
        ]

        result = await list_months(ctx=_mock_ctx(mock_client))

        assert "Ready to Assign $5,577.49" in result
        assert "Available $" not in result
