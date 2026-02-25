"""Tests for YNAB API client."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from py_ynab_mcp.client import YNABClient, YNABError


@pytest.fixture
def client() -> YNABClient:
    return YNABClient(access_token="test-token")


def _mock_response(
    status_code: int = 200,
    json_data: dict[str, object] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request(
            "GET", "https://api.ynab.com/v1/test"
        ),
    )


_VALID_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


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


class TestGetBudgets:
    @pytest.mark.anyio
    async def test_returns_budgets(
        self, client: YNABClient
    ) -> None:
        mock_data: dict[str, object] = {
            "data": {
                "budgets": [
                    {"id": "budget-1", "name": "My Budget"},
                    {"id": "budget-2", "name": "Joint Budget"},
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
