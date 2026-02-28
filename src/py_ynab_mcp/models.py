"""Pydantic models for YNAB API responses."""

from decimal import Decimal

from pydantic import BaseModel, field_validator


def milliunits_to_dollars(milliunits: int) -> Decimal:
    """Convert YNAB milliunits to dollar amount.

    YNAB stores amounts as milliunits: $10.00 = 10000.
    """
    return Decimal(milliunits) / Decimal(1000)


def dollars_to_milliunits(dollars: Decimal) -> int:
    """Convert dollar amount to YNAB milliunits.

    $10.00 = 10000 milliunits.
    """
    return int(dollars * Decimal(1000))


# --- Account models ---


class Account(BaseModel):
    """A YNAB account."""

    id: str
    name: str
    type: str
    balance: Decimal
    cleared_balance: Decimal
    closed: bool
    deleted: bool

    @field_validator("balance", "cleared_balance", mode="before")
    @classmethod
    def convert_milliunits(cls, v: int | Decimal) -> Decimal:
        if isinstance(v, int):
            return milliunits_to_dollars(v)
        return v


class AccountsResponse(BaseModel):
    """Wrapper for YNAB accounts endpoint response."""

    accounts: list[Account]


class BudgetSummary(BaseModel):
    """A YNAB budget summary."""

    id: str
    name: str
    last_modified_on: str
    first_month: str
    last_month: str


class BudgetSummaryResponse(BaseModel):
    """Wrapper for YNAB budgets endpoint response."""

    budgets: list[BudgetSummary]


# --- Transaction models ---


class TransactionWrite(BaseModel):
    """Request model for creating a transaction."""

    account_id: str
    date: str
    amount: int  # milliunits
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    memo: str | None = None
    cleared: str | None = None
    approved: bool | None = None
    flag_color: str | None = None
    import_id: str | None = None


class TransactionUpdate(BaseModel):
    """Request model for updating a transaction (partial, includes ID)."""

    id: str
    account_id: str | None = None
    date: str | None = None
    amount: int | None = None
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    memo: str | None = None
    cleared: str | None = None
    approved: bool | None = None
    flag_color: str | None = None


class Transaction(BaseModel):
    """A YNAB transaction (response model)."""

    id: str
    account_id: str
    account_name: str
    date: str
    amount: Decimal
    payee_id: str | None
    payee_name: str | None
    category_id: str | None
    category_name: str | None
    memo: str | None
    cleared: str
    approved: bool
    deleted: bool

    @field_validator("amount", mode="before")
    @classmethod
    def convert_milliunits(cls, v: int | Decimal) -> Decimal:
        if isinstance(v, int):
            return milliunits_to_dollars(v)
        return v


class TransactionResponse(BaseModel):
    """Wrapper for single transaction endpoint response."""

    transaction: Transaction


class TransactionsResponse(BaseModel):
    """Wrapper for multiple transactions endpoint response."""

    transactions: list[Transaction]


class BulkResult(BaseModel):
    """Result of a bulk transaction create."""

    transaction_ids: list[str]
    duplicate_import_ids: list[str]


class BulkCreateResponse(BaseModel):
    """Wrapper for bulk create endpoint response."""

    bulk: BulkResult


# --- Category models ---


class Category(BaseModel):
    """A YNAB category."""

    id: str
    name: str
    budgeted: Decimal
    activity: Decimal
    balance: Decimal
    deleted: bool

    @field_validator("budgeted", "activity", "balance", mode="before")
    @classmethod
    def convert_milliunits(cls, v: int | Decimal) -> Decimal:
        if isinstance(v, int):
            return milliunits_to_dollars(v)
        return v


class CategoryGroup(BaseModel):
    """A YNAB category group with its categories."""

    id: str
    name: str
    categories: list[Category]
    deleted: bool


class CategoriesResponse(BaseModel):
    """Wrapper for categories endpoint response."""

    category_groups: list[CategoryGroup]


# --- Payee models ---


class Payee(BaseModel):
    """A YNAB payee."""

    id: str
    name: str
    deleted: bool


class PayeesResponse(BaseModel):
    """Wrapper for payees endpoint response."""

    payees: list[Payee]
