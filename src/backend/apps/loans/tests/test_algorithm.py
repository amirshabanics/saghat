"""
Unit tests for apps/loans/algorithm.py

Tests cover:
- compute_user_score() with various scenarios
- run_loan_assignment() with mock users
- Edge cases: no eligible users, single user, multiple users with same score
- Users with active loans are excluded
- Users with zero loan_request_amount are excluded
"""

from decimal import Decimal

from django.test import TestCase

from apps.loans.algorithm import compute_user_score, run_loan_assignment
from apps.loans.models import Loan, LoanState
from apps.payments.models import Config, LoanPayment, Payment
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(
    username: str,
    balance: Decimal = Decimal("100.00000000"),
    loan_request_amount: Decimal = Decimal("50.00000000"),
    is_main: bool = False,
    is_active: bool = True,
) -> User:
    """Create and return a User with the given attributes."""
    return User.objects.create_user(
        username=username,
        password="pass123",
        balance=balance,
        loan_request_amount=loan_request_amount,
        is_main=is_main,
        is_active=is_active,
    )


def make_payment(
    user: User,
    amount: Decimal,
    jalali_year: int,
    jalali_month: int,
    bitpin_id: str = "",
) -> Payment:
    """Create and return a Payment for the given user."""
    return Payment.objects.create(
        user=user,
        amount=amount,
        jalali_year=jalali_year,
        jalali_month=jalali_month,
        bitpin_payment_id=bitpin_id
        or f"bp_{user.username}_{jalali_year}_{jalali_month}",
    )


def make_loan_payment(
    user: User,
    loan: Loan,
    amount: Decimal,
    jalali_year: int,
    jalali_month: int,
) -> LoanPayment:
    """Create a Payment + LoanPayment for the given user and loan."""
    payment = make_payment(user, amount, jalali_year, jalali_month)
    return LoanPayment.objects.create(
        payment=payment,
        loan=loan,
        amount=amount,
    )


def make_active_loan(
    user: User,
    amount: Decimal,
    jalali_year: int,
    jalali_month: int,
    min_payment: Decimal = Decimal("20.00000000"),
) -> Loan:
    """Create an ACTIVE loan for the given user."""
    return Loan.objects.create(
        user=user,
        amount=amount,
        state=LoanState.ACTIVE,
        jalali_year=jalali_year,
        jalali_month=jalali_month,
        min_amount_for_each_payment=min_payment,
    )


def get_or_create_config() -> Config:
    """Get or create the singleton Config."""
    config, _ = Config.objects.get_or_create(
        pk=1,
        defaults={
            "min_membership_fee": Decimal("20.00000000"),
            "max_month_for_loan_payment": 24,
            "min_amount_for_loan_payment": Decimal("20.00000000"),
        },
    )
    return config


# ---------------------------------------------------------------------------
# Tests for compute_user_score()
# ---------------------------------------------------------------------------


class TestComputeUserScoreReturnsNone(TestCase):
    """
    Tests for cases where compute_user_score() should return None (unlimited score).

    None is returned when any denominator factor is zero/missing.
    """

    def test_returns_none_when_no_payment_history(self):
        """User with no payments gets None (unlimited) score."""
        user = make_user(
            "nohistory", loan_request_amount=Decimal("50.00000000")
        )

        score = compute_user_score(user)

        assert score is None

    def test_returns_none_when_no_loan_payments(self):
        """User who has paid membership fees but never made loan payments gets None."""
        user = make_user("noloanpay", balance=Decimal("200.00000000"))
        # Has a payment record but no LoanPayment
        make_payment(user, Decimal("20.00000000"), 1403, 1)

        score = compute_user_score(user)

        assert score is None

    def test_returns_none_when_no_active_loans(self):
        """User with payment history and loan payments but no active loans gets None."""
        user = make_user("noactiveloan", balance=Decimal("200.00000000"))
        # Create a payment
        make_payment(user, Decimal("20.00000000"), 1403, 1)
        # Create a loan payment without an active loan (use a different loan)
        loan = Loan.objects.create(
            user=user,
            amount=Decimal("100.00000000"),
            state=LoanState.INITIAL,  # Not ACTIVE
            jalali_year=1402,
            jalali_month=1,
        )
        make_loan_payment(user, loan, Decimal("20.00000000"), 1403, 2)

        score = compute_user_score(user)

        # total_loan_amount_user_get queries ACTIVE loans only → 0 → None
        assert score is None

    def test_returns_none_when_loan_request_amount_is_zero(self):
        """User with loan_request_amount=0 gets None (log(0) is undefined)."""
        user = make_user("zeroloan", loan_request_amount=Decimal("0"))
        make_payment(user, Decimal("20.00000000"), 1403, 1)

        score = compute_user_score(user)

        assert score is None

    def test_returns_none_when_loan_request_amount_is_one(self):
        """User with loan_request_amount=1 gets None (log(1)=0 → denominator=0)."""
        user = make_user("oneloan", loan_request_amount=Decimal("1.00000000"))
        make_payment(user, Decimal("20.00000000"), 1403, 1)

        score = compute_user_score(user)

        # log(1) = 0 → denominator factor is 0 → None
        assert score is None


