"""Tests for Pydantic models and milliunit conversion."""

from decimal import Decimal

from py_ynab_mcp.models import (
    Account,
    AccountDetail,
    BudgetSettings,
    BudgetSummary,
    Category,
    CategoryBudgetWrite,
    CategoryUpdate,
    CurrencyFormat,
    DateFormat,
    MonthDetail,
    MonthSummary,
    Payee,
    PayeeDetail,
    ScheduledSubTransaction,
    ScheduledTransaction,
    ScheduledTransactionUpdate,
    ScheduledTransactionWrite,
    Transaction,
    TransactionUpdate,
    TransactionWrite,
    User,
    dollars_to_milliunits,
    milliunits_to_dollars,
)


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


class TestDollarsToMilliunits:
    def test_positive_amount(self) -> None:
        assert dollars_to_milliunits(Decimal("10")) == 10000

    def test_zero(self) -> None:
        assert dollars_to_milliunits(Decimal("0")) == 0

    def test_negative_amount(self) -> None:
        assert dollars_to_milliunits(Decimal("-5.50")) == -5500

    def test_cents(self) -> None:
        assert dollars_to_milliunits(Decimal("42.50")) == 42500

    def test_fractional_cents(self) -> None:
        assert dollars_to_milliunits(Decimal("1.234")) == 1234

    def test_large_amount(self) -> None:
        assert dollars_to_milliunits(Decimal("100000")) == 100_000_000

    def test_roundtrip(self) -> None:
        """dollars_to_milliunits(milliunits_to_dollars(x)) == x"""
        for v in [0, 1, -1, 10000, -5500, 1234, 100_000_000]:
            assert dollars_to_milliunits(
                milliunits_to_dollars(v)
            ) == v


class TestBudgetSummaryModel:
    def test_all_fields(self) -> None:
        b = BudgetSummary(
            id="abc-123",
            name="My Budget",
            last_modified_on="2026-02-28T12:00:00+00:00",
            first_month="2024-01-01",
            last_month="2026-02-01",
        )
        assert b.id == "abc-123"
        assert b.name == "My Budget"
        assert b.last_modified_on == "2026-02-28T12:00:00+00:00"
        assert b.first_month == "2024-01-01"
        assert b.last_month == "2026-02-01"


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


class TestTransactionModel:
    def test_amount_conversion_from_milliunits(self) -> None:
        txn = Transaction(
            id="txn-1",
            account_id="acct-1",
            account_name="Checking",
            date="2026-02-25",
            amount=-42500,  # type: ignore[arg-type]
            payee_id=None,
            payee_name="Costco",
            category_id=None,
            category_name="Groceries",
            memo="Weekly shop",
            cleared="cleared",
            approved=True,
            deleted=False,
        )
        assert txn.amount == Decimal("-42.5")

    def test_amount_accepts_decimal(self) -> None:
        txn = Transaction(
            id="txn-1",
            account_id="acct-1",
            account_name="Checking",
            date="2026-02-25",
            amount=Decimal("100.00"),
            payee_id=None,
            payee_name=None,
            category_id=None,
            category_name=None,
            memo=None,
            cleared="uncleared",
            approved=False,
            deleted=False,
        )
        assert txn.amount == Decimal("100.00")


class TestTransactionWriteModel:
    def test_required_fields(self) -> None:
        txn = TransactionWrite(
            account_id="acct-1",
            date="2026-02-25",
            amount=-42500,
        )
        assert txn.account_id == "acct-1"
        assert txn.amount == -42500
        assert txn.payee_name is None

    def test_optional_fields(self) -> None:
        txn = TransactionWrite(
            account_id="acct-1",
            date="2026-02-25",
            amount=-42500,
            payee_name="Costco",
            memo="Groceries",
            cleared="cleared",
        )
        assert txn.payee_name == "Costco"
        assert txn.memo == "Groceries"

    def test_exclude_none_dump(self) -> None:
        txn = TransactionWrite(
            account_id="acct-1",
            date="2026-02-25",
            amount=-42500,
        )
        dumped = txn.model_dump(exclude_none=True)
        assert "payee_name" not in dumped
        assert "memo" not in dumped
        assert dumped["account_id"] == "acct-1"


