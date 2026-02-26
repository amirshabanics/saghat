"""
Unit tests for apps/users/models.py

Tests cover:
- User creation via create_user()
- has_active_loan property
- balance field defaults and behavior
- is_main flag
- loan_request_amount field
"""

from decimal import Decimal
from django.test import TestCase

from apps.users.models import User


class TestUserCreation(TestCase):
    """Tests for User model creation."""

    def test_create_user_with_defaults(self):
        """User created with create_user() has correct default field values."""
        user = User.objects.create_user(username="alice", password="pass123")

        assert user.username == "alice"
        assert user.balance == Decimal("0")
        assert user.is_main is False
        assert user.loan_request_amount == Decimal("0")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_create_user_with_custom_balance(self):
        """User can be created with a custom balance."""
        user = User.objects.create_user(
            username="bob",
            password="pass123",
            balance=Decimal("250.50000000"),
        )

        assert user.balance == Decimal("250.50000000")

    def test_create_user_with_loan_request_amount(self):
        """User can be created with a loan_request_amount."""
        user = User.objects.create_user(
            username="carol",
            password="pass123",
            loan_request_amount=Decimal("100.00000000"),
        )

        assert user.loan_request_amount == Decimal("100.00000000")

    def test_create_main_user(self):
        """User with is_main=True is correctly stored."""
        user = User.objects.create_user(
            username="mainuser",
            password="pass123",
            is_main=True,
        )

        assert user.is_main is True

    def test_user_str_representation(self):
        """User __str__ returns the username."""
        user = User.objects.create_user(username="dave", password="pass123")

        assert str(user) == "dave"

    def test_user_db_table_name(self):
        """User model uses the 'users' db_table."""
        assert User._meta.db_table == "users"

    def test_create_multiple_users_unique_usernames(self):
        """Multiple users can be created with unique usernames."""
        user1 = User.objects.create_user(username="user1", password="pass")
        user2 = User.objects.create_user(username="user2", password="pass")

        assert user1.pk != user2.pk
        assert User.objects.count() == 2

    def test_balance_precision(self):
        """Balance field stores up to 8 decimal places."""
        user = User.objects.create_user(
            username="precise",
            password="pass",
            balance=Decimal("123.12345678"),
        )
        # Re-fetch from DB to confirm persistence
        user.refresh_from_db()
        assert user.balance == Decimal("123.12345678")


class TestUserHasActiveLoan(TestCase):
    """Tests for the has_active_loan property."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="loanuser",
            password="pass123",
            balance=Decimal("200.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )

    def test_has_active_loan_false_when_no_loans(self):
        """has_active_loan is False when user has no loans at all."""
        assert self.user.has_active_loan is False

    def test_has_active_loan_true_when_active_loan_exists(self):
        """has_active_loan is True when user has an ACTIVE loan."""
        from apps.loans.models import Loan, LoanState

        Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=1,
        )

        assert self.user.has_active_loan is True

    def test_has_active_loan_false_when_only_initial_loan(self):
        """has_active_loan is False when user only has an INITIAL loan."""
        from apps.loans.models import Loan, LoanState

        Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.INITIAL,
            jalali_year=1403,
            jalali_month=2,
        )

        assert self.user.has_active_loan is False

    def test_has_active_loan_false_when_only_no_one_loan(self):
        """has_active_loan is False when only NO_ONE loan exists (no user assigned)."""
        from apps.loans.models import Loan, LoanState

        # NO_ONE loans have no user assigned
        Loan.objects.create(
            user=None,
            state=LoanState.NO_ONE,
            jalali_year=1403,
            jalali_month=3,
        )

        assert self.user.has_active_loan is False

    def test_has_active_loan_false_after_loan_settled(self):
        """has_active_loan is False when user's loan is not in ACTIVE state."""
        from apps.loans.models import Loan, LoanState

        loan = Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=4,
        )
        # Simulate settling by changing state (in real app this would be done differently)
        loan.state = LoanState.INITIAL
        loan.save()

        assert self.user.has_active_loan is False

    def test_has_active_loan_true_with_multiple_loans(self):
        """has_active_loan is True even if user has multiple loans, one being active."""
        from apps.loans.models import Loan, LoanState

        # An old initial loan
        Loan.objects.create(
            user=self.user,
            amount=Decimal("50.00000000"),
            state=LoanState.INITIAL,
            jalali_year=1402,
            jalali_month=1,
        )
        # A current active loan
        Loan.objects.create(
            user=self.user,
            amount=Decimal("100.00000000"),
            state=LoanState.ACTIVE,
            jalali_year=1403,
            jalali_month=5,
        )

        assert self.user.has_active_loan is True


class TestUserBalanceField(TestCase):
    """Tests for the balance field behavior."""

    def test_balance_defaults_to_zero(self):
        """Balance defaults to Decimal('0') on creation."""
        user = User.objects.create_user(username="zerobal", password="pass")
        assert user.balance == Decimal("0")

    def test_balance_can_be_updated(self):
        """Balance can be updated and persisted."""
        user = User.objects.create_user(username="updatebal", password="pass")
        user.balance = Decimal("75.00000000")
        user.save()

        user.refresh_from_db()
        assert user.balance == Decimal("75.00000000")

    def test_balance_supports_large_values(self):
        """Balance field supports large values (max_digits=20)."""
        large_balance = Decimal("999999999999.12345678")
        user = User.objects.create_user(
            username="richuser",
            password="pass",
            balance=large_balance,
        )
        user.refresh_from_db()
        assert user.balance == large_balance
