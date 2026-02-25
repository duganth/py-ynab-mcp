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
    BulkCreateResponse,
    BulkResult,
    CategoriesResponse,
    CategoryGroup,
    Payee,
    PayeesResponse,
    Transaction,
    TransactionResponse,
    TransactionsResponse,
    TransactionUpdate,
    TransactionWrite,
)

YNAB_BASE_URL = "https://api.ynab.com/v1"

_BUDGET_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    r"|^last-used$"
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
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
        self._rate_limit_remaining: int | None = None

    @property
    def rate_limit_remaining(self) -> int | None:
        """Remaining API requests this period, or None if unknown."""
        return self._rate_limit_remaining

    def _validate_budget_id(self, budget_id: str) -> None:
        if not _BUDGET_ID_RE.match(budget_id):
            raise YNABError(400, "Invalid budget_id format")

    def _validate_transaction_id(self, transaction_id: str) -> None:
        if not _UUID_RE.match(transaction_id):
            raise YNABError(400, "Invalid transaction_id format")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Make an authenticated request to the YNAB API."""
        try:
            response = await self._client.request(
                method, path, json=json
            )
        except httpx.HTTPError:
            raise YNABError(
                0, "Network error communicating with YNAB"
            ) from None

        # Track rate limit from response headers.
        # YNAB format: "used/total" (e.g. "36/200") or plain int.
        rate_header = response.headers.get("x-rate-limit")
        if rate_header is not None:
            try:
                if "/" in rate_header:
                    used, total = rate_header.split("/", 1)
                    self._rate_limit_remaining = (
                        int(total) - int(used)
                    )
                else:
                    self._rate_limit_remaining = int(rate_header)
            except ValueError:
                pass

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
        self._validate_budget_id(budget_id)
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

    async def get_categories(
        self, budget_id: str = "last-used"
    ) -> list[CategoryGroup]:
        """List category groups for a budget."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "GET", f"/budgets/{budget_id}/categories"
        )
        try:
            parsed = CategoriesResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return [
            CategoryGroup(
                id=g.id,
                name=g.name,
                deleted=g.deleted,
                categories=[
                    c for c in g.categories
                    if not c.deleted
                ],
            )
            for g in parsed.category_groups
            if not g.deleted
        ]

    async def get_payees(
        self, budget_id: str = "last-used"
    ) -> list[Payee]:
        """List payees for a budget."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "GET", f"/budgets/{budget_id}/payees"
        )
        try:
            parsed = PayeesResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return [p for p in parsed.payees if not p.deleted]

    async def create_transaction(
        self,
        budget_id: str,
        transaction: TransactionWrite,
    ) -> Transaction:
        """Create a single transaction."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "POST",
            f"/budgets/{budget_id}/transactions",
            json={"transaction": transaction.model_dump(
                exclude_none=True
            )},
        )
        try:
            parsed = TransactionResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.transaction

    async def create_transactions(
        self,
        budget_id: str,
        transactions: list[TransactionWrite],
    ) -> BulkResult:
        """Create multiple transactions in bulk."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "POST",
            f"/budgets/{budget_id}/transactions",
            json={"transactions": [
                t.model_dump(exclude_none=True)
                for t in transactions
            ]},
        )
        try:
            parsed = BulkCreateResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.bulk

    async def update_transaction(
        self,
        budget_id: str,
        transaction: TransactionUpdate,
    ) -> Transaction:
        """Update a single transaction (via bulk PATCH endpoint)."""
        results = await self.update_transactions(
            budget_id, [transaction]
        )
        if not results:
            raise YNABError(
                0, "No transaction returned after update"
            )
        return results[0]

    async def update_transactions(
        self,
        budget_id: str,
        transactions: list[TransactionUpdate],
    ) -> list[Transaction]:
        """Update multiple transactions in bulk."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "PATCH",
            f"/budgets/{budget_id}/transactions",
            json={"transactions": [
                t.model_dump(exclude_none=True)
                for t in transactions
            ]},
        )
        try:
            parsed = TransactionsResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.transactions

    async def delete_transaction(
        self,
        budget_id: str,
        transaction_id: str,
    ) -> None:
        """Delete a transaction."""
        self._validate_budget_id(budget_id)
        self._validate_transaction_id(transaction_id)
        await self._request(
            "DELETE",
            f"/budgets/{budget_id}/transactions/{transaction_id}",
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
