"""
Unit tests for apps/payments/models.py

Tests cover:
- Config model: singleton behavior, defaults, get_config()
- Payment model: creation, unique_together constraint, str representation
- MembershipFeePayment model: creation, 1:1 relationship with Payment
- LoanPayment model: creation, FK to Loan, 1:1 relationship with Payment
"""

import uuid
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from apps.loans.models import Loan, LoanState
from apps.payments.models import (
    Config,
    LoanPayment,
    MembershipFeePayment,
    Payment,
)
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(
    username: str, balance: Decimal = Decimal("100.00000000")
) -> User:
    return User.objects.create_user(
        username=username,
        password="pass123",
        balance=balance,
    )


def make_payment(
    user: User,
    amount: Decimal,
    jalali_year: int,
    jalali_month: int,
    bitpin_id: str = "",
) -> Payment:
    return Payment.objects.create(
        user=user,
        amount=amount,
        jalali_year=jalali_year,
        jalali_month=jalali_month,
        bitpin_payment_id=bitpin_id
        or f"bp_{user.username}_{jalali_year}_{jalali_month}",
    )


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfigModel(TestCase):
    """Tests for the Config singleton model."""

    def test_config_default_values(self):
        """Config created with get_config() has correct default values."""
        config = Config.get_config()

        assert config.min_membership_fee == Decimal("20")
        assert config.max_month_for_loan_payment == 24
        assert config.min_amount_for_loan_payment == Decimal("20")

    def test_get_config_returns_same_instance(self):
        """get_config() always returns the same singleton instance (pk=1)."""
        config1 = Config.get_config()
        config2 = Config.get_config()

        assert config1.pk == config2.pk == 1

    def test_get_config_creates_if_not_exists(self):
        """get_config() creates the config if it doesn't exist."""
        assert Config.objects.count() == 0

        config = Config.get_config()

        assert Config.objects.count() == 1
        assert config.pk == 1

    def test_get_config_does_not_duplicate(self):
        """Calling get_config() multiple times does not create duplicates."""
        Config.get_config()
        Config.get_config()
        Config.get_config()

        assert Config.objects.count() == 1

    def test_config_str_representation(self):
        """Config __str__ includes the min_membership_fee."""
        config = Config.get_config()

        result = str(config)
        assert "20" in result

    def test_config_db_table_name(self):
        """Config model uses the 'config' db_table."""
        assert Config._meta.db_table == "config"

    def test_config_can_be_updated(self):
        """Config fields can be updated and persisted."""
        config = Config.get_config()
        config.min_membership_fee = Decimal("30.00000000")
        config.max_month_for_loan_payment = 36
        config.save()

        config.refresh_from_db()
        assert config.min_membership_fee == Decimal("30.00000000")
        assert config.max_month_for_loan_payment == 36


# ---------------------------------------------------------------------------
# Payment tests
# ---------------------------------------------------------------------------


class TestPaymentModel(TestCase):
    """Tests for the Payment model."""

    def setUp(self):
        self.user = make_user("payer")

    def test_create_payment(self):
        """Payment can be created with required fields."""
        payment = make_payment(self.user, Decimal("50.00000000"), 1403, 1)

        assert payment.user == self.user
        assert payment.amount == Decimal("50.00000000")
        assert payment.jalali_year == 1403
        assert payment.jalali_month == 1
        assert payment.bitpin_payment_id == f"bp_{self.user.username}_1403_1"
        assert isinstance(payment.id, uuid.UUID)

    def test_payment_id_is_uuid(self):
        """Payment primary key is a UUID."""
        payment = make_payment(self.user, Decimal("20.00000000"), 1403, 2)
        assert isinstance(payment.id, uuid.UUID)

    def test_payment_str_representation(self):
        """Payment __str__ includes user_id, year/month, and amount."""
        payment = make_payment(self.user, Decimal("25.00000000"), 1403, 3)

        result = str(payment)
        assert "1403" in result
        assert "3" in result
        assert "25" in result

    def test_payment_db_table_name(self):
        """Payment model uses the 'payments' db_table."""
        assert Payment._meta.db_table == "payments"

    def test_payment_unique_together_user_year_month(self):
        """A user cannot have two payments for the same Jalali year/month."""
        make_payment(
            self.user, Decimal("20.00000000"), 1403, 4, bitpin_id="bp_first"
        )

        with self.assertRaises(IntegrityError):
            make_payment(
                self.user,
                Decimal("30.00000000"),
                1403,
                4,
                bitpin_id="bp_second",
            )

    def test_different_users_can_pay_same_month(self):
        """Two different users can both have payments for the same month."""
        user2 = make_user("payer2")

        payment1 = make_payment(self.user, Decimal("20.00000000"), 1403, 5)
        payment2 = make_payment(user2, Decimal("20.00000000"), 1403, 5)

        assert payment1.pk != payment2.pk
        assert (
            Payment.objects.filter(jalali_year=1403, jalali_month=5).count()
            == 2
        )

    def test_same_user_can_pay_different_months(self):
        """Same user can have payments for different months."""
        payment1 = make_payment(self.user, Decimal("20.00000000"), 1403, 6)
        payment2 = make_payment(self.user, Decimal("20.00000000"), 1403, 7)

        assert payment1.pk != payment2.pk

    def test_payment_amount_precision(self):
        """Payment amount stores up to 8 decimal places."""
        payment = make_payment(self.user, Decimal("20.12345678"), 1403, 8)
        payment.refresh_from_db()

        assert payment.amount == Decimal("20.12345678")


# ---------------------------------------------------------------------------
# MembershipFeePayment tests
# ---------------------------------------------------------------------------


