"""Tests for MCP server tool integration."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from py_ynab_mcp.client import YNABError
from py_ynab_mcp.models import Account, BulkResult, Transaction
from py_ynab_mcp.server import (
    create_transaction,
    create_transactions,
    delete_transaction,
    list_accounts,
    update_transaction,
)

_VALID_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_VALID_UUID_2 = "11111111-2222-3333-4444-555555555555"


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
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = accounts
            mock_cls.return_value = mock_client

            result = await list_accounts()

        assert "Checking" in result
        assert "$1,500.50" in result
        assert "Savings" in result
        assert "$10,000.00" in result

    @pytest.mark.anyio
    async def test_negative_balance_formatting(self) -> None:
        accounts = [
            _make_account(
                "Credit Card", "creditCard",
                Decimal("-1500"), Decimal("-1200"),
            ),
        ]
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = accounts
            mock_cls.return_value = mock_client

            result = await list_accounts()

        assert "-$1,500.00" in result
        assert "-$1,200.00" in result

    @pytest.mark.anyio
    async def test_passes_budget_id(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = []
            mock_cls.return_value = mock_client

            await list_accounts(budget_id="my-budget")

        mock_client.get_accounts.assert_called_once_with(
            "my-budget"
        )

    @pytest.mark.anyio
    async def test_default_budget_uses_last_used(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = []
            mock_cls.return_value = mock_client

            await list_accounts()

        mock_client.get_accounts.assert_called_once_with(
            "last-used"
        )

    @pytest.mark.anyio
    async def test_missing_token_returns_error(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient",
            side_effect=ValueError(
                "YNAB access token required"
            ),
        ):
            result = await list_accounts()

        assert "Configuration error" in result

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.side_effect = YNABError(
                401, "Invalid access token"
            )
            mock_cls.return_value = mock_client

            result = await list_accounts()

        assert "Invalid access token" in result

    @pytest.mark.anyio
    async def test_no_accounts(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = []
            mock_cls.return_value = mock_client

            result = await list_accounts()

        assert "No open accounts found" in result

    @pytest.mark.anyio
    async def test_unexpected_error_caught(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.side_effect = (
                RuntimeError("something broke")
            )
            mock_cls.return_value = mock_client

            result = await list_accounts()

        assert "unexpected error" in result

    @pytest.mark.anyio
    async def test_client_closed_after_success(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = []
            mock_cls.return_value = mock_client

            await list_accounts()

        mock_client.close.assert_called_once()

    @pytest.mark.anyio
    async def test_client_closed_after_error(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_accounts.side_effect = YNABError(
                500, "Server error"
            )
            mock_cls.return_value = mock_client

            await list_accounts()

        mock_client.close.assert_called_once()


class TestCreateTransaction:
    @pytest.mark.anyio
    async def test_creates_and_returns_confirmation(
        self,
    ) -> None:
        txn = _make_transaction()
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transaction.return_value = txn
            mock_client.rate_limit_remaining = None
            mock_cls.return_value = mock_client

            result = await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
                payee_name="Costco",
            )

        assert "txn-1" in result
        assert "Costco" in result
        mock_client.close.assert_called_once()

    @pytest.mark.anyio
    async def test_invalid_amount_returns_error(self) -> None:
        result = await create_transaction(
            account_id=_VALID_UUID,
            amount="not-a-number",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_nan_amount_returns_error(self) -> None:
        result = await create_transaction(
            account_id=_VALID_UUID,
            amount="NaN",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_empty_amount_returns_error(self) -> None:
        result = await create_transaction(
            account_id=_VALID_UUID,
            amount="",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_infinity_amount_returns_error(self) -> None:
        result = await create_transaction(
            account_id=_VALID_UUID,
            amount="Infinity",
            date="2026-02-25",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_invalid_date_returns_error(self) -> None:
        result = await create_transaction(
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
            account_id=_VALID_UUID,
            amount="-42.50",
            date="2026-02-25",
            cleared="invalid",
        )
        assert "Invalid cleared" in result

    @pytest.mark.anyio
    async def test_dry_run_returns_preview(self) -> None:
        result = await create_transaction(
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
    async def test_dry_run_no_api_call(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            result = await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
                dry_run=True,
            )

        assert "[DRY RUN]" in result
        mock_cls.assert_not_called()

    @pytest.mark.anyio
    async def test_rate_limit_warning_shown(self) -> None:
        txn = _make_transaction()
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transaction.return_value = txn
            mock_client.rate_limit_remaining = 15
            mock_cls.return_value = mock_client

            result = await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
            )

        assert "Rate limit" in result
        assert "15/200" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning_hidden(self) -> None:
        txn = _make_transaction()
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transaction.return_value = txn
            mock_client.rate_limit_remaining = 150
            mock_cls.return_value = mock_client

            result = await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
            )

        assert "Rate limit" not in result

    @pytest.mark.anyio
    async def test_missing_token_returns_error(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient",
            side_effect=ValueError("token required"),
        ):
            result = await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
            )

        assert "Configuration error" in result

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transaction.side_effect = (
                YNABError(400, "Bad request")
            )
            mock_cls.return_value = mock_client

            result = await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
            )

        assert "Bad request" in result

    @pytest.mark.anyio
    async def test_client_closed_on_error(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transaction.side_effect = (
                YNABError(500, "Server error")
            )
            mock_cls.return_value = mock_client

            await create_transaction(
                account_id=_VALID_UUID,
                amount="-42.50",
                date="2026-02-25",
            )

        mock_client.close.assert_called_once()


class TestCreateTransactions:
    @pytest.mark.anyio
    async def test_bulk_create(self) -> None:
        bulk = BulkResult(
            transaction_ids=["txn-1", "txn-2"],
            duplicate_import_ids=[],
        )
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transactions.return_value = bulk
            mock_client.rate_limit_remaining = None
            mock_cls.return_value = mock_client

            result = await create_transactions(
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
            transactions_json="not json",
        )
        assert "Invalid JSON" in result

    @pytest.mark.anyio
    async def test_empty_array(self) -> None:
        result = await create_transactions(
            transactions_json="[]",
        )
        assert "non-empty" in result

    @pytest.mark.anyio
    async def test_not_array(self) -> None:
        result = await create_transactions(
            transactions_json='{"not": "array"}',
        )
        assert "non-empty JSON array" in result

    @pytest.mark.anyio
    async def test_invalid_amount_in_bulk(self) -> None:
        result = await create_transactions(
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
    async def test_dry_run_no_api_call(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            await create_transactions(
                transactions_json=(
                    f'[{{"account_id": "{_VALID_UUID}",'
                    f' "amount": "-10.00",'
                    f' "date": "2026-02-25"}}]'
                ),
                dry_run=True,
            )

        mock_cls.assert_not_called()

    @pytest.mark.anyio
    async def test_duplicates_reported(self) -> None:
        bulk = BulkResult(
            transaction_ids=["txn-1"],
            duplicate_import_ids=["dup-1"],
        )
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_transactions.return_value = bulk
            mock_client.rate_limit_remaining = None
            mock_cls.return_value = mock_client

            result = await create_transactions(
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
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.update_transaction.return_value = txn
            mock_client.rate_limit_remaining = None
            mock_cls.return_value = mock_client

            result = await update_transaction(
                transaction_id=_VALID_UUID,
                memo="Updated memo",
            )

        assert "Updated transaction" in result
        assert "Updated memo" in result
        mock_client.close.assert_called_once()

    @pytest.mark.anyio
    async def test_no_fields_returns_error(self) -> None:
        result = await update_transaction(
            transaction_id=_VALID_UUID,
        )
        assert "No fields to update" in result

    @pytest.mark.anyio
    async def test_invalid_transaction_id(self) -> None:
        result = await update_transaction(
            transaction_id="bad-id",
            memo="test",
        )
        assert "Invalid transaction_id" in result

    @pytest.mark.anyio
    async def test_invalid_amount(self) -> None:
        result = await update_transaction(
            transaction_id=_VALID_UUID,
            amount="not-a-number",
        )
        assert "Invalid amount" in result

    @pytest.mark.anyio
    async def test_invalid_date(self) -> None:
        result = await update_transaction(
            transaction_id=_VALID_UUID,
            date="bad-date",
        )
        assert "Invalid date" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        result = await update_transaction(
            transaction_id=_VALID_UUID,
            amount="-50.00",
            memo="Changed",
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert "-$50.00" in result
        assert "Changed" in result

    @pytest.mark.anyio
    async def test_dry_run_no_api_call(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            await update_transaction(
                transaction_id=_VALID_UUID,
                memo="test",
                dry_run=True,
            )

        mock_cls.assert_not_called()

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        txn = _make_transaction()
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.update_transaction.return_value = txn
            mock_client.rate_limit_remaining = 10
            mock_cls.return_value = mock_client

            result = await update_transaction(
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
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.rate_limit_remaining = None
            mock_cls.return_value = mock_client

            result = await delete_transaction(
                transaction_id=_VALID_UUID,
            )

        assert "Deleted transaction" in result
        assert _VALID_UUID in result
        mock_client.close.assert_called_once()

    @pytest.mark.anyio
    async def test_invalid_transaction_id(self) -> None:
        result = await delete_transaction(
            transaction_id="bad-id",
        )
        assert "Invalid transaction_id" in result

    @pytest.mark.anyio
    async def test_dry_run_preview(self) -> None:
        result = await delete_transaction(
            transaction_id=_VALID_UUID,
            dry_run=True,
        )
        assert "[DRY RUN]" in result
        assert _VALID_UUID in result

    @pytest.mark.anyio
    async def test_dry_run_no_api_call(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            await delete_transaction(
                transaction_id=_VALID_UUID,
                dry_run=True,
            )

        mock_cls.assert_not_called()

    @pytest.mark.anyio
    async def test_api_error_returns_message(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.delete_transaction.side_effect = (
                YNABError(404, "Transaction not found")
            )
            mock_cls.return_value = mock_client

            result = await delete_transaction(
                transaction_id=_VALID_UUID,
            )

        assert "Transaction not found" in result

    @pytest.mark.anyio
    async def test_rate_limit_warning(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.rate_limit_remaining = 5
            mock_cls.return_value = mock_client

            result = await delete_transaction(
                transaction_id=_VALID_UUID,
            )

        assert "Rate limit" in result
        assert "5/200" in result

    @pytest.mark.anyio
    async def test_missing_token_returns_error(self) -> None:
        with patch(
            "py_ynab_mcp.server.YNABClient",
            side_effect=ValueError("token required"),
        ):
            result = await delete_transaction(
                transaction_id=_VALID_UUID,
            )

        assert "Configuration error" in result
