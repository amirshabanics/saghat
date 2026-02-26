from decimal import Decimal
from typing import Optional
import uuid
from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    """
    Request body for submitting a monthly payment.

    Fields:
    - membership_fee: Amount paid as monthly membership fee (>= Config.min_membership_fee)
    - loan: Amount paid toward active loan repayment (>= Loan.min_amount_for_each_payment).
            Must be null/omitted if user has no active loan.
    - loan_request_amount: The USDT amount this user wants if they win the loan this month.
                           Stored on the User model. Set to 0 or null to opt out.
    - bitpin_payment_id: The payment ID from Bitpin to verify the transaction.
    """

    membership_fee: Decimal = Field(..., gt=0)
    loan: Optional[Decimal] = Field(default=None, gt=0)
    loan_request_amount: Optional[Decimal] = Field(default=None, ge=0)
    bitpin_payment_id: str = Field(..., min_length=1)


class MembershipFeePaymentResponse(BaseModel):
    amount: Decimal

    model_config = {"from_attributes": True}


class LoanPaymentResponse(BaseModel):
    loan_id: uuid.UUID
    amount: Decimal

    model_config = {"from_attributes": True}


class PaymentResponse(BaseModel):
    id: uuid.UUID
    user_id: int
    amount: Decimal
    jalali_year: int
    jalali_month: int
    bitpin_payment_id: str
    membership_fee: Optional[MembershipFeePaymentResponse]
    loan_payment: Optional[LoanPaymentResponse]

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    detail: str


class ConfigResponse(BaseModel):
    min_membership_fee: Decimal
    max_month_for_loan_payment: int
    min_amount_for_loan_payment: Decimal

    model_config = {"from_attributes": True}