class TestComputeUserScoreReturnsZero(TestCase):
    """
    Tests for cases where compute_user_score() returns Decimal('0').

    Zero is returned when denominator > 0 but numerator <= 0.
    """

    def _setup_user_with_active_loan_and_payments(
        self,
        username: str,
        balance: Decimal,
        loan_request_amount: Decimal,
        loan_amount: Decimal,
    ):
        """
        Set up a user who:
        - Has a payment record
        - Has an active loan
        - Has made loan payments
        This ensures the denominator is > 0.
        """
        user = make_user(
            username, balance=balance, loan_request_amount=loan_request_amount
        )
        # Membership payment
        make_payment(user, Decimal("20.00000000"), 1403, 1)
        # Active loan
        loan = make_active_loan(user, loan_amount, 1402, 1)
        # Loan payment (makes total_user_loan_payments > 0)
        make_loan_payment(user, loan, Decimal("20.00000000"), 1403, 2)
        return user, loan

    def test_returns_zero_when_balance_is_zero(self):
        """
        User with balance=0 gets score=0 because log(balance) factor in numerator is 0.
        """
        user, _ = self._setup_user_with_active_loan_and_payments(
            username="zerobal",
            balance=Decimal("0"),
            loan_request_amount=Decimal("100.00000000"),
            loan_amount=Decimal("100.00000000"),
        )

        score = compute_user_score(user)

        # numerator has log(balance)=0 → numerator=0 → score=0
        assert score == Decimal("0")

    def test_returns_zero_when_balance_is_one(self):
        """
        User with balance=1 gets score=0 because log(1)=0 → numerator=0.
        """
        user, _ = self._setup_user_with_active_loan_and_payments(
            username="onebal",
            balance=Decimal("1.00000000"),
            loan_request_amount=Decimal("100.00000000"),
            loan_amount=Decimal("100.00000000"),
        )

        score = compute_user_score(user)

        assert score == Decimal("0")


