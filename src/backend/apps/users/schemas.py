import re
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    is_main: bool


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=8)
    first_name: str = Field(default="")
    last_name: str = Field(default="")
    email: str = Field(default="")
    is_main: bool = Field(default=False)
    loan_request_amount: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        # Allow letters, digits, underscores, hyphens, dots
        if not re.match(r"^[\w.-]+$", v):
            raise ValueError(
                "Username may only contain letters, digits, underscores, dots, and hyphens"
            )
        return v


class UserResponse(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
    is_main: bool
    balance: Decimal
    loan_request_amount: Decimal
    has_active_loan: bool

    model_config = {"from_attributes": True}


class UpdateLoanRequestAmountRequest(BaseModel):
    loan_request_amount: Decimal = Field(..., ge=0)


class ErrorResponse(BaseModel):
    detail: str
