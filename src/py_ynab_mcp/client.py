"""YNAB API client."""

import os
import re

import httpx
from pydantic import ValidationError

from py_ynab_mcp.models import (
    Account,
    AccountDetail,
    AccountDetailResponse,
    AccountsResponse,
    BudgetSettings,
    BudgetSettingsResponse,
    BudgetSummary,
    BudgetSummaryResponse,
    BulkCreateResponse,
    BulkResult,
    CategoriesResponse,
    Category,
    CategoryBudgetWrite,
    CategoryGroup,
    CategoryResponse,
    CategoryUpdate,
    MonthDetail,
    MonthDetailResponse,
    MonthsResponse,
    MonthSummary,
    Payee,
    PayeeDetail,
    PayeeDetailResponse,
    PayeesResponse,
    ScheduledTransaction,
    ScheduledTransactionResponse,
    ScheduledTransactionsResponse,
    ScheduledTransactionUpdate,
    ScheduledTransactionWrite,
    Transaction,
    TransactionResponse,
    TransactionsResponse,
    TransactionUpdate,
    TransactionWrite,
    User,
    UserResponse,
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
        params: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Make an authenticated request to the YNAB API."""
        try:
            response = await self._client.request(
                method, path, json=json, params=params
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

    async def get_months(
        self, budget_id: str = "last-used"
    ) -> list[MonthSummary]:
        """List budget months."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "GET", f"/budgets/{budget_id}/months"
        )
        try:
            parsed = MonthsResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return [m for m in parsed.months if not m.deleted]

    async def get_month(
        self, budget_id: str = "last-used", *, month: str
    ) -> MonthDetail:
        """Get a single budget month with category breakdowns."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "GET", f"/budgets/{budget_id}/months/{month}"
        )
        try:
            parsed = MonthDetailResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.month

    async def get_transactions(
        self,
        budget_id: str = "last-used",
        *,
        since_date: str,
        account_id: str | None = None,
        category_id: str | None = None,
        payee_id: str | None = None,
        type: str | None = None,
    ) -> list[Transaction]:
        """List transactions with optional filters.

        Exactly one of account_id, category_id, payee_id may be
        provided to filter by that dimension. All accept since_date
        and type as additional filters.
        """
        self._validate_budget_id(budget_id)
        filters = [
            f for f in (account_id, category_id, payee_id)
            if f is not None
        ]
        if len(filters) > 1:
            raise ValueError(
                "At most one of account_id, category_id, "
                "payee_id may be provided."
            )

        # Build the endpoint path based on which filter is set.
        if account_id:
            if not _UUID_RE.match(account_id):
                raise YNABError(
                    400, "Invalid account_id format"
                )
            path = (
                f"/budgets/{budget_id}"
                f"/accounts/{account_id}/transactions"
            )
        elif category_id:
            if not _UUID_RE.match(category_id):
                raise YNABError(
                    400, "Invalid category_id format"
                )
            path = (
                f"/budgets/{budget_id}"
                f"/categories/{category_id}/transactions"
            )
        elif payee_id:
            if not _UUID_RE.match(payee_id):
                raise YNABError(
                    400, "Invalid payee_id format"
                )
            path = (
                f"/budgets/{budget_id}"
                f"/payees/{payee_id}/transactions"
            )
        else:
            path = f"/budgets/{budget_id}/transactions"

        params: dict[str, str] = {"since_date": since_date}
        if type:
            params["type"] = type

        data = await self._request(
            "GET", path, params=params
        )
        try:
            parsed = TransactionsResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return [
            t for t in parsed.transactions if not t.deleted
        ]

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

    def _validate_account_id(self, account_id: str) -> None:
        if not _UUID_RE.match(account_id):
            raise YNABError(400, "Invalid account_id format")

    def _validate_category_id(self, category_id: str) -> None:
        if not _UUID_RE.match(category_id):
            raise YNABError(400, "Invalid category_id format")

    def _validate_payee_id(self, payee_id: str) -> None:
        if not _UUID_RE.match(payee_id):
            raise YNABError(400, "Invalid payee_id format")

    async def update_category_budget(
        self,
        budget_id: str,
        month: str,
        category_id: str,
        budget_write: CategoryBudgetWrite,
    ) -> Category:
        """Update the budgeted amount for a category in a month."""
        self._validate_budget_id(budget_id)
        self._validate_category_id(category_id)
        data = await self._request(
            "PATCH",
            f"/budgets/{budget_id}/months/{month}"
            f"/categories/{category_id}",
            json={"category": budget_write.model_dump()},
        )
        try:
            parsed = CategoryResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.category

    async def update_category(
        self,
        budget_id: str,
        category_id: str,
        update: CategoryUpdate,
    ) -> Category:
        """Update category metadata."""
        self._validate_budget_id(budget_id)
        self._validate_category_id(category_id)
        data = await self._request(
            "PATCH",
            f"/budgets/{budget_id}/categories/{category_id}",
            json={"category": update.model_dump(
                exclude_none=True
            )},
        )
        try:
            parsed = CategoryResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.category

    def _validate_scheduled_transaction_id(
        self, scheduled_transaction_id: str
    ) -> None:
        if not _UUID_RE.match(scheduled_transaction_id):
            raise YNABError(
                400,
                "Invalid scheduled_transaction_id format",
            )

    async def get_scheduled_transactions(
        self, budget_id: str = "last-used"
    ) -> list[ScheduledTransaction]:
        """List scheduled transactions for a budget."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "GET",
            f"/budgets/{budget_id}/scheduled_transactions",
        )
        try:
            parsed = (
                ScheduledTransactionsResponse.model_validate(
                    data
                )
            )
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return [
            st
            for st in parsed.scheduled_transactions
            if not st.deleted
        ]

    async def get_scheduled_transaction(
        self,
        budget_id: str,
        scheduled_transaction_id: str,
    ) -> ScheduledTransaction:
        """Get a single scheduled transaction."""
        self._validate_budget_id(budget_id)
        self._validate_scheduled_transaction_id(
            scheduled_transaction_id
        )
        data = await self._request(
            "GET",
            f"/budgets/{budget_id}"
            f"/scheduled_transactions"
            f"/{scheduled_transaction_id}",
        )
        try:
            parsed = (
                ScheduledTransactionResponse.model_validate(
                    data
                )
            )
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.scheduled_transaction

    async def create_scheduled_transaction(
        self,
        budget_id: str,
        transaction: ScheduledTransactionWrite,
    ) -> ScheduledTransaction:
        """Create a scheduled transaction."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "POST",
            f"/budgets/{budget_id}/scheduled_transactions",
            json={
                "scheduled_transaction": (
                    transaction.model_dump(exclude_none=True)
                )
            },
        )
        try:
            parsed = (
                ScheduledTransactionResponse.model_validate(
                    data
                )
            )
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.scheduled_transaction

    async def update_scheduled_transaction(
        self,
        budget_id: str,
        scheduled_transaction_id: str,
        update: ScheduledTransactionUpdate,
    ) -> ScheduledTransaction:
        """Update a scheduled transaction."""
        self._validate_budget_id(budget_id)
        self._validate_scheduled_transaction_id(
            scheduled_transaction_id
        )
        data = await self._request(
            "PUT",
            f"/budgets/{budget_id}"
            f"/scheduled_transactions"
            f"/{scheduled_transaction_id}",
            json={
                "scheduled_transaction": (
                    update.model_dump(exclude_none=True)
                )
            },
        )
        try:
            parsed = (
                ScheduledTransactionResponse.model_validate(
                    data
                )
            )
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.scheduled_transaction

    async def delete_scheduled_transaction(
        self,
        budget_id: str,
        scheduled_transaction_id: str,
    ) -> None:
        """Delete a scheduled transaction."""
        self._validate_budget_id(budget_id)
        self._validate_scheduled_transaction_id(
            scheduled_transaction_id
        )
        await self._request(
            "DELETE",
            f"/budgets/{budget_id}"
            f"/scheduled_transactions"
            f"/{scheduled_transaction_id}",
        )

    async def get_user(self) -> User:
        """Get the authenticated user."""
        data = await self._request("GET", "/user")
        try:
            parsed = UserResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.user

    async def get_budget_settings(
        self, budget_id: str = "last-used"
    ) -> BudgetSettings:
        """Get budget settings (date/currency format)."""
        self._validate_budget_id(budget_id)
        data = await self._request(
            "GET", f"/budgets/{budget_id}/settings"
        )
        try:
            parsed = BudgetSettingsResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.settings

    async def get_account(
        self, budget_id: str, account_id: str
    ) -> AccountDetail:
        """Get a single account with full detail."""
        self._validate_budget_id(budget_id)
        self._validate_account_id(account_id)
        data = await self._request(
            "GET",
            f"/budgets/{budget_id}/accounts/{account_id}",
        )
        try:
            parsed = AccountDetailResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.account

    async def get_category(
        self, budget_id: str, category_id: str
    ) -> Category:
        """Get a single category."""
        self._validate_budget_id(budget_id)
        self._validate_category_id(category_id)
        data = await self._request(
            "GET",
            f"/budgets/{budget_id}/categories/{category_id}",
        )
        try:
            parsed = CategoryResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.category

    async def get_payee(
        self, budget_id: str, payee_id: str
    ) -> PayeeDetail:
        """Get a single payee with full detail."""
        self._validate_budget_id(budget_id)
        self._validate_payee_id(payee_id)
        data = await self._request(
            "GET",
            f"/budgets/{budget_id}/payees/{payee_id}",
        )
        try:
            parsed = PayeeDetailResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.payee

    async def get_transaction(
        self, budget_id: str, transaction_id: str
    ) -> Transaction:
        """Get a single transaction."""
        self._validate_budget_id(budget_id)
        self._validate_transaction_id(transaction_id)
        data = await self._request(
            "GET",
            f"/budgets/{budget_id}/transactions/{transaction_id}",
        )
        try:
            parsed = TransactionResponse.model_validate(data)
        except ValidationError:
            raise YNABError(
                0, "Unexpected response format from YNAB API"
            ) from None
        return parsed.transaction

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