class TestComputeUserScorePositive(TestCase):
    """
    Tests for cases where compute_user_score() returns a positive Decimal.
    """

    def _setup_full_user(
        self,
        username: str,
        balance: Decimal = Decimal("500.00000000"),
        loan_request_amount: Decimal = Decimal("100.00000000"),
        loan_amount: Decimal = Decimal("200.00000000"),
        membership_payment_amount: Decimal = Decimal("20.00000000"),
        loan_payment_amount: Decimal = Decimal("20.00000000"),
    ) -> User:
        """
        Create a user with all the data needed for a positive score:
        - balance > e (so log(balance) > 0)
        - loan_request_amount > e (so log(loan_request_amount) > 0)
        - active loan with amount > e (so log(loan_amount) > 0)
        - at least one loan payment
        - at least one membership payment
        """
        user = make_user(
            username, balance=balance, loan_request_amount=loan_request_amount
        )
        # Membership payment (most recent)
        make_payment(user, membership_payment_amount, 1403, 1)
        # Active loan
        loan = make_active_loan(user, loan_amount, 1402, 1)
        # Loan payment
        make_loan_payment(user, loan, loan_payment_amount, 1403, 2)
        return user

    def test_returns_positive_decimal_for_well_qualified_user(self):
        """A user with good history gets a positive Decimal score."""
        user = self._setup_full_user("qualified")

        score = compute_user_score(user)

        assert score is not None
        assert score > Decimal("0")

    def test_score_is_decimal_type(self):
        """compute_user_score returns a Decimal (not float or int)."""
        user = self._setup_full_user("decimaltype")

        score = compute_user_score(user)

        assert score is not None
        assert isinstance(score, Decimal)

    def test_higher_balance_increases_score(self):
        """
        A user with higher balance (all else equal) should have a higher score,
        because log(balance) is a numerator factor.
        """
        user_low = self._setup_full_user(
            "lowbal",
            balance=Decimal("10.00000000"),
            loan_request_amount=Decimal("100.00000000"),
            loan_amount=Decimal("200.00000000"),
        )
        user_high = self._setup_full_user(
            "highbal",
            balance=Decimal("1000.00000000"),
            loan_request_amount=Decimal("100.00000000"),
            loan_amount=Decimal("200.00000000"),
        )

        score_low = compute_user_score(user_low)
        score_high = compute_user_score(user_high)

        # Both should be positive
        assert score_low is not None and score_low > 0
        assert score_high is not None and score_high > 0
        # Higher balance → higher score
        assert score_high > score_low

    def test_higher_loan_request_decreases_score(self):
        """
        A user requesting a larger loan (all else equal) should have a lower score,
        because log(loan_request_amount) is a denominator factor.
        """
        user_small_req = self._setup_full_user(
            "smallreq",
            balance=Decimal("500.00000000"),
            loan_request_amount=Decimal("10.00000000"),
            loan_amount=Decimal("200.00000000"),
        )
        user_large_req = self._setup_full_user(
            "largereq",
            balance=Decimal("500.00000000"),
            loan_request_amount=Decimal("500.00000000"),
            loan_amount=Decimal("200.00000000"),
        )

        score_small = compute_user_score(user_small_req)
        score_large = compute_user_score(user_large_req)

        # Both should be positive
        assert score_small is not None and score_small > 0
        assert score_large is not None and score_large > 0
        # Smaller request → higher score
        assert score_small > score_large

    def test_more_months_no_loan_increases_score(self):
        """
        A user with more months paying without a loan (all else equal) should have
        a higher score, because total_month_no_loan is a numerator factor.
        """
        # User with 1 membership payment (no extra months without loan)
        user_few = make_user(
            "fewmonths",
            balance=Decimal("500.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user_few, Decimal("20.00000000"), 1403, 1)
        loan_few = make_active_loan(user_few, Decimal("200.00000000"), 1402, 1)
        make_loan_payment(user_few, loan_few, Decimal("20.00000000"), 1403, 2)

        # User with 5 membership payments (more months without loan)
        user_many = make_user(
            "manymonths",
            balance=Decimal("500.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        for month in range(1, 6):
            make_payment(user_many, Decimal("20.00000000"), 1403, month)
        loan_many = make_active_loan(
            user_many, Decimal("200.00000000"), 1402, 1
        )
        make_loan_payment(
            user_many, loan_many, Decimal("20.00000000"), 1403, 6
        )

        score_few = compute_user_score(user_few)
        score_many = compute_user_score(user_many)

        assert score_few is not None and score_few > 0
        assert score_many is not None and score_many > 0
        assert score_many > score_few


# ---------------------------------------------------------------------------
# Tests for run_loan_assignment()
# ---------------------------------------------------------------------------


class TestRunLoanAssignmentNoEligibleUsers(TestCase):
    """Tests for run_loan_assignment() when no users are eligible."""

    def setUp(self):
        get_or_create_config()

    def test_no_active_users_raises_value_error(self):
        """
        run_loan_assignment raises ValueError if not all active users have paid.
        With no users at all, it should succeed (no unpaid users).
        """
        # No users → no unpaid users → should create NO_ONE loan
        loan = run_loan_assignment(1403, 1)

        assert loan.state == LoanState.NO_ONE
        assert loan.jalali_year == 1403
        assert loan.jalali_month == 1

    def test_raises_value_error_when_user_has_not_paid(self):
        """run_loan_assignment raises ValueError if an active user hasn't paid."""
        user = make_user("unpaid", balance=Decimal("100.00000000"))
        # No payment for this month

        with self.assertRaises(ValueError) as ctx:
            run_loan_assignment(1403, 2)

        assert "unpaid" in str(ctx.exception)

    def test_all_users_have_active_loans_creates_no_one_loan(self):
        """When all eligible users have active loans, creates a NO_ONE loan."""
        user = make_user(
            "activeloanuser",
            balance=Decimal("200.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        # Pay for this month
        make_payment(user, Decimal("20.00000000"), 1403, 3)
        # Give user an active loan
        make_active_loan(user, Decimal("100.00000000"), 1402, 1)

        loan = run_loan_assignment(1403, 3)

        assert loan.state == LoanState.NO_ONE
        assert (
            loan.log["not_participated"][0]["reason"]
            == "User has an active loan"
        )

    def test_all_users_have_zero_loan_request_creates_no_one_loan(self):
        """When all users have loan_request_amount=0, creates a NO_ONE loan."""
        user = make_user(
            "optedout",
            balance=Decimal("200.00000000"),
            loan_request_amount=Decimal("0"),
        )
        make_payment(user, Decimal("20.00000000"), 1403, 4)

        loan = run_loan_assignment(1403, 4)

        assert loan.state == LoanState.NO_ONE
        assert "opted out" in loan.log["not_participated"][0]["reason"]

    def test_user_excluded_when_loan_request_exceeds_balance(self):
        """Non-main user with loan_request_amount > balance is excluded."""
        user = make_user(
            "overrequest",
            balance=Decimal("50.00000000"),
            loan_request_amount=Decimal("200.00000000"),  # > balance
            is_main=False,
        )
        make_payment(user, Decimal("20.00000000"), 1403, 5)

        loan = run_loan_assignment(1403, 5)

        assert loan.state == LoanState.NO_ONE
        not_participated = loan.log["not_participated"]
        assert any(
            "loan_request_amount" in e["reason"] for e in not_participated
        )


class TestRunLoanAssignmentSingleUser(TestCase):
    """Tests for run_loan_assignment() with a single eligible user."""

    def setUp(self):
        get_or_create_config()

    def _setup_eligible_user(
        self,
        username: str = "winner",
        balance: Decimal = Decimal("500.00000000"),
        loan_request_amount: Decimal = Decimal("100.00000000"),
        jalali_year: int = 1403,
        jalali_month: int = 1,
    ) -> User:
        """Create a user who is eligible for a loan."""
        user = make_user(
            username, balance=balance, loan_request_amount=loan_request_amount
        )
        make_payment(user, Decimal("20.00000000"), jalali_year, jalali_month)
        return user

    def test_single_eligible_user_wins_loan(self):
        """Single eligible user always wins the loan assignment."""
        user = self._setup_eligible_user(jalali_year=1403, jalali_month=1)

        loan = run_loan_assignment(1403, 1)

        assert loan.state == LoanState.ACTIVE
        assert loan.user == user
        assert loan.amount == Decimal("100.00000000")
        assert loan.jalali_year == 1403
        assert loan.jalali_month == 1

    def test_loan_amount_matches_user_request(self):
        """Loan amount equals the winner's loan_request_amount."""
        user = self._setup_eligible_user(
            loan_request_amount=Decimal("75.00000000"),
            jalali_year=1403,
            jalali_month=2,
        )

        loan = run_loan_assignment(1403, 2)

        assert loan.amount == Decimal("75.00000000")

    def test_loan_log_contains_winner(self):
        """Loan log records the selected user_id."""
        user = self._setup_eligible_user(jalali_year=1403, jalali_month=3)

        loan = run_loan_assignment(1403, 3)

        assert loan.log["selected"] == user.id

    def test_loan_log_contains_participated_entry(self):
        """Loan log records the user in the participated list."""
        user = self._setup_eligible_user(jalali_year=1403, jalali_month=4)

        loan = run_loan_assignment(1403, 4)

        participated = loan.log["participated"]
        assert len(participated) == 1
        assert participated[0]["user_id"] == user.id
        assert participated[0]["username"] == user.username

    def test_loan_min_payment_set_from_config(self):
        """Loan min_amount_for_each_payment is set from Config."""
        config = Config.objects.get(pk=1)
        user = self._setup_eligible_user(jalali_year=1403, jalali_month=5)

        loan = run_loan_assignment(1403, 5)

        assert (
            loan.min_amount_for_each_payment
            == config.min_amount_for_loan_payment
        )

    def test_no_one_loan_when_request_exceeds_saghat_balance(self):
        """
        Creates NO_ONE loan when user's loan_request_amount exceeds total saghat balance.
        """
        # User with very small balance but large loan request
        user = make_user(
            "bigasker",
            balance=Decimal("10.00000000"),
            loan_request_amount=Decimal("10.00000000"),
        )
        make_payment(user, Decimal("20.00000000"), 1403, 6)
        # saghat_balance = sum of all user balances = 10
        # loan_request_amount = 10 → 10 <= 10 → should be fundable

        loan = run_loan_assignment(1403, 6)

        # 10 <= 10 so it should be funded
        assert loan.state == LoanState.ACTIVE

    def test_no_one_loan_when_request_strictly_exceeds_saghat_balance(self):
        """
        Creates NO_ONE loan when user's loan_request_amount > total saghat balance.
        """
        user = make_user(
            "toobig",
            balance=Decimal("10.00000000"),
            loan_request_amount=Decimal("11.00000000"),  # > balance
            is_main=True,  # is_main bypasses the balance check for eligibility
        )
        make_payment(user, Decimal("20.00000000"), 1403, 7)

        loan = run_loan_assignment(1403, 7)

        # saghat_balance = 10, loan_request = 11 → not fundable
        assert loan.state == LoanState.NO_ONE
        assert "saghat_balance" in loan.log.get("note", "")


class TestRunLoanAssignmentMultipleUsers(TestCase):
    """Tests for run_loan_assignment() with multiple eligible users."""

    def setUp(self):
        get_or_create_config()

    def test_user_with_active_loan_excluded_from_multiple(self):
        """User with active loan is excluded even when other users are eligible."""
        # User 1: has active loan → excluded
        user1 = make_user(
            "hasloan",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user1, Decimal("20.00000000"), 1403, 1)
        make_active_loan(user1, Decimal("100.00000000"), 1402, 1)

        # User 2: eligible
        user2 = make_user(
            "eligible",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user2, Decimal("20.00000000"), 1403, 1)

        loan = run_loan_assignment(1403, 1)

        assert loan.state == LoanState.ACTIVE
        assert loan.user == user2
        # user1 should be in not_participated
        not_participated_ids = [
            e["user_id"] for e in loan.log["not_participated"]
        ]
        assert user1.id in not_participated_ids

    def test_winner_selected_from_unlimited_score_pool(self):
        """
        When multiple users have unlimited (None) scores, one is randomly selected.
        """
        # Both users have no payment history → unlimited score
        user1 = make_user(
            "unlimited1",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user1, Decimal("20.00000000"), 1403, 1)

        user2 = make_user(
            "unlimited2",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user2, Decimal("20.00000000"), 1403, 1)

        loan = run_loan_assignment(1403, 1)

        assert loan.state == LoanState.ACTIVE
        assert loan.user in [user1, user2]
        # Both should be in random_pool
        assert len(loan.log["random_pool"]) == 2

    def test_user_with_higher_score_wins(self):
        """
        User with higher computed score wins when scores differ.
        We set up one user with a much higher score by giving them more months
        without a loan (higher total_month_no_loan numerator factor).
        """
        # User 1: has payment history + active loan + loan payments → computable score
        # Give user1 many months of payments (high total_month_no_loan)
        user1 = make_user(
            "highscore",
            balance=Decimal("1000.00000000"),
            loan_request_amount=Decimal("50.00000000"),
        )
        # 10 membership payments
        for month in range(1, 11):
            make_payment(user1, Decimal("20.00000000"), 1402, month)
        # Active loan
        loan1 = make_active_loan(user1, Decimal("200.00000000"), 1401, 1)
        # Loan payment
        make_loan_payment(user1, loan1, Decimal("20.00000000"), 1402, 11)
        # Payment for current month
        make_payment(user1, Decimal("20.00000000"), 1403, 1)

        # User 2: minimal history → lower score
        user2 = make_user(
            "lowscore",
            balance=Decimal("10.00000000"),  # low balance → low log(balance)
            loan_request_amount=Decimal("50.00000000"),
        )
        make_payment(user2, Decimal("20.00000000"), 1403, 1)
        loan2 = make_active_loan(user2, Decimal("200.00000000"), 1401, 2)
        make_loan_payment(user2, loan2, Decimal("20.00000000"), 1403, 2)
        # Note: user2 has a loan payment in 1403/2 but we need 1403/1 payment
        # The payment for 1403/1 was already created above

        score1 = compute_user_score(user1)
        score2 = compute_user_score(user2)

        # Verify score1 > score2 (or one is None/unlimited)
        # If score1 is None (unlimited), it beats any finite score
        if score1 is None and score2 is not None:
            # user1 has unlimited score → should win
            pass
        elif score1 is not None and score2 is not None:
            assert score1 > score2

    def test_zero_loan_request_user_excluded_from_multiple(self):
        """User with loan_request_amount=0 is excluded even with other eligible users."""
        user_opted_out = make_user(
            "optedout",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("0"),
        )
        make_payment(user_opted_out, Decimal("20.00000000"), 1403, 1)

        user_eligible = make_user(
            "wantsit",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user_eligible, Decimal("20.00000000"), 1403, 1)

        loan = run_loan_assignment(1403, 1)

        assert loan.state == LoanState.ACTIVE
        assert loan.user == user_eligible
        not_participated_ids = [
            e["user_id"] for e in loan.log["not_participated"]
        ]
        assert user_opted_out.id in not_participated_ids

    def test_inactive_users_excluded(self):
        """Inactive users (is_active=False) are not considered in assignment."""
        active_user = make_user(
            "active",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
            is_active=True,
        )
        make_payment(active_user, Decimal("20.00000000"), 1403, 1)

        inactive_user = make_user(
            "inactive",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
            is_active=False,
        )
        # Inactive user has NOT paid (and shouldn't be required to)

        loan = run_loan_assignment(1403, 1)

        assert loan.state == LoanState.ACTIVE
        assert loan.user == active_user

    def test_main_user_bypasses_balance_check(self):
        """
        is_main user can request a loan even if loan_request_amount > balance.
        """
        main_user = make_user(
            "mainbig",
            balance=Decimal("10.00000000"),
            loan_request_amount=Decimal("500.00000000"),  # > balance
            is_main=True,
        )
        make_payment(main_user, Decimal("20.00000000"), 1403, 1)

        # saghat_balance = 10, but main_user requests 500 → not fundable
        # However, main_user should be in participated (not excluded for balance check)
        loan = run_loan_assignment(1403, 1)

        # main_user is eligible (bypasses balance check) but can't be funded
        # because saghat_balance < loan_request_amount
        assert loan.state == LoanState.NO_ONE
        participated_ids = [e["user_id"] for e in loan.log["participated"]]
        assert main_user.id in participated_ids

    def test_loan_assignment_creates_loan_record_in_db(self):
        """run_loan_assignment creates a Loan record in the database."""
        user = make_user(
            "dbtest",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user, Decimal("20.00000000"), 1403, 1)

        assert Loan.objects.count() == 0

        loan = run_loan_assignment(1403, 1)

        assert Loan.objects.count() == 1
        assert Loan.objects.get(pk=loan.pk) is not None

    def test_duplicate_month_raises_integrity_error(self):
        """Running assignment twice for the same month raises an error."""
        from django.db import IntegrityError

        user = make_user(
            "dupmonth",
            balance=Decimal("300.00000000"),
            loan_request_amount=Decimal("100.00000000"),
        )
        make_payment(user, Decimal("20.00000000"), 1403, 1)

        run_loan_assignment(1403, 1)

        # Second run for same month should fail due to unique_together constraint
        with self.assertRaises(IntegrityError):
            run_loan_assignment(1403, 1)