class TestTransactionUpdateModel:
    def test_only_id_required(self) -> None:
        update = TransactionUpdate(id="txn-1")
        assert update.id == "txn-1"
        assert update.amount is None
        assert update.memo is None

    def test_partial_fields(self) -> None:
        update = TransactionUpdate(
            id="txn-1",
            memo="Updated memo",
            amount=-10000,
        )
        dumped = update.model_dump(exclude_none=True)
        assert dumped == {
            "id": "txn-1",
            "memo": "Updated memo",
            "amount": -10000,
        }


class TestCategoryModel:
    def test_milliunit_conversion(self) -> None:
        cat = Category(
            id="cat-1",
            name="Groceries",
            budgeted=500000,  # type: ignore[arg-type]
            activity=-250000,  # type: ignore[arg-type]
            balance=250000,  # type: ignore[arg-type]
            deleted=False,
        )
        assert cat.budgeted == Decimal("500")
        assert cat.activity == Decimal("-250")
        assert cat.balance == Decimal("250")

    def test_optional_fields(self) -> None:
        cat = Category(
            id="cat-1",
            name="Groceries",
            category_group_id="group-1",
            budgeted=Decimal("500"),
            activity=Decimal("-250"),
            balance=Decimal("250"),
            note="Weekly groceries",
            hidden=True,
            deleted=False,
        )
        assert cat.category_group_id == "group-1"
        assert cat.note == "Weekly groceries"
        assert cat.hidden is True

    def test_optional_fields_default(self) -> None:
        cat = Category(
            id="cat-1",
            name="Groceries",
            budgeted=Decimal("0"),
            activity=Decimal("0"),
            balance=Decimal("0"),
            deleted=False,
        )
        assert cat.category_group_id is None
        assert cat.note is None
        assert cat.hidden is False


class TestCategoryBudgetWriteModel:
    def test_budgeted_field(self) -> None:
        w = CategoryBudgetWrite(budgeted=500000)
        assert w.budgeted == 500000
        assert w.model_dump() == {"budgeted": 500000}


class TestCategoryUpdateModel:
    def test_all_fields(self) -> None:
        u = CategoryUpdate(
            name="Restaurants", note="Eating out", hidden=False
        )
        dumped = u.model_dump(exclude_none=True)
        assert dumped == {
            "name": "Restaurants",
            "note": "Eating out",
            "hidden": False,
        }

    def test_partial_fields(self) -> None:
        u = CategoryUpdate(name="Restaurants")
        dumped = u.model_dump(exclude_none=True)
        assert dumped == {"name": "Restaurants"}
        assert "note" not in dumped
        assert "hidden" not in dumped


class TestMonthSummaryModel:
    def test_milliunit_conversion(self) -> None:
        m = MonthSummary(
            month="2026-02-01",
            note=None,
            income=500000,  # type: ignore[arg-type]
            budgeted=400000,  # type: ignore[arg-type]
            activity=-350000,  # type: ignore[arg-type]
            to_be_budgeted=100000,  # type: ignore[arg-type]
            age_of_money=45,
            deleted=False,
        )
        assert m.income == Decimal("500")
        assert m.budgeted == Decimal("400")
        assert m.activity == Decimal("-350")
        assert m.to_be_budgeted == Decimal("100")

    def test_optional_fields(self) -> None:
        m = MonthSummary(
            month="2026-02-01",
            note="Test note",
            income=Decimal("0"),
            budgeted=Decimal("0"),
            activity=Decimal("0"),
            to_be_budgeted=Decimal("0"),
            age_of_money=None,
            deleted=False,
        )
        assert m.note == "Test note"
        assert m.age_of_money is None

    def test_accepts_decimal(self) -> None:
        m = MonthSummary(
            month="2026-02-01",
            note=None,
            income=Decimal("1000.50"),
            budgeted=Decimal("800"),
            activity=Decimal("-700"),
            to_be_budgeted=Decimal("200.50"),
            age_of_money=30,
            deleted=False,
        )
        assert m.income == Decimal("1000.50")


