"""Tests for YNAB API client."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from py_ynab_mcp.client import YNABClient, YNABError
from py_ynab_mcp.models import (
    ScheduledTransactionUpdate,
    ScheduledTransactionWrite,
    TransactionUpdate,
    TransactionWrite,
)


@pytest.fixture
def client() -> YNABClient:
    return YNABClient(access_token="test-token")


def _mock_response(
    status_code: int = 200,
    json_data: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        headers=headers or {},
        request=httpx.Request(
            "GET", "https://api.ynab.com/v1/test"
        ),
    )


_VALID_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_VALID_UUID_2 = "11111111-2222-3333-4444-555555555555"


class TestClientInit:
    def test_missing_token_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(
                ValueError, match="YNAB access token required"
            ):
                YNABClient()

    def test_token_from_param(self) -> None:
        c = YNABClient(access_token="my-token")
        assert (
            c._client.headers["Authorization"]
            == "Bearer my-token"
        )

    def test_token_from_env(self) -> None:
        with patch.dict(
            "os.environ", {"YNAB_ACCESS_TOKEN": "env-token"}
        ):
            c = YNABClient()
            assert (
                c._client.headers["Authorization"]
                == "Bearer env-token"
            )

    def test_rate_limit_initially_none(self) -> None:
        c = YNABClient(access_token="test")
        assert c.rate_limit_remaining is None


class TestGetBudgets:
    @pytest.mark.anyio
    async def test_returns_budgets(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "budgets": [
                    {
                        "id": "budget-1",
                        "name": "My Budget",
                        "last_modified_on": "2026-02-28T12:00:00+00:00",
                        "first_month": "2024-01-01",
                        "last_month": "2026-02-01",
                    },
                    {
                        "id": "budget-2",
                        "name": "Joint Budget",
                        "last_modified_on": "2026-02-27T08:00:00+00:00",
                        "first_month": "2025-06-01",
                        "last_month": "2026-03-01",
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            budgets = await client.get_budgets()

        assert len(budgets) == 2
        assert budgets[0].id == "budget-1"
        assert budgets[0].name == "My Budget"


class TestGetAccounts:
    @pytest.mark.anyio
    async def test_returns_open_accounts(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "accounts": [
                    {
                        "id": "acct-1",
                        "name": "Checking",
                        "type": "checking",
                        "balance": 50000,
                        "cleared_balance": 45000,
                        "closed": False,
                        "deleted": False,
                    },
                    {
                        "id": "acct-2",
                        "name": "Old Account",
                        "type": "savings",
                        "balance": 0,
                        "cleared_balance": 0,
                        "closed": True,
                        "deleted": False,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            accounts = await client.get_accounts(_VALID_UUID)

        assert len(accounts) == 1
        assert accounts[0].name == "Checking"
        assert accounts[0].balance == Decimal("50")

    @pytest.mark.anyio
    async def test_filters_deleted(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "accounts": [
                    {
                        "id": "acct-1",
                        "name": "Deleted",
                        "type": "checking",
                        "balance": 0,
                        "cleared_balance": 0,
                        "closed": False,
                        "deleted": True,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            accounts = await client.get_accounts()

        assert len(accounts) == 0

    @pytest.mark.anyio
    async def test_invalid_budget_id_rejected(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(YNABError, match="Invalid budget_id"):
            await client.get_accounts("../../evil/path")

    @pytest.mark.anyio
    async def test_valid_uuid_accepted(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {"accounts": []}
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            accounts = await client.get_accounts(_VALID_UUID)

        assert accounts == []


class TestErrorHandling:
    @pytest.mark.anyio
    async def test_401_raises_auth_error(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(401, {})
            with pytest.raises(
                YNABError, match="Invalid access token"
            ):
                await client.get_budgets()

    @pytest.mark.anyio
    async def test_429_raises_rate_limit(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(429, {})
            with pytest.raises(YNABError, match="Rate limited"):
                await client.get_budgets()

    @pytest.mark.anyio
    async def test_timeout_raises(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = httpx.TimeoutException(
                "timed out"
            )
            with pytest.raises(YNABError, match="Network error"):
                await client.get_budgets()

    @pytest.mark.anyio
    async def test_connect_error_raises(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = httpx.ConnectError(
                "connection refused"
            )
            with pytest.raises(YNABError, match="Network error"):
                await client.get_budgets()

    @pytest.mark.anyio
    async def test_generic_http_error_raises(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = httpx.ReadError(
                "connection reset"
            )
            with pytest.raises(YNABError, match="Network error"):
                await client.get_budgets()

    @pytest.mark.anyio
    async def test_error_with_detail_json(
        self, client: YNABClient
    ) -> None:
        error_body: dict[str, object] = {
            "error": {
                "id": "404",
                "name": "not_found",
                "detail": "Budget not found",
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                404, error_body
            )
            with pytest.raises(
                YNABError, match="Budget not found"
            ):
                await client.get_budgets()

    @pytest.mark.anyio
    async def test_error_with_non_json_body(
        self, client: YNABClient
    ) -> None:
        resp = httpx.Response(
            status_code=502,
            text="<html>Bad Gateway</html>",
            request=httpx.Request(
                "GET", "https://api.ynab.com/v1/budgets"
            ),
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = resp
            with pytest.raises(YNABError, match="HTTP 502"):
                await client.get_budgets()


class TestRateLimitTracking:
    @pytest.mark.anyio
    async def test_tracks_used_total_format(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {"budgets": []}
        }
        resp = _mock_response(
            200, mock_data,
            headers={"x-rate-limit": "20/200"},
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = resp
            await client.get_budgets()

        assert client.rate_limit_remaining == 180

    @pytest.mark.anyio
    async def test_tracks_plain_int_format(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {"budgets": []}
        }
        resp = _mock_response(
            200, mock_data,
            headers={"x-rate-limit": "180"},
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = resp
            await client.get_budgets()

        assert client.rate_limit_remaining == 180

    @pytest.mark.anyio
    async def test_no_header_stays_none(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {"budgets": []}
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            await client.get_budgets()

        assert client.rate_limit_remaining is None

    @pytest.mark.anyio
    async def test_updates_across_requests(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {"budgets": []}
        }
        resp1 = _mock_response(
            200, mock_data,
            headers={"x-rate-limit": "100/200"},
        )
        resp2 = _mock_response(
            200, mock_data,
            headers={"x-rate-limit": "101/200"},
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = resp1
            await client.get_budgets()
            assert client.rate_limit_remaining == 100  # 200-100

            mock_req.return_value = resp2
            await client.get_budgets()
            assert client.rate_limit_remaining == 99  # 200-101


def _txn_response(
    txn_id: str = "txn-1",
) -> dict[str, object]:
    """Build a mock YNAB transaction response."""
    return {
        "data": {
            "transaction": {
                "id": txn_id,
                "account_id": _VALID_UUID,
                "account_name": "Checking",
                "date": "2026-02-25",
                "amount": -42500,
                "payee_id": None,
                "payee_name": "Costco",
                "category_id": None,
                "category_name": "Groceries",
                "memo": "Weekly shop",
                "cleared": "cleared",
                "approved": True,
                "deleted": False,
            }
        }
    }


class TestCreateTransaction:
    @pytest.mark.anyio
    async def test_creates_transaction(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_response()
            )
            txn_write = TransactionWrite(
                account_id=_VALID_UUID,
                date="2026-02-25",
                amount=-42500,
                payee_name="Costco",
            )
            result = await client.create_transaction(
                _VALID_UUID, txn_write
            )

        assert result.id == "txn-1"
        assert result.amount == Decimal("-42.5")
        assert result.payee_name == "Costco"
        # Verify POST was called with correct body
        call_args = mock_req.call_args
        assert call_args[1]["json"]["transaction"]["amount"] == -42500

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        txn = TransactionWrite(
            account_id=_VALID_UUID,
            date="2026-02-25",
            amount=-42500,
        )
        with pytest.raises(YNABError, match="Invalid budget_id"):
            await client.create_transaction("bad-id", txn)


class TestCreateTransactions:
    @pytest.mark.anyio
    async def test_bulk_create(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "bulk": {
                    "transaction_ids": ["txn-1", "txn-2"],
                    "duplicate_import_ids": [],
                }
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            writes = [
                TransactionWrite(
                    account_id=_VALID_UUID,
                    date="2026-02-25",
                    amount=-10000,
                ),
                TransactionWrite(
                    account_id=_VALID_UUID,
                    date="2026-02-25",
                    amount=-20000,
                ),
            ]
            result = await client.create_transactions(
                _VALID_UUID, writes
            )

        assert result.transaction_ids == ["txn-1", "txn-2"]
        assert result.duplicate_import_ids == []

    @pytest.mark.anyio
    async def test_bulk_with_duplicates(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "bulk": {
                    "transaction_ids": ["txn-1"],
                    "duplicate_import_ids": ["import-dup"],
                }
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            writes = [
                TransactionWrite(
                    account_id=_VALID_UUID,
                    date="2026-02-25",
                    amount=-10000,
                    import_id="import-dup",
                ),
            ]
            result = await client.create_transactions(
                _VALID_UUID, writes
            )

        assert result.duplicate_import_ids == ["import-dup"]


class TestUpdateTransaction:
    @pytest.mark.anyio
    async def test_update_single(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "transactions": [
                    {
                        "id": _VALID_UUID_2,
                        "account_id": _VALID_UUID,
                        "account_name": "Checking",
                        "date": "2026-02-25",
                        "amount": -50000,
                        "payee_id": None,
                        "payee_name": "Costco",
                        "category_id": None,
                        "category_name": "Groceries",
                        "memo": "Updated memo",
                        "cleared": "cleared",
                        "approved": True,
                        "deleted": False,
                    }
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            update = TransactionUpdate(
                id=_VALID_UUID_2,
                memo="Updated memo",
            )
            result = await client.update_transaction(
                _VALID_UUID, update
            )

        assert result.memo == "Updated memo"
        # Verify PATCH was called
        call_args = mock_req.call_args
        assert call_args[0][0] == "PATCH"


class TestUpdateTransactions:
    @pytest.mark.anyio
    async def test_bulk_update(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "transactions": [
                    {
                        "id": _VALID_UUID,
                        "account_id": _VALID_UUID,
                        "account_name": "Checking",
                        "date": "2026-02-25",
                        "amount": -10000,
                        "payee_id": None,
                        "payee_name": None,
                        "category_id": None,
                        "category_name": None,
                        "memo": "Bulk updated",
                        "cleared": "cleared",
                        "approved": True,
                        "deleted": False,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            updates = [
                TransactionUpdate(
                    id=_VALID_UUID,
                    memo="Bulk updated",
                ),
            ]
            result = await client.update_transactions(
                _VALID_UUID, updates
            )

        assert len(result) == 1
        assert result[0].memo == "Bulk updated"


class TestDeleteTransaction:
    @pytest.mark.anyio
    async def test_deletes_transaction(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "transaction": {
                    "id": _VALID_UUID_2,
                    "account_id": _VALID_UUID,
                    "account_name": "Checking",
                    "date": "2026-02-25",
                    "amount": -42500,
                    "payee_id": None,
                    "payee_name": None,
                    "category_id": None,
                    "category_name": None,
                    "memo": None,
                    "cleared": "cleared",
                    "approved": True,
                    "deleted": True,
                }
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            await client.delete_transaction(
                _VALID_UUID, _VALID_UUID_2
            )

        call_args = mock_req.call_args
        assert call_args[0][0] == "DELETE"
        assert _VALID_UUID_2 in call_args[0][1]

    @pytest.mark.anyio
    async def test_invalid_transaction_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid transaction_id"
        ):
            await client.delete_transaction(
                _VALID_UUID, "bad-id"
            )

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.delete_transaction(
                "bad-id", _VALID_UUID_2
            )


class TestGetCategories:
    @pytest.mark.anyio
    async def test_returns_categories(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "category_groups": [
                    {
                        "id": "grp-1",
                        "name": "Bills",
                        "deleted": False,
                        "categories": [
                            {
                                "id": "cat-1",
                                "name": "Rent",
                                "budgeted": 1500000,
                                "activity": -1500000,
                                "balance": 0,
                                "deleted": False,
                            },
                        ],
                    },
                    {
                        "id": "grp-2",
                        "name": "Deleted Group",
                        "deleted": True,
                        "categories": [],
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            groups = await client.get_categories(_VALID_UUID)

        assert len(groups) == 1
        assert groups[0].name == "Bills"
        assert groups[0].categories[0].budgeted == Decimal("1500")

    @pytest.mark.anyio
    async def test_filters_deleted_categories_within_groups(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "category_groups": [
                    {
                        "id": "grp-1",
                        "name": "Bills",
                        "deleted": False,
                        "categories": [
                            {
                                "id": "cat-1",
                                "name": "Rent",
                                "budgeted": 1500000,
                                "activity": -1500000,
                                "balance": 0,
                                "deleted": False,
                            },
                            {
                                "id": "cat-2",
                                "name": "Old Bill",
                                "budgeted": 0,
                                "activity": 0,
                                "balance": 0,
                                "deleted": True,
                            },
                        ],
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            groups = await client.get_categories(_VALID_UUID)

        assert len(groups) == 1
        assert len(groups[0].categories) == 1
        assert groups[0].categories[0].name == "Rent"


class TestGetPayees:
    @pytest.mark.anyio
    async def test_returns_payees(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "payees": [
                    {
                        "id": "payee-1",
                        "name": "Costco",
                        "deleted": False,
                    },
                    {
                        "id": "payee-2",
                        "name": "Old Payee",
                        "deleted": True,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            payees = await client.get_payees(_VALID_UUID)

        assert len(payees) == 1
        assert payees[0].name == "Costco"


def _txn_list_response(
    *txn_ids: str,
) -> dict[str, object]:
    """Build a mock YNAB transactions list response."""
    txns = []
    for tid in txn_ids:
        txns.append({
            "id": tid,
            "account_id": _VALID_UUID,
            "account_name": "Checking",
            "date": "2026-02-25",
            "amount": -42500,
            "payee_id": None,
            "payee_name": "Costco",
            "category_id": None,
            "category_name": "Groceries",
            "memo": "Weekly shop",
            "cleared": "cleared",
            "approved": True,
            "deleted": False,
        })
    return {"data": {"transactions": txns}}


class TestGetTransactions:
    @pytest.mark.anyio
    async def test_returns_transactions(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response("txn-1", "txn-2")
            )
            result = await client.get_transactions(
                _VALID_UUID, since_date="2026-02-01"
            )

        assert len(result) == 2
        assert result[0].id == "txn-1"
        assert result[1].id == "txn-2"

    @pytest.mark.anyio
    async def test_filters_deleted(
        self, client: YNABClient
    ) -> None:
        data: dict[str, object] = {
            "data": {
                "transactions": [
                    {
                        "id": "txn-1",
                        "account_id": _VALID_UUID,
                        "account_name": "Checking",
                        "date": "2026-02-25",
                        "amount": -42500,
                        "payee_id": None,
                        "payee_name": "Costco",
                        "category_id": None,
                        "category_name": "Groceries",
                        "memo": None,
                        "cleared": "cleared",
                        "approved": True,
                        "deleted": False,
                    },
                    {
                        "id": "txn-2",
                        "account_id": _VALID_UUID,
                        "account_name": "Checking",
                        "date": "2026-02-25",
                        "amount": -10000,
                        "payee_id": None,
                        "payee_name": "Deleted",
                        "category_id": None,
                        "category_name": None,
                        "memo": None,
                        "cleared": "cleared",
                        "approved": True,
                        "deleted": True,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.get_transactions(
                _VALID_UUID, since_date="2026-02-01"
            )

        assert len(result) == 1
        assert result[0].id == "txn-1"

    @pytest.mark.anyio
    async def test_routes_to_account_endpoint(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response()
            )
            await client.get_transactions(
                _VALID_UUID,
                since_date="2026-02-01",
                account_id=_VALID_UUID_2,
            )

        call_args = mock_req.call_args
        path = call_args[0][1]
        assert f"/accounts/{_VALID_UUID_2}/transactions" in path

    @pytest.mark.anyio
    async def test_routes_to_category_endpoint(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response()
            )
            await client.get_transactions(
                _VALID_UUID,
                since_date="2026-02-01",
                category_id=_VALID_UUID_2,
            )

        call_args = mock_req.call_args
        path = call_args[0][1]
        assert (
            f"/categories/{_VALID_UUID_2}/transactions" in path
        )

    @pytest.mark.anyio
    async def test_routes_to_payee_endpoint(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response()
            )
            await client.get_transactions(
                _VALID_UUID,
                since_date="2026-02-01",
                payee_id=_VALID_UUID_2,
            )

        call_args = mock_req.call_args
        path = call_args[0][1]
        assert f"/payees/{_VALID_UUID_2}/transactions" in path

    @pytest.mark.anyio
    async def test_passes_since_date_param(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response()
            )
            await client.get_transactions(
                _VALID_UUID, since_date="2026-02-01"
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["params"]["since_date"] == "2026-02-01"

    @pytest.mark.anyio
    async def test_passes_type_param(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response()
            )
            await client.get_transactions(
                _VALID_UUID,
                since_date="2026-02-01",
                type="uncategorized",
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["params"]["type"] == "uncategorized"

    @pytest.mark.anyio
    async def test_multiple_filters_raises(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            ValueError, match="At most one"
        ):
            await client.get_transactions(
                _VALID_UUID,
                since_date="2026-02-01",
                account_id=_VALID_UUID_2,
                category_id=_VALID_UUID_2,
            )

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_transactions(
                "bad-id", since_date="2026-02-01"
            )

    @pytest.mark.anyio
    async def test_invalid_account_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid account_id"
        ):
            await client.get_transactions(
                _VALID_UUID,
                since_date="2026-02-01",
                account_id="bad-id",
            )

    @pytest.mark.anyio
    async def test_default_endpoint_no_filter(
        self, client: YNABClient
    ) -> None:
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, _txn_list_response()
            )
            await client.get_transactions(
                _VALID_UUID, since_date="2026-02-01"
            )

        call_args = mock_req.call_args
        path = call_args[0][1]
        assert path == f"/budgets/{_VALID_UUID}/transactions"


class TestRequestJsonBody:
    @pytest.mark.anyio
    async def test_passes_json_body(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": _txn_response()["data"]
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            txn = TransactionWrite(
                account_id=_VALID_UUID,
                date="2026-02-25",
                amount=-42500,
            )
            await client.create_transaction(_VALID_UUID, txn)

        call_kwargs = mock_req.call_args[1]
        assert "json" in call_kwargs
        assert call_kwargs["json"]["transaction"]["amount"] == -42500


class TestGetMonths:
    @pytest.mark.anyio
    async def test_returns_months(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "months": [
                    {
                        "month": "2026-02-01",
                        "note": None,
                        "income": 500000,
                        "budgeted": 400000,
                        "activity": -350000,
                        "to_be_budgeted": 100000,
                        "age_of_money": 45,
                        "deleted": False,
                    },
                    {
                        "month": "2026-01-01",
                        "note": "January",
                        "income": 600000,
                        "budgeted": 500000,
                        "activity": -450000,
                        "to_be_budgeted": 50000,
                        "age_of_money": 40,
                        "deleted": False,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            months = await client.get_months(_VALID_UUID)

        assert len(months) == 2
        assert months[0].month == "2026-02-01"
        from decimal import Decimal
        assert months[0].income == Decimal("500")

    @pytest.mark.anyio
    async def test_filters_deleted(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "months": [
                    {
                        "month": "2026-02-01",
                        "note": None,
                        "income": 500000,
                        "budgeted": 400000,
                        "activity": -350000,
                        "to_be_budgeted": 100000,
                        "age_of_money": 45,
                        "deleted": False,
                    },
                    {
                        "month": "2025-12-01",
                        "note": None,
                        "income": 0,
                        "budgeted": 0,
                        "activity": 0,
                        "to_be_budgeted": 0,
                        "age_of_money": None,
                        "deleted": True,
                    },
                ]
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            months = await client.get_months(_VALID_UUID)

        assert len(months) == 1

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_months("bad-id")


class TestGetMonth:
    @pytest.mark.anyio
    async def test_returns_month_detail(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "month": {
                    "month": "2026-02-01",
                    "note": "Budget tight",
                    "income": 500000,
                    "budgeted": 400000,
                    "activity": -350000,
                    "to_be_budgeted": 100000,
                    "age_of_money": 45,
                    "deleted": False,
                    "categories": [
                        {
                            "id": "cat-1",
                            "name": "Groceries",
                            "budgeted": 200000,
                            "activity": -150000,
                            "balance": 50000,
                            "deleted": False,
                        },
                    ],
                }
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            detail = await client.get_month(
                _VALID_UUID, month="2026-02-01"
            )

        assert detail.month == "2026-02-01"
        assert detail.note == "Budget tight"
        assert len(detail.categories) == 1
        assert detail.categories[0].name == "Groceries"

    @pytest.mark.anyio
    async def test_current_month(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "month": {
                    "month": "2026-02-01",
                    "note": None,
                    "income": 0,
                    "budgeted": 0,
                    "activity": 0,
                    "to_be_budgeted": 0,
                    "age_of_money": None,
                    "deleted": False,
                    "categories": [],
                }
            }
        }
        with patch.object(
            client._client, "request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            await client.get_month(
                _VALID_UUID, month="current"
            )

        call_args = mock_req.call_args
        path = call_args[0][1]
        assert "/months/current" in path

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_month(
                "bad-id", month="2026-02-01"
            )


def _scheduled_txn_data(
    st_id: str = "st-1",
) -> dict[str, object]:
    """Build mock scheduled transaction data."""
    return {
        "id": st_id,
        "date_first": "2026-03-01",
        "date_next": "2026-04-01",
        "frequency": "monthly",
        "amount": -150000,
        "memo": "Rent",
        "flag_color": None,
        "account_id": _VALID_UUID,
        "account_name": "Checking",
        "payee_id": None,
        "payee_name": "Landlord",
        "category_id": None,
        "category_name": "Rent",
        "transfer_account_id": None,
        "subtransactions": [],
        "deleted": False,
    }


class TestGetScheduledTransactions:
    @pytest.mark.anyio
    async def test_returns_scheduled(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "scheduled_transactions": [
                    _scheduled_txn_data("st-1"),
                    _scheduled_txn_data("st-2"),
                ]
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_scheduled_transactions(
                _VALID_UUID
            )

        assert len(result) == 2
        assert result[0].id == "st-1"
        from decimal import Decimal
        assert result[0].amount == Decimal("-150")

    @pytest.mark.anyio
    async def test_filters_deleted(
        self, client: YNABClient
    ) -> None:
        deleted = _scheduled_txn_data("st-del")
        deleted["deleted"] = True
        mock_data: dict[str, object] = {
            "data": {
                "scheduled_transactions": [
                    _scheduled_txn_data("st-1"),
                    deleted,
                ]
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_scheduled_transactions(
                _VALID_UUID
            )

        assert len(result) == 1

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_scheduled_transactions("bad")


class TestGetScheduledTransaction:
    @pytest.mark.anyio
    async def test_returns_single(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "scheduled_transaction": (
                    _scheduled_txn_data(_VALID_UUID_2)
                )
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = (
                await client.get_scheduled_transaction(
                    _VALID_UUID, _VALID_UUID_2
                )
            )

        assert result.id == _VALID_UUID_2
        assert result.frequency == "monthly"

    @pytest.mark.anyio
    async def test_invalid_scheduled_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError,
            match="Invalid scheduled_transaction_id",
        ):
            await client.get_scheduled_transaction(
                _VALID_UUID, "bad-id"
            )


class TestCreateScheduledTransaction:
    @pytest.mark.anyio
    async def test_creates(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "scheduled_transaction": (
                    _scheduled_txn_data("st-new")
                )
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            write = ScheduledTransactionWrite(
                account_id=_VALID_UUID,
                date="2026-03-01",
                amount=-150000,
                frequency="monthly",
                payee_name="Landlord",
            )
            result = (
                await client.create_scheduled_transaction(
                    _VALID_UUID, write
                )
            )

        assert result.id == "st-new"
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        write = ScheduledTransactionWrite(
            account_id=_VALID_UUID,
            date="2026-03-01",
            amount=-150000,
            frequency="monthly",
        )
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.create_scheduled_transaction(
                "bad", write
            )


class TestUpdateScheduledTransaction:
    @pytest.mark.anyio
    async def test_updates(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "scheduled_transaction": (
                    _scheduled_txn_data(_VALID_UUID_2)
                )
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            update = ScheduledTransactionUpdate(
                amount=-200000,
            )
            result = (
                await client.update_scheduled_transaction(
                    _VALID_UUID, _VALID_UUID_2, update
                )
            )

        assert result.id == _VALID_UUID_2
        call_args = mock_req.call_args
        assert call_args[0][0] == "PUT"

    @pytest.mark.anyio
    async def test_invalid_scheduled_id(
        self, client: YNABClient
    ) -> None:
        update = ScheduledTransactionUpdate(amount=-200000)
        with pytest.raises(
            YNABError,
            match="Invalid scheduled_transaction_id",
        ):
            await client.update_scheduled_transaction(
                _VALID_UUID, "bad-id", update
            )


class TestDeleteScheduledTransaction:
    @pytest.mark.anyio
    async def test_deletes(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "scheduled_transaction": (
                    _scheduled_txn_data(_VALID_UUID_2)
                )
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            await client.delete_scheduled_transaction(
                _VALID_UUID, _VALID_UUID_2
            )

        call_args = mock_req.call_args
        assert call_args[0][0] == "DELETE"
        assert _VALID_UUID_2 in call_args[0][1]

    @pytest.mark.anyio
    async def test_invalid_scheduled_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError,
            match="Invalid scheduled_transaction_id",
        ):
            await client.delete_scheduled_transaction(
                _VALID_UUID, "bad-id"
            )

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.delete_scheduled_transaction(
                "bad", _VALID_UUID_2
            )


class TestGetUser:
    @pytest.mark.anyio
    async def test_returns_user(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {"user": {"id": "user-abc-123"}}
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_user()

        assert result.id == "user-abc-123"
        call_args = mock_req.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/user"


class TestGetBudgetSettings:
    @pytest.mark.anyio
    async def test_returns_settings(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "settings": {
                    "date_format": {"format": "MM/DD/YYYY"},
                    "currency_format": {
                        "iso_code": "USD",
                        "example_format": "123,456.78",
                        "decimal_digits": 2,
                        "decimal_separator": ".",
                        "symbol_first": True,
                        "group_separator": ",",
                        "currency_symbol": "$",
                        "display_symbol": True,
                    },
                }
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_budget_settings(
                _VALID_UUID
            )

        assert result.date_format.format == "MM/DD/YYYY"
        assert result.currency_format.iso_code == "USD"

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_budget_settings("bad")


def _account_detail_data(
    account_id: str,
) -> dict[str, object]:
    return {
        "id": account_id,
        "name": "Checking",
        "type": "checking",
        "balance": 15000,
        "cleared_balance": 12000,
        "closed": False,
        "deleted": False,
        "on_budget": True,
        "note": "Main account",
        "uncleared_balance": 3000,
        "transfer_payee_id": "payee-1",
    }


class TestGetAccount:
    @pytest.mark.anyio
    async def test_returns_detail(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "account": _account_detail_data(
                    _VALID_UUID_2
                )
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_account(
                _VALID_UUID, _VALID_UUID_2
            )

        assert result.id == _VALID_UUID_2
        assert result.on_budget is True
        assert result.note == "Main account"
        assert result.uncleared_balance == Decimal("3")

    @pytest.mark.anyio
    async def test_invalid_account_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid account_id"
        ):
            await client.get_account(_VALID_UUID, "bad-id")

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_account("bad", _VALID_UUID_2)


def _category_data(
    category_id: str,
) -> dict[str, object]:
    return {
        "id": category_id,
        "name": "Groceries",
        "category_group_id": "group-1",
        "budgeted": 500000,
        "activity": -250000,
        "balance": 250000,
        "note": "Weekly groceries",
        "hidden": False,
        "deleted": False,
    }


class TestGetCategory:
    @pytest.mark.anyio
    async def test_returns_category(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "category": _category_data(_VALID_UUID_2)
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_category(
                _VALID_UUID, _VALID_UUID_2
            )

        assert result.id == _VALID_UUID_2
        assert result.name == "Groceries"
        assert result.budgeted == Decimal("500")

    @pytest.mark.anyio
    async def test_invalid_category_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid category_id"
        ):
            await client.get_category(_VALID_UUID, "bad-id")

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_category("bad", _VALID_UUID_2)


class TestGetPayee:
    @pytest.mark.anyio
    async def test_returns_payee_detail(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "payee": {
                    "id": _VALID_UUID_2,
                    "name": "Costco",
                    "deleted": False,
                    "transfer_account_id": "acct-2",
                }
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_payee(
                _VALID_UUID, _VALID_UUID_2
            )

        assert result.id == _VALID_UUID_2
        assert result.name == "Costco"
        assert result.transfer_account_id == "acct-2"

    @pytest.mark.anyio
    async def test_invalid_payee_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid payee_id"
        ):
            await client.get_payee(_VALID_UUID, "bad-id")

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_payee("bad", _VALID_UUID_2)


def _transaction_data(
    transaction_id: str,
) -> dict[str, object]:
    return {
        "id": transaction_id,
        "account_id": "acct-1",
        "account_name": "Checking",
        "date": "2026-02-25",
        "amount": -42500,
        "payee_id": "payee-1",
        "payee_name": "Costco",
        "category_id": "cat-1",
        "category_name": "Groceries",
        "memo": "Weekly shop",
        "cleared": "cleared",
        "approved": True,
        "deleted": False,
    }


class TestGetTransaction:
    @pytest.mark.anyio
    async def test_returns_transaction(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "transaction": _transaction_data(
                    _VALID_UUID_2
                )
            }
        }
        with patch.object(
            client._client, "request",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = _mock_response(
                200, mock_data
            )
            result = await client.get_transaction(
                _VALID_UUID, _VALID_UUID_2
            )

        assert result.id == _VALID_UUID_2
        assert result.amount == Decimal("-42.5")
        assert result.payee_name == "Costco"

    @pytest.mark.anyio
    async def test_invalid_transaction_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid transaction_id"
        ):
            await client.get_transaction(
                _VALID_UUID, "bad-id"
            )

    @pytest.mark.anyio
    async def test_invalid_budget_id(
        self, client: YNABClient
    ) -> None:
        with pytest.raises(
            YNABError, match="Invalid budget_id"
        ):
            await client.get_transaction(
                "bad", _VALID_UUID_2
            )
