"""Tests for Pydantic models and milliunit conversion."""

from decimal import Decimal

from py_ynab_mcp.models import Account, milliunits_to_dollars


class TestMilliunitsConversion:
    def test_positive_amount(self) -> None:
        assert milliunits_to_dollars(10000) == Decimal("10")

    def test_zero(self) -> None:
        assert milliunits_to_dollars(0) == Decimal("0")

    def test_negative_amount(self) -> None:
        assert milliunits_to_dollars(-5500) == Decimal("-5.5")

    def test_fractional_cents(self) -> None:
        # 1234 milliunits = $1.234
        assert milliunits_to_dollars(1234) == Decimal("1.234")

    def test_large_amount(self) -> None:
        # $100,000.00 = 100_000_000 milliunits
        assert milliunits_to_dollars(100_000_000) == Decimal("100000")


class TestAccountModel:
    def test_balance_conversion_from_milliunits(self) -> None:
        acct = Account(
            id="abc-123",
            name="Checking",
            type="checking",
            balance=15000,  # type: ignore[arg-type]
            cleared_balance=12000,  # type: ignore[arg-type]
            closed=False,
            deleted=False,
        )
        assert acct.balance == Decimal("15")
        assert acct.cleared_balance == Decimal("12")

    def test_balance_accepts_decimal(self) -> None:
        acct = Account(
            id="abc-123",
            name="Savings",
            type="savings",
            balance=Decimal("100.50"),
            cleared_balance=Decimal("100.50"),
            closed=False,
            deleted=False,
        )
        assert acct.balance == Decimal("100.50")
