import math
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db.models import Sum


@dataclass
class NotParticipatedEntry:
    user_id: int
    username: str
    reason: str


@dataclass
class ParticipatedEntry:
    user_id: int
    username: str
    point: str  # "unlimited", "0", or decimal string


@dataclass
class AssignmentLog:
    not_participated: list[NotParticipatedEntry] = field(default_factory=list)
    participated: list[ParticipatedEntry] = field(default_factory=list)
    selected: Optional[int] = None  # user_id of winner
    random_pool: list[int] = field(
        default_factory=list
    )  # user_ids in random pool


@dataclass
class UserScore:
    user_id: int
    username: str
    score: Optional[Decimal]  # None means "unlimited" (infinity)
    loan_request_amount: Decimal


def compute_user_score(user: "User") -> Optional[Decimal]:  # type: ignore[name-defined]
    """
    Compute the loan assignment score for a user.

    Score = (numerator_product) / (denominator_product)

    If denominator_product == 0 → score is None (unlimited/infinity)

    Numerator factors (multiply together):
    - log(previous_loan_amount): log of the amount of their most recent settled loan
    - log(balance): log of current balance
    - total_month_no_loan: number of months user paid membership fee without having a loan

    Denominator factors (multiply together):
    - total_payment_for_last_month: total amount paid in the most recent payment
    - total_user_loan_payments: total count of loan payments ever made
    - log(total_loan_amount_user_get): log of total loan amount received historically
    - total_loan_user_get: total number of loans received
    - log(loan_request_amount): log of what they're requesting now

    For log() factors: if the value is 0 or negative, treat as 0 (skip that factor).
    For count factors: if 0, that factor contributes 0 to denominator (making it 0 → unlimited).

    IMPORTANT: Check denominator first. If any denominator factor is 0, return None immediately.
    """
    from apps.loans.models import Loan, LoanState
    from apps.payments.models import LoanPayment, Payment

    # --- Denominator factors ---

    # total_payment_for_last_month: sum of amounts in the user's most recent Payment
    last_payment = (
        Payment.objects.filter(user=user)
        .order_by("-jalali_year", "-jalali_month")
        .first()
    )
    if last_payment is None:
        return None  # No payment history → unlimited
    total_payment_for_last_month = last_payment.amount
    if total_payment_for_last_month <= 0:
        return None  # denominator would be 0

    # total_user_loan_payments: count of all LoanPayment records for this user
    total_user_loan_payments = LoanPayment.objects.filter(
        payment__user=user
    ).count()
    if total_user_loan_payments == 0:
        return None  # denominator would be 0

    # total_loan_amount_user_get: sum of all loan amounts received
    total_loan_amount = Loan.objects.filter(
        user=user, state=LoanState.ACTIVE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if total_loan_amount <= 0:
        return None  # log(0) → denominator would be 0
    log_total_loan_amount = Decimal(str(math.log(float(total_loan_amount))))
    if log_total_loan_amount <= 0:
        return None

    # total_loan_user_get: count of loans received (active or settled)
    total_loan_user_get = Loan.objects.filter(
        user=user, state=LoanState.ACTIVE
    ).count()
    if total_loan_user_get == 0:
        return None  # denominator would be 0

    # log(loan_request_amount)
    if user.loan_request_amount <= 0:
        return None  # log(0) → denominator would be 0
    log_loan_request = Decimal(str(math.log(float(user.loan_request_amount))))
    if log_loan_request <= 0:
        return None

    denominator = (
        total_payment_for_last_month
        * Decimal(str(total_user_loan_payments))
        * log_total_loan_amount
        * Decimal(str(total_loan_user_get))
        * log_loan_request
    )

    if denominator <= 0:
        return None  # unlimited

    # --- Numerator factors ---

    # log(previous_loan_amount): most recent loan amount
    previous_loan = (
        Loan.objects.filter(user=user, state=LoanState.ACTIVE)
        .order_by("-created_at")
        .first()
    )
    if (
        previous_loan is None
        or previous_loan.amount is None
        or previous_loan.amount <= 0
    ):
        log_previous_loan = Decimal("0")
    else:
        log_val = math.log(float(previous_loan.amount))
        log_previous_loan = (
            Decimal(str(log_val)) if log_val > 0 else Decimal("0")
        )

    # log(balance)
    if user.balance <= 0:
        log_balance = Decimal("0")
    else:
        log_val = math.log(float(user.balance))
        log_balance = Decimal(str(log_val)) if log_val > 0 else Decimal("0")

    # total_month_no_loan: count of months where user paid but had no active loan
    # Approximated as: total payments - months where they had an active loan payment
    total_payments_count = Payment.objects.filter(user=user).count()
    months_with_loan_payment = (
        LoanPayment.objects.filter(payment__user=user)
        .values("payment__jalali_year", "payment__jalali_month")
        .distinct()
        .count()
    )
    total_month_no_loan = max(
        0, total_payments_count - months_with_loan_payment
    )

    numerator = (
        log_previous_loan * log_balance * Decimal(str(total_month_no_loan))
    )

    if numerator <= 0:
        return Decimal("0")

    return numerator / denominator


def run_loan_assignment(jalali_year: int, jalali_month: int) -> "Loan":  # type: ignore[name-defined]
    """
    Run the loan assignment algorithm for the given Jalali month.

    Steps:
    1. Verify all active users have paid for this month
    2. Find eligible users
    3. Compute scores
    4. Select winner (random among tied max-score users)
    5. Check fund balance
    6. Create/update Loan record

    Returns the created/updated Loan object.
    """
    from django.db import transaction

    from apps.loans.models import Loan, LoanState
    from apps.payments.models import Config, Payment
    from apps.users.models import User

    config = Config.get_config()

    # Get all active users
    all_users = list(User.objects.filter(is_active=True))

    # Check all users have paid this month
    paid_user_ids = set(
        Payment.objects.filter(
            jalali_year=jalali_year,
            jalali_month=jalali_month,
        ).values_list("user_id", flat=True)
    )

    unpaid_users = [u for u in all_users if u.id not in paid_user_ids]
    if unpaid_users:
        unpaid_names = ", ".join(u.username for u in unpaid_users)
        raise ValueError(
            f"Not all users have paid for {jalali_year}/{jalali_month}. "
            f"Unpaid: {unpaid_names}"
        )

    # Calculate saghat_balance (sum of all user balances)
    saghat_balance = User.objects.filter(is_active=True).aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0")

    log = AssignmentLog()

    # Determine eligibility for each user
    eligible_users: list[User] = []
    for user in all_users:
        # Condition 1: is_main OR loan_request_amount <= balance
        if not user.is_main and user.loan_request_amount > user.balance:
            log.not_participated.append(
                NotParticipatedEntry(
                    user_id=user.id,
                    username=user.username,
                    reason=f"loan_request_amount ({user.loan_request_amount}) > balance ({user.balance})",
                )
            )
            continue

        # Condition 2: no active loan
        if user.has_active_loan:
            log.not_participated.append(
                NotParticipatedEntry(
                    user_id=user.id,
                    username=user.username,
                    reason="User has an active loan",
                )
            )
            continue

        # Condition 3: loan_request_amount > 0
        if user.loan_request_amount <= 0:
            log.not_participated.append(
                NotParticipatedEntry(
                    user_id=user.id,
                    username=user.username,
                    reason="loan_request_amount is 0 (opted out)",
                )
            )
            continue

        eligible_users.append(user)

    # If no eligible users, create no_one loan
    if not eligible_users:
        with transaction.atomic():
            loan = Loan.objects.create(
                state=LoanState.NO_ONE,
                jalali_year=jalali_year,
                jalali_month=jalali_month,
                log={
                    "not_participated": [
                        {
                            "user_id": e.user_id,
                            "username": e.username,
                            "reason": e.reason,
                        }
                        for e in log.not_participated
                    ],
                    "participated": [],
                    "selected": None,
                    "random_pool": [],
                },
            )
        return loan

    # Compute scores for eligible users
    user_scores: list[UserScore] = []
    for user in eligible_users:
        score = compute_user_score(user)
        score_str = "unlimited" if score is None else str(score)
        log.participated.append(
            ParticipatedEntry(
                user_id=user.id,
                username=user.username,
                point=score_str,
            )
        )
        user_scores.append(
            UserScore(
                user_id=user.id,
                username=user.username,
                score=score,
                loan_request_amount=user.loan_request_amount,
            )
        )

    # Filter by fund balance: user.loan_request_amount <= saghat_balance
    fundable_scores = [
        us for us in user_scores if us.loan_request_amount <= saghat_balance
    ]

    if not fundable_scores:
        # No one can be funded
        with transaction.atomic():
            loan = Loan.objects.create(
                state=LoanState.NO_ONE,
                jalali_year=jalali_year,
                jalali_month=jalali_month,
                log={
                    "not_participated": [
                        {
                            "user_id": e.user_id,
                            "username": e.username,
                            "reason": e.reason,
                        }
                        for e in log.not_participated
                    ],
                    "participated": [
                        {
                            "user_id": e.user_id,
                            "username": e.username,
                            "point": e.point,
                        }
                        for e in log.participated
                    ],
                    "selected": None,
                    "random_pool": [],
                    "note": "No user's loan_request_amount fits within saghat_balance",
                },
            )
        return loan

    # Determine max score group
    # None (unlimited) > any Decimal
    has_unlimited = any(us.score is None for us in fundable_scores)

    if has_unlimited:
        max_score_group = [us for us in fundable_scores if us.score is None]
    else:
        max_score = max(us.score for us in fundable_scores)  # type: ignore[type-var]
        max_score_group = [
            us for us in fundable_scores if us.score == max_score
        ]

    # Random selection from max score group
    log.random_pool = [us.user_id for us in max_score_group]
    winner_score = random.choice(max_score_group)
    log.selected = winner_score.user_id

    # Get the winner User object
    winner_user = next(
        u for u in eligible_users if u.id == winner_score.user_id
    )

    # Create the active loan
    with transaction.atomic():
        loan = Loan.objects.create(
            user=winner_user,
            amount=winner_score.loan_request_amount,
            state=LoanState.ACTIVE,
            jalali_year=jalali_year,
            jalali_month=jalali_month,
            min_amount_for_each_payment=config.min_amount_for_loan_payment,
            log={
                "not_participated": [
                    {
                        "user_id": e.user_id,
                        "username": e.username,
                        "reason": e.reason,
                    }
                    for e in log.not_participated
                ],
                "participated": [
                    {
                        "user_id": e.user_id,
                        "username": e.username,
                        "point": e.point,
                    }
                    for e in log.participated
                ],
                "selected": log.selected,
                "random_pool": log.random_pool,
            },
        )

    return loan