class TestMonthDetailModel:
    def test_inherits_summary_fields(self) -> None:
        cat = Category(
            id="cat-1",
            name="Groceries",
            budgeted=Decimal("500"),
            activity=Decimal("-250"),
            balance=Decimal("250"),
            deleted=False,
        )
        d = MonthDetail(
            month="2026-02-01",
            note=None,
            income=500000,  # type: ignore[arg-type]
            budgeted=400000,  # type: ignore[arg-type]
            activity=-350000,  # type: ignore[arg-type]
            to_be_budgeted=100000,  # type: ignore[arg-type]
            age_of_money=45,
            deleted=False,
            categories=[cat],
        )
        assert d.income == Decimal("500")
        assert len(d.categories) == 1
        assert d.categories[0].name == "Groceries"

    def test_empty_categories(self) -> None:
        d = MonthDetail(
            month="2026-02-01",
            note=None,
            income=Decimal("0"),
            budgeted=Decimal("0"),
            activity=Decimal("0"),
            to_be_budgeted=Decimal("0"),
            age_of_money=None,
            deleted=False,
            categories=[],
        )
        assert d.categories == []


class TestPayeeModel:
    def test_basic_payee(self) -> None:
        payee = Payee(
            id="payee-1",
            name="Costco",
            deleted=False,
        )
        assert payee.name == "Costco"
        assert not payee.deleted


class TestScheduledSubTransactionModel:
    def test_milliunit_conversion(self) -> None:
        sub = ScheduledSubTransaction(
            id="sub-1",
            scheduled_transaction_id="st-1",
            amount=-25000,  # type: ignore[arg-type]
            memo="Half",
            payee_id=None,
            category_id="cat-1",
            transfer_account_id=None,
            deleted=False,
        )
        assert sub.amount == Decimal("-25")

    def test_optional_fields_none(self) -> None:
        sub = ScheduledSubTransaction(
            id="sub-1",
            scheduled_transaction_id="st-1",
            amount=Decimal("-25"),
            memo=None,
            payee_id=None,
            category_id=None,
            transfer_account_id=None,
            deleted=False,
        )
        assert sub.memo is None
        assert sub.category_id is None


class TestScheduledTransactionModel:
    def test_milliunit_conversion(self) -> None:
        st = ScheduledTransaction(
            id="st-1",
            date_first="2026-03-01",
            date_next="2026-04-01",
            frequency="monthly",
            amount=-150000,  # type: ignore[arg-type]
            memo=None,
            flag_color=None,
            account_id="acct-1",
            account_name="Checking",
            payee_id=None,
            payee_name="Landlord",
            category_id=None,
            category_name="Rent",
            transfer_account_id=None,
            subtransactions=[],
            deleted=False,
        )
        assert st.amount == Decimal("-150")

    def test_with_subtransactions(self) -> None:
        sub = ScheduledSubTransaction(
            id="sub-1",
            scheduled_transaction_id="st-1",
            amount=Decimal("-50"),
            memo="Part 1",
            payee_id=None,
            category_id=None,
            transfer_account_id=None,
            deleted=False,
        )
        st = ScheduledTransaction(
            id="st-1",
            date_first="2026-03-01",
            date_next="2026-04-01",
            frequency="monthly",
            amount=Decimal("-100"),
            memo=None,
            flag_color="blue",
            account_id="acct-1",
            account_name="Checking",
            payee_id=None,
            payee_name=None,
            category_id=None,
            category_name=None,
            transfer_account_id=None,
            subtransactions=[sub],
            deleted=False,
        )
        assert len(st.subtransactions) == 1
        assert st.flag_color == "blue"


