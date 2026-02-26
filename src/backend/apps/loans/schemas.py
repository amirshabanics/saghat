import uuid
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel


class LoanPaymentSummary(BaseModel):
    id: uuid.UUID
    amount: Decimal
    jalali_year: int
    jalali_month: int

    model_config = {"from_attributes": True}


class LoanResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[int]
    username: Optional[str]
    amount: Optional[Decimal]
    state: str
    jalali_year: int
    jalali_month: int
    min_amount_for_each_payment: Optional[Decimal]
    total_paid: Decimal
    remaining_balance: Decimal
    log: dict[str, Any]
    payments: list[LoanPaymentSummary]

    model_config = {"from_attributes": True}


class StartLoanResponse(BaseModel):
    loan: LoanResponse
    message: str


class ErrorResponse(BaseModel):
    detail: str


class LoanHistoryFilters(BaseModel):
    jalali_year_gt: Optional[int] = None
    jalali_year_lt: Optional[int] = None
    jalali_month_gt: Optional[int] = None
    jalali_month_lt: Optional[int] = None
