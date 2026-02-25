"""Tests for MCP server tool integration."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from py_ynab_mcp.client import YNABError
from py_ynab_mcp.models import Account
from py_ynab_mcp.server import list_accounts


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
