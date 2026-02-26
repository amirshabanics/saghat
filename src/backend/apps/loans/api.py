import uuid as uuid_module
from typing import Any, Optional

from django.http import HttpRequest
from ninja import Query, Router

from apps.common.auth import jwt_auth, main_user_auth
from apps.common.jalali import get_current_jalali
from apps.loans.algorithm import run_loan_assignment
from apps.loans.models import Loan, LoanState
from apps.loans.schemas import (
    ErrorResponse,
    LoanHistoryFilters,
    LoanPaymentSummary,
    LoanResponse,
    StartLoanResponse,
)
from apps.users.models import User

router = Router(tags=["loans"])


def _build_loan_response(loan: Loan) -> LoanResponse:
    """Helper to build a LoanResponse from a Loan ORM object."""
    payments = loan.payments.select_related("payment").order_by(
        "payment__jalali_year", "payment__jalali_month"
    )
    payment_summaries = [
        LoanPaymentSummary(
            id=lp.payment.id,
            amount=lp.amount,
            jalali_year=lp.payment.jalali_year,
            jalali_month=lp.payment.jalali_month,
        )
        for lp in payments
    ]

    username: Optional[str] = None
    if loan.user_id is not None:
        try:
            username = loan.user.username
        except Exception:
            username = None

    return LoanResponse(
        id=loan.id,
        user_id=loan.user_id,
        username=username,
        amount=loan.amount,
        state=loan.state,
        jalali_year=loan.jalali_year,
        jalali_month=loan.jalali_month,
        min_amount_for_each_payment=loan.min_amount_for_each_payment,
        total_paid=loan.total_paid,
        remaining_balance=loan.remaining_balance,
        log=loan.log,
        payments=payment_summaries,
    )


@router.post(
    "/start",
    response={
        201: StartLoanResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        409: ErrorResponse,
    },
    auth=jwt_auth,
)
def start_loan_assignment(request: HttpRequest) -> tuple[int, Any]:
    """
    Trigger loan assignment for the current Jalali month.

    Any authenticated user can trigger this.
    Requirements:
    - All active users must have paid for the current month
    - No loan assignment has been done for this month yet

    The algorithm:
    1. Finds eligible users (no active loan, loan_request_amount > 0, balance check)
    2. Computes scores based on payment history
    3. Selects winner randomly from tied max-score users
    4. Checks fund balance
    5. Creates Loan record (active or no_one)
    """
    jalali = get_current_jalali()

    # Check if loan assignment already done for this month
    if Loan.objects.filter(
        jalali_year=jalali.year,
        jalali_month=jalali.month,
    ).exists():
        return 409, ErrorResponse(
            detail=f"Loan assignment already done for {jalali.year}/{jalali.month}"
        )

    try:
        loan = run_loan_assignment(jalali.year, jalali.month)
    except ValueError as e:
        return 400, ErrorResponse(detail=str(e))

    loan_response = _build_loan_response(loan)

    state_messages = {
        LoanState.ACTIVE: f"Loan assigned to user {loan.user_id} for amount {loan.amount}",
        LoanState.NO_ONE: "No eligible user found for loan assignment this month",
        LoanState.INITIAL: "Loan assignment initiated",
    }
    message = state_messages.get(loan.state, "Loan assignment completed")

    return 201, StartLoanResponse(loan=loan_response, message=message)


@router.get(
    "/history",
    response={200: list[LoanResponse], 403: ErrorResponse},
    auth=main_user_auth,
)
def get_all_loan_history(
    request: HttpRequest,
    filters: LoanHistoryFilters = Query(...),
) -> tuple[int, Any]:
    """
    Get all loan history. Only accessible by is_main users.

    Query params:
    - jalali_year_gt: Filter loans with jalali_year > this value
    - jalali_year_lt: Filter loans with jalali_year < this value
    - jalali_month_gt: Filter loans with jalali_month > this value
    - jalali_month_lt: Filter loans with jalali_month < this value
    """
    qs = (
        Loan.objects.select_related("user")
        .prefetch_related("payments__payment")
        .order_by("-jalali_year", "-jalali_month")
    )

    if filters.jalali_year_gt is not None:
        qs = qs.filter(jalali_year__gt=filters.jalali_year_gt)
    if filters.jalali_year_lt is not None:
        qs = qs.filter(jalali_year__lt=filters.jalali_year_lt)
    if filters.jalali_month_gt is not None:
        qs = qs.filter(jalali_month__gt=filters.jalali_month_gt)
    if filters.jalali_month_lt is not None:
        qs = qs.filter(jalali_month__lt=filters.jalali_month_lt)

    return 200, [_build_loan_response(loan) for loan in qs]


@router.get(
    "/my-history",
    response={200: list[LoanResponse], 401: ErrorResponse},
    auth=jwt_auth,
)
def get_my_loan_history(request: HttpRequest) -> tuple[int, Any]:
    """Get the authenticated user's loan history."""
    user: User = request.auth  # type: ignore[assignment]

    loans = (
        Loan.objects.filter(user=user)
        .select_related("user")
        .prefetch_related("payments__payment")
        .order_by("-jalali_year", "-jalali_month")
    )

    return 200, [_build_loan_response(loan) for loan in loans]


@router.get(
    "/{loan_id}",
    response={
        200: LoanResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    auth=jwt_auth,
)
def get_loan_detail(request: HttpRequest, loan_id: str) -> tuple[int, Any]:
    """
    Get details of a specific loan.
    - is_main users can see any loan
    - Regular users can only see their own loans
    """
    user: User = request.auth  # type: ignore[assignment]

    try:
        loan_uuid = uuid_module.UUID(loan_id)
    except ValueError:
        return 404, ErrorResponse(detail="Invalid loan ID format")

    try:
        loan = (
            Loan.objects.select_related("user")
            .prefetch_related("payments__payment")
            .get(id=loan_uuid)
        )
    except Loan.DoesNotExist:
        return 404, ErrorResponse(detail="Loan not found")

    # Access control
    if not user.is_main and loan.user_id != user.id:
        return 403, ErrorResponse(
            detail="You do not have permission to view this loan"
        )

    return 200, _build_loan_response(loan)
