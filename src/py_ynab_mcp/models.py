"""Pydantic models for YNAB API responses."""

from decimal import Decimal

from pydantic import BaseModel, field_validator


def milliunits_to_dollars(milliunits: int) -> Decimal:
    """Convert YNAB milliunits to dollar amount.

    YNAB stores amounts as milliunits: $10.00 = 10000.
    """
    return Decimal(milliunits) / Decimal(1000)


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


class BudgetSummaryResponse(BaseModel):
    """Wrapper for YNAB budgets endpoint response."""

    budgets: list[BudgetSummary]
