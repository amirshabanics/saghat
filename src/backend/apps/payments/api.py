from typing import Any
from django.http import HttpRequest
from django.db import transaction
from ninja import Router

from saghat.settings.base import settings as app_settings
from apps.common.auth import jwt_auth
from apps.common.jalali import get_current_jalali
from apps.loans.models import Loan, LoanState
from apps.payments.bitpin import get_bitpin_client
from apps.payments.models import (
    Config,
    MembershipFeePayment,
    LoanPayment,
    Payment,
)
from apps.payments.schemas import (
    ConfigResponse,
    ErrorResponse,
    LoanPaymentResponse,
    MembershipFeePaymentResponse,
    PaymentRequest,
    PaymentResponse,
)
from apps.users.models import User

router = Router(tags=["payments"])


@router.post(
    "/pay",
    response={
        201: PaymentResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        409: ErrorResponse,
    },
    auth=jwt_auth,
)
def pay(request: HttpRequest, payload: PaymentRequest) -> tuple[int, Any]:
    """
    Submit a monthly payment for the current Jalali month.

    This endpoint:
    1. Validates membership_fee >= Config.min_membership_fee
    2. Validates loan repayment if user has an active loan
    3. Validates loan_request_amount (updates user model)
    4. Verifies total amount with Bitpin API
    5. Creates Payment, MembershipFeePayment, and optionally LoanPayment records
    6. Updates user.balance += membership_fee

    A user can only submit one payment per Jalali month.
    """
    user: User = request.auth  # type: ignore[assignment]
    config = Config.get_config()
    jalali = get_current_jalali()

    # Check duplicate payment for this month
    if Payment.objects.filter(
        user=user,
        jalali_year=jalali.year,
        jalali_month=jalali.month,
    ).exists():
        return 409, ErrorResponse(
            detail=f"Payment already submitted for {jalali.year}/{jalali.month}"
        )

    # Validate membership fee
    if payload.membership_fee < config.min_membership_fee:
        return 400, ErrorResponse(
            detail=(
                f"Membership fee {payload.membership_fee} is less than "
                f"minimum required {config.min_membership_fee}"
            )
        )

    # Validate loan repayment
    active_loan: Loan | None = None
    try:
        active_loan = user.loans.get(state=LoanState.ACTIVE)
    except Loan.DoesNotExist:
        active_loan = None

    if active_loan is not None:
        # User has active loan — loan payment is required
        if payload.loan is None:
            return 400, ErrorResponse(
                detail="You have an active loan. Loan repayment amount is required."
            )
        if payload.loan < active_loan.min_amount_for_each_payment:
            return 400, ErrorResponse(
                detail=(
                    f"Loan payment {payload.loan} is less than minimum required "
                    f"{active_loan.min_amount_for_each_payment}"
                )
            )
    else:
        # No active loan — loan payment must be null
        if payload.loan is not None:
            return 400, ErrorResponse(
                detail="You do not have an active loan. Loan payment must be null."
            )

    # Calculate total amount to verify with Bitpin
    total_amount = payload.membership_fee
    if payload.loan is not None:
        total_amount += payload.loan

    # Verify with Bitpin (skip if no API key configured — dev mode)
    if app_settings.BITPIN_API_KEY:
        bitpin_client = get_bitpin_client()
        is_valid, reason = bitpin_client.verify_payment_amount(
            payload.bitpin_payment_id, total_amount
        )
        if not is_valid:
            return 400, ErrorResponse(
                detail=f"Bitpin payment verification failed: {reason}"
            )

    # Create records atomically
    with transaction.atomic():
        # Update loan_request_amount on user if provided
        if payload.loan_request_amount is not None:
            user.loan_request_amount = payload.loan_request_amount

        # Increase balance by membership fee
        user.balance = user.balance + payload.membership_fee
        user.save(update_fields=["balance", "loan_request_amount"])

        # Create base Payment record
        payment = Payment.objects.create(
            user=user,
            amount=total_amount,
            jalali_year=jalali.year,
            jalali_month=jalali.month,
            bitpin_payment_id=payload.bitpin_payment_id,
        )

        # Create MembershipFeePayment
        membership_fee_payment = MembershipFeePayment.objects.create(
            payment=payment,
            amount=payload.membership_fee,
        )

        # Create LoanPayment if applicable
        loan_payment_obj: LoanPayment | None = None
        if active_loan is not None and payload.loan is not None:
            loan_payment_obj = LoanPayment.objects.create(
                payment=payment,
                loan=active_loan,
                amount=payload.loan,
            )

    # Build response
    loan_payment_response: LoanPaymentResponse | None = None
    if loan_payment_obj is not None:
        loan_payment_response = LoanPaymentResponse(
            loan_id=active_loan.id,  # type: ignore[union-attr]
            amount=loan_payment_obj.amount,
        )

    return 201, PaymentResponse(
        id=payment.id,
        user_id=user.id,
        amount=payment.amount,
        jalali_year=payment.jalali_year,
        jalali_month=payment.jalali_month,
        bitpin_payment_id=payment.bitpin_payment_id,
        membership_fee=MembershipFeePaymentResponse(
            amount=membership_fee_payment.amount
        ),
        loan_payment=loan_payment_response,
    )


@router.get(
    "/config",
    response={200: ConfigResponse},
    auth=jwt_auth,
)
def get_config(request: HttpRequest) -> tuple[int, Any]:
    """Get the current fund configuration."""
    config = Config.get_config()
    return 200, ConfigResponse(
        min_membership_fee=config.min_membership_fee,
        max_month_for_loan_payment=config.max_month_for_loan_payment,
        min_amount_for_loan_payment=config.min_amount_for_loan_payment,
    )


@router.get(
    "/my-payments",
    response={200: list[PaymentResponse], 401: ErrorResponse},
    auth=jwt_auth,
)
def list_my_payments(request: HttpRequest) -> tuple[int, Any]:
    """List all payments made by the authenticated user."""
    user: User = request.auth  # type: ignore[assignment]
    payments = (
        Payment.objects.filter(user=user)
        .select_related("membership_fee", "loan_payment", "loan_payment__loan")
        .order_by("-jalali_year", "-jalali_month")
    )

    result = []
    for p in payments:
        mf = getattr(p, "membership_fee", None)
        lp = getattr(p, "loan_payment", None)
        result.append(
            PaymentResponse(
                id=p.id,
                user_id=p.user_id,
                amount=p.amount,
                jalali_year=p.jalali_year,
                jalali_month=p.jalali_month,
                bitpin_payment_id=p.bitpin_payment_id,
                membership_fee=(
                    MembershipFeePaymentResponse(amount=mf.amount)
                    if mf
                    else None
                ),
                loan_payment=(
                    LoanPaymentResponse(loan_id=lp.loan_id, amount=lp.amount)
                    if lp
                    else None
                ),
            )
        )
    return 200, result