class TestMembershipFeePaymentModel(TestCase):
    """Tests for the MembershipFeePayment model."""

    def setUp(self):
        self.user = make_user("member")
        self.payment = make_payment(self.user, Decimal("30.00000000"), 1403, 1)

    def test_create_membership_fee_payment(self):
        """MembershipFeePayment can be created linked to a Payment."""
        mfp = MembershipFeePayment.objects.create(
            payment=self.payment,
            amount=Decimal("30.00000000"),
        )

        assert mfp.payment == self.payment
        assert mfp.amount == Decimal("30.00000000")

    def test_membership_fee_payment_str_representation(self):
        """MembershipFeePayment __str__ includes payment_id and amount."""
        mfp = MembershipFeePayment.objects.create(
            payment=self.payment,
            amount=Decimal("30.00000000"),
        )

        result = str(mfp)
        assert "30" in result

    def test_membership_fee_payment_db_table_name(self):
        """MembershipFeePayment uses the 'membership_fee_payments' db_table."""
        assert MembershipFeePayment._meta.db_table == "membership_fee_payments"

    def test_membership_fee_payment_one_to_one_with_payment(self):
        """MembershipFeePayment has a 1:1 relationship with Payment."""
        MembershipFeePayment.objects.create(
            payment=self.payment,
            amount=Decimal("30.00000000"),
        )

        # Trying to create another MembershipFeePayment for the same Payment should fail
        with self.assertRaises(IntegrityError):
            MembershipFeePayment.objects.create(
                payment=self.payment,
                amount=Decimal("20.00000000"),
            )

    def test_membership_fee_payment_accessible_via_reverse_relation(self):
        """Payment.membership_fee reverse relation works correctly."""
        mfp = MembershipFeePayment.objects.create(
            payment=self.payment,
            amount=Decimal("30.00000000"),
        )

        assert self.payment.membership_fee == mfp

    def test_membership_fee_payment_cascades_on_payment_delete(self):
        """Deleting a Payment also deletes its MembershipFeePayment."""
        MembershipFeePayment.objects.create(
            payment=self.payment,
            amount=Decimal("30.00000000"),
        )
        payment_id = self.payment.id

        self.payment.delete()

        assert not MembershipFeePayment.objects.filter(
            payment_id=payment_id
        ).exists()

    def test_membership_fee_amount_precision(self):
        """MembershipFeePayment amount stores up to 8 decimal places."""
        mfp = MembershipFeePayment.objects.create(
            payment=self.payment,
            amount=Decimal("25.12345678"),
        )
        mfp.refresh_from_db()

        assert mfp.amount == Decimal("25.12345678")


# ---------------------------------------------------------------------------
# LoanPayment tests
# ---------------------------------------------------------------------------


class TestLoanPaymentModel(TestCase):
    """Tests for the LoanPayment model."""

    def setUp(self):
        self.user = make_user("loaner")
        self.loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("200.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=1,
            min_amount_for_each_payment=Decimal("20.00000000"),
        )
        self.payment = make_payment(self.user, Decimal("20.00000000"), 1403, 2)

    def test_create_loan_payment(self):
        """LoanPayment can be created linked to a Payment and Loan."""
        lp = LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        assert lp.payment == self.payment
        assert lp.loan == self.loan
        assert lp.amount == Decimal("20.00000000")

    def test_loan_payment_str_representation(self):
        """LoanPayment __str__ includes payment_id, loan_id, and amount."""
        lp = LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        result = str(lp)
        assert "20" in result

    def test_loan_payment_db_table_name(self):
        """LoanPayment uses the 'loan_payments' db_table."""
        assert LoanPayment._meta.db_table == "loan_payments"

    def test_loan_payment_one_to_one_with_payment(self):
        """LoanPayment has a 1:1 relationship with Payment."""
        LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        # Trying to create another LoanPayment for the same Payment should fail
        with self.assertRaises(IntegrityError):
            LoanPayment.objects.create(
                payment=self.payment,
                loan=self.loan,
                amount=Decimal("10.00000000"),
            )

    def test_loan_payment_accessible_via_reverse_relation(self):
        """Payment.loan_payment reverse relation works correctly."""
        lp = LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        assert self.payment.loan_payment == lp

    def test_loan_payment_accessible_via_loan_payments(self):
        """Loan.payments reverse relation returns all LoanPayments for that loan."""
        lp = LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        assert self.loan.payments.count() == 1
        assert self.loan.payments.first() == lp

    def test_loan_payment_cascades_on_payment_delete(self):
        """Deleting a Payment also deletes its LoanPayment."""
        LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )
        payment_id = self.payment.id

        self.payment.delete()

        assert not LoanPayment.objects.filter(payment_id=payment_id).exists()

    def test_multiple_loan_payments_for_same_loan(self):
        """A loan can have multiple LoanPayments (from different Payment records)."""
        lp1 = LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        payment2 = make_payment(self.user, Decimal("30.00000000"), 1403, 3)
        lp2 = LoanPayment.objects.create(
            payment=payment2,
            loan=self.loan,
            amount=Decimal("30.00000000"),
        )

        assert self.loan.payments.count() == 2
        assert lp1.pk != lp2.pk

    def test_loan_payment_amount_precision(self):
        """LoanPayment amount stores up to 8 decimal places."""
        lp = LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.12345678"),
        )
        lp.refresh_from_db()

        assert lp.amount == Decimal("20.12345678")

    def test_loan_payment_contributes_to_loan_total_paid(self):
        """LoanPayment amount is reflected in Loan.total_paid."""
        LoanPayment.objects.create(
            payment=self.payment,
            loan=self.loan,
            amount=Decimal("20.00000000"),
        )

        assert self.loan.total_paid == Decimal("20.00000000")
        assert self.loan.remaining_balance == Decimal("180.00000000")
