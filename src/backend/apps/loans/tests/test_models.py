"""
Unit tests for apps/loans/models.py

Tests cover:
- Loan creation with various states
- LoanState choices
- total_paid property
- remaining_balance property
- is_settled property
"""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.loans.models import Loan, LoanState
from apps.users.models import User


class TestLoanStateChoices(TestCase):
    """Tests for the LoanState TextChoices enum."""

    def test_loan_state_values(self):
        """LoanState has the expected string values."""
        assert LoanState.INITIAL == "initial"
        assert LoanState.ACTIVE == "active"
        assert LoanState.NO_ONE == "no_one"

    def test_loan_state_labels(self):
        """LoanState has the expected human-readable labels."""
        assert LoanState.INITIAL.label == "Initial"
        assert LoanState.ACTIVE.label == "Active"
        assert LoanState.NO_ONE.label == "No One"

    def test_loan_state_choices_list(self):
        """LoanState.choices contains all three states."""
        choices = dict(LoanState.choices)
        assert "initial" in choices
        assert "active" in choices
        assert "no_one" in choices


class TestLoanCreation(TestCase):
    """Tests for Loan model creation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="borrower",
            password="pass123",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("150.00000000"),
        )

    def test_create_loan_with_defaults(self):
        """Loan created with minimal fields has correct defaults."""
        loan = Loan.objects.create(
            jalali_year=1403,
            jalali_month=1,
        )

        assert loan.state == LoanState.INITIAL
        assert loan.user is None
        assert loan.amount is None
        assert loan.log == {}
        assert loan.min_amount_for_each_payment is None
        assert isinstance(loan.id, uuid.UUID)

    def test_create_active_loan_with_user(self):
        """Active loan can be created with a user and amount."""
        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("150.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=2,
            min_amount_for_each_payment=Decimal("20.00000000"),
        )

        assert loan.user == self.user
        assert loan.amount == Decimal("150.00000000")
        assert loan.state == LoanState.ACTIVE
        assert loan.min_amount_for_each_payment == Decimal("20.00000000")

    def test_create_no_one_loan(self):
        """NO_ONE loan can be created without a user."""
        loan = Loan.objects.create(
            state=LoanState.NO_ONE,
            jalali_year=1403,
            jalali_month=3,
            log={
                "not_participated": [],
                "participated": [],
                "selected": None,
                "random_pool": [],
            },
        )

        assert loan.state == LoanState.NO_ONE
        assert loan.user is None
        assert loan.log["selected"] is None

    def test_loan_unique_together_jalali_year_month(self):
        """Two loans cannot share the same jalali_year and jalali_month."""
        from django.db import IntegrityError

        Loan.objects.create(jalali_year=1403, jalali_month=4)

        with self.assertRaises(IntegrityError):
            Loan.objects.create(jalali_year=1403, jalali_month=4)

    def test_loan_str_representation(self):
        """Loan __str__ includes year, month, state, and user_id."""
        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=5,
        )

        result = str(loan)
        assert "1403" in result
        assert "5" in result
        assert "active" in result

    def test_loan_db_table_name(self):
        """Loan model uses the 'loans' db_table."""
        assert Loan._meta.db_table == "loans"

    def test_loan_id_is_uuid(self):
        """Loan primary key is a UUID."""
        loan = Loan.objects.create(jalali_year=1403, jalali_month=6)
        assert isinstance(loan.id, uuid.UUID)

    def test_loan_log_stores_json(self):
        """Loan log field stores and retrieves JSON data correctly."""
        log_data = {
            "not_participated": [
                {"user_id": 1, "username": "alice", "reason": "active loan"}
            ],
            "participated": [
                {"user_id": 2, "username": "bob", "point": "unlimited"}
            ],
            "selected": 2,
            "random_pool": [2],
        }
        loan = Loan.objects.create(
            jalali_year=1403,
            jalali_month=7,
            log=log_data,
        )
        loan.refresh_from_db()

        assert loan.log["selected"] == 2
        assert loan.log["participated"][0]["username"] == "bob"
        assert loan.log["not_participated"][0]["reason"] == "active loan"


class TestLoanTotalPaid(TestCase):
    """Tests for the total_paid property."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="payer",
            password="pass123",
            balance=Decimal("500.00000000"),
        )
        self.loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("200.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=1,
            min_amount_for_each_payment=Decimal("20.00000000"),
        )

    def _make_loan_payment(self, amount: Decimal, year: int, month: int):
        """Helper to create a LoanPayment linked to self.loan."""
        from apps.payments.models import LoanPayment, Payment

        payment = Payment.objects.create(
            user=self.user,
            amount=amount,
            jalali_year=year,
            jalali_month=month,
            bitpin_payment_id=f"bp_{year}_{month}",
        )
        LoanPayment.objects.create(
            payment=payment,
            loan=self.loan,
            amount=amount,
        )
        return payment

    def test_total_paid_zero_when_no_payments(self):
        """total_paid is Decimal('0') when no loan payments exist."""
        assert self.loan.total_paid == Decimal("0")

    def test_total_paid_single_payment(self):
        """total_paid equals the single payment amount."""
        self._make_loan_payment(Decimal("50.00000000"), 1403, 2)

        assert self.loan.total_paid == Decimal("50.00000000")

    def test_total_paid_multiple_payments(self):
        """total_paid sums all loan payments."""
        self._make_loan_payment(Decimal("50.00000000"), 1403, 2)
        self._make_loan_payment(Decimal("30.00000000"), 1403, 3)
        self._make_loan_payment(Decimal("20.00000000"), 1403, 4)

        assert self.loan.total_paid == Decimal("100.00000000")


