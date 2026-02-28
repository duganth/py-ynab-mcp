"""Tests for MCP server tool integration."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from py_ynab_mcp.client import YNABError
from py_ynab_mcp.models import (
    Account,
    BudgetSummary,
    BulkResult,
    Category,
    CategoryGroup,
    MonthDetail,
    MonthSummary,
    Payee,
    Transaction,
)
from py_ynab_mcp.server import (
    create_transaction,
    create_transactions,
    delete_transaction,
    get_month,
    list_accounts,
    list_budgets,
    list_categories,
    list_months,
    list_payees,
    list_transactions,
    update_category,
    update_category_budget,
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
        cleared="cleared",
        approved=True,
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

        assert "unexpected error" in result


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

        assert "unexpected error" in result


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

        assert "unexpected error" in result


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

        assert "unexpected error" in result


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

        assert "unexpected error" in result

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
        assert "unexpected error" in result

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

        assert "unexpected error" in result

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
        bulk = BulkResult(
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
    async def test_duplicates_reported(self) -> None:
        bulk = BulkResult(
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

        assert "unexpected error" in result


class TestUpdateCategory:
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
    async def test_updates_hidden(self) -> None:
        cat = _make_category(hidden=True)
        mock_client = AsyncMock()
        mock_client.update_category.return_value = cat
        mock_client.rate_limit_remaining = None

        result = await update_category(
            ctx=_mock_ctx(mock_client),
            category_id=_VALID_UUID,
            hidden=True,
        )

        assert "hidden" in result

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
        result = await update_category(
            ctx=_mock_ctx(),
            category_id=_VALID_UUID,
            name="Restaurants",
            note="Eating out",
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "Restaurants" in result
        assert "Eating out" in result

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

        assert "unexpected error" in result