class TestScheduledTransactionWriteModel:
    def test_required_fields(self) -> None:
        w = ScheduledTransactionWrite(
            account_id="acct-1",
            date="2026-03-01",
            amount=-150000,
            frequency="monthly",
        )
        assert w.frequency == "monthly"
        assert w.payee_name is None

    def test_exclude_none_dump(self) -> None:
        w = ScheduledTransactionWrite(
            account_id="acct-1",
            date="2026-03-01",
            amount=-150000,
            frequency="monthly",
        )
        dumped = w.model_dump(exclude_none=True)
        assert "payee_name" not in dumped
        assert "memo" not in dumped
        assert dumped["frequency"] == "monthly"

    def test_optional_fields(self) -> None:
        w = ScheduledTransactionWrite(
            account_id="acct-1",
            date="2026-03-01",
            amount=-150000,
            frequency="monthly",
            payee_name="Landlord",
            memo="Rent",
        )
        assert w.payee_name == "Landlord"
        assert w.memo == "Rent"


class TestScheduledTransactionUpdateModel:
    def test_all_optional(self) -> None:
        u = ScheduledTransactionUpdate()
        dumped = u.model_dump(exclude_none=True)
        assert dumped == {}

    def test_partial_fields(self) -> None:
        u = ScheduledTransactionUpdate(
            amount=-200000,
            frequency="weekly",
        )
        dumped = u.model_dump(exclude_none=True)
        assert dumped == {
            "amount": -200000,
            "frequency": "weekly",
        }


class TestUserModel:
    def test_basic(self) -> None:
        user = User(id="user-123")
        assert user.id == "user-123"


class TestAccountDetailModel:
    def test_inherits_account_fields(self) -> None:
        acct = AccountDetail(
            id="acct-1",
            name="Checking",
            type="checking",
            balance=15000,  # type: ignore[arg-type]
            cleared_balance=12000,  # type: ignore[arg-type]
            closed=False,
            deleted=False,
            on_budget=True,
            note="Main account",
            uncleared_balance=3000,  # type: ignore[arg-type]
            transfer_payee_id="payee-1",
        )
        assert acct.balance == Decimal("15")
        assert acct.cleared_balance == Decimal("12")
        assert acct.uncleared_balance == Decimal("3")
        assert acct.on_budget is True
        assert acct.note == "Main account"
        assert acct.transfer_payee_id == "payee-1"

    def test_optional_fields_none(self) -> None:
        acct = AccountDetail(
            id="acct-1",
            name="Savings",
            type="savings",
            balance=Decimal("100"),
            cleared_balance=Decimal("100"),
            closed=False,
            deleted=False,
            on_budget=False,
            note=None,
            uncleared_balance=Decimal("0"),
            transfer_payee_id=None,
        )
        assert acct.note is None
        assert acct.transfer_payee_id is None


class TestDateFormatModel:
    def test_basic(self) -> None:
        df = DateFormat(format="MM/DD/YYYY")
        assert df.format == "MM/DD/YYYY"


class TestCurrencyFormatModel:
    def test_basic(self) -> None:
        cf = CurrencyFormat(
            iso_code="USD",
            example_format="123,456.78",
            decimal_digits=2,
            decimal_separator=".",
            symbol_first=True,
            group_separator=",",
            currency_symbol="$",
            display_symbol=True,
        )
        assert cf.iso_code == "USD"
        assert cf.symbol_first is True
        assert cf.decimal_digits == 2


class TestBudgetSettingsModel:
    def test_nested(self) -> None:
        settings = BudgetSettings(
            date_format=DateFormat(format="MM/DD/YYYY"),
            currency_format=CurrencyFormat(
                iso_code="USD",
                example_format="123,456.78",
                decimal_digits=2,
                decimal_separator=".",
                symbol_first=True,
                group_separator=",",
                currency_symbol="$",
                display_symbol=True,
            ),
        )
        assert settings.date_format.format == "MM/DD/YYYY"
        assert settings.currency_format.iso_code == "USD"


class TestPayeeDetailModel:
    def test_inherits_payee_fields(self) -> None:
        payee = PayeeDetail(
            id="payee-1",
            name="Costco",
            deleted=False,
            transfer_account_id="acct-2",
        )
        assert payee.name == "Costco"
        assert payee.transfer_account_id == "acct-2"

    def test_transfer_account_none(self) -> None:
        payee = PayeeDetail(
            id="payee-1",
            name="Costco",
            deleted=False,
            transfer_account_id=None,
        )
        assert payee.transfer_account_id is None