class TestLoanRemainingBalance(TestCase):
    """Tests for the remaining_balance property."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="debtor",
            password="pass123",
            balance=Decimal("500.00000000"),
        )

    def test_remaining_balance_zero_when_amount_is_none(self):
        """remaining_balance is Decimal('0') when loan amount is None."""
        loan = Loan.objects.create(
            jalali_year=1403,
            jalali_month=1,
            state=LoanState.INITIAL,
        )

        assert loan.remaining_balance == Decimal("0")

    def test_remaining_balance_equals_amount_when_no_payments(self):
        """remaining_balance equals loan amount when no payments made."""
        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("200.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=2,
        )

        assert loan.remaining_balance == Decimal("200.00000000")

    def test_remaining_balance_decreases_with_payments(self):
        """remaining_balance decreases as payments are made."""
        from apps.payments.models import LoanPayment, Payment

        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("200.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=3,
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("80.00000000"),
            jalali_year=1403,
            jalali_month=4,
            bitpin_payment_id="bp_test_1",
        )
        LoanPayment.objects.create(
            payment=payment,
            loan=loan,
            amount=Decimal("80.00000000"),
        )

        assert loan.remaining_balance == Decimal("120.00000000")


class TestLoanIsSettled(TestCase):
    """Tests for the is_settled property."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="settler",
            password="pass123",
            balance=Decimal("500.00000000"),
        )

    def test_is_settled_false_when_no_payments(self):
        """is_settled is False when no payments have been made."""
        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=1,
        )

        assert loan.is_settled is False

    def test_is_settled_false_when_partially_paid(self):
        """is_settled is False when loan is only partially paid."""
        from apps.payments.models import LoanPayment, Payment

        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=2,
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("50.00000000"),
            jalali_year=1403,
            jalali_month=3,
            bitpin_payment_id="bp_partial",
        )
        LoanPayment.objects.create(
            payment=payment,
            loan=loan,
            amount=Decimal("50.00000000"),
        )

        assert loan.is_settled is False

    def test_is_settled_true_when_fully_paid(self):
        """is_settled is True when total_paid >= loan amount."""
        from apps.payments.models import LoanPayment, Payment

        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=4,
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            jalali_year=1403,
            jalali_month=5,
            bitpin_payment_id="bp_full",
        )
        LoanPayment.objects.create(
            payment=payment,
            loan=loan,
            amount=Decimal("100.00000000"),
        )

        assert loan.is_settled is True

    def test_is_settled_true_when_overpaid(self):
        """is_settled is True when total_paid exceeds loan amount."""
        from apps.payments.models import LoanPayment, Payment

        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=6,
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("120.00000000"),
            jalali_year=1403,
            jalali_month=7,
            bitpin_payment_id="bp_over",
        )
        LoanPayment.objects.create(
            payment=payment,
            loan=loan,
            amount=Decimal("120.00000000"),
        )

        assert loan.is_settled is True

    def test_is_settled_true_when_amount_is_none(self):
        """is_settled is True when loan amount is None (remaining_balance returns 0)."""
        loan = Loan.objects.create(
            jalali_year=1403,
            jalali_month=8,
            state=LoanState.INITIAL,
        )

        # remaining_balance returns 0 when amount is None, so 0 <= 0 → settled
        assert loan.is_settled is True
