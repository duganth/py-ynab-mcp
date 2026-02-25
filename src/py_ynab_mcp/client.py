"""YNAB API client."""

import os
import re

import httpx
from pydantic import ValidationError

from py_ynab_mcp.models import (
    Account,
    AccountsResponse,
    BudgetSummary,
    BudgetSummaryResponse,
)

YNAB_BASE_URL = "https://api.ynab.com/v1"

_BUDGET_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    r"|^last-used$"
)


class YNABError(Exception):
    """Error from YNAB API."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"YNAB API error ({status_code}): {detail}")


class YNABClient:
    """Async client for the YNAB API."""

    def __init__(self, access_token: str | None = None) -> None:
        token = access_token or os.environ.get("YNAB_ACCESS_TOKEN")
        if not token:
            raise ValueError(
                "YNAB access token required. "
                "Set YNAB_ACCESS_TOKEN environment variable "
                "or pass access_token."
            )
        self._client = httpx.AsyncClient(
            base_url=YNAB_BASE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    async def _request(
        self, method: str, path: str
    ) -> dict[str, object]:
        """Make an authenticated request to the YNAB API."""
        try:
            response = await self._client.request(method, path)
        except httpx.HTTPError:
            raise YNABError(
                0, "Network error communicating with YNAB"
            ) from None

        if response.status_code == 401:
            raise YNABError(401, "Invalid access token")
        if response.status_code == 429:
            raise YNABError(
                429, "Rate limited — try again later"
            )
        if response.status_code >= 400:
            try:
                detail = (
                    response.json()
                    .get("error", {})
                    .get("detail", "Unknown error")
                )
            except Exception:
                detail = f"HTTP {response.status_code}"
            raise YNABError(response.status_code, detail)

        try:
            data: dict[str, object] = response.json().get(
                "data", {}
            )
        except Exception:
            raise YNABError(
                0, "Invalid response from YNAB API"
            ) from None
        return data

    async def get_budgets(self) -> list[BudgetSummary]:
        """List all budgets."""
        data = await self._request("GET", "/budgets")
        try:
            parsed = BudgetSummaryResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.budgets

    async def get_accounts(
        self, budget_id: str = "last-used"
    ) -> list[Account]:
        """List accounts for a budget."""
        if not _BUDGET_ID_RE.match(budget_id):
            raise YNABError(
                400, "Invalid budget_id format"
            )
        data = await self._request(
            "GET", f"/budgets/{budget_id}/accounts"
        )
        try:
            parsed = AccountsResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return [
            a for a in parsed.accounts
            if not a.deleted and not a.closed
        ]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
