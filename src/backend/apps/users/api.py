from typing import Any

from django.contrib.auth import authenticate
from django.http import HttpRequest
from ninja import Router

from apps.common.auth import create_access_token, jwt_auth, main_user_auth
from apps.users.models import User
from apps.users.schemas import (
    CreateUserRequest,
    ErrorResponse,
    LoginRequest,
    LoginResponse,
    UpdateLoanRequestAmountRequest,
    UserResponse,
)

router = Router(tags=["auth"])


@router.post(
    "/login", response={200: LoginResponse, 401: ErrorResponse}, auth=None
)
def login(request: HttpRequest, payload: LoginRequest) -> tuple[int, Any]:
    """
    Authenticate a user and return a JWT access token.
    Uses Django's built-in authenticate() which checks username/password.
    """
    user = authenticate(
        request, username=payload.username, password=payload.password
    )
    if user is None:
        return 401, ErrorResponse(detail="Invalid username or password")

    token = create_access_token(user.id)
    return 200, LoginResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        is_main=user.is_main,
    )


@router.post(
    "/users",
    response={201: UserResponse, 400: ErrorResponse, 403: ErrorResponse},
    auth=main_user_auth,
)
def create_user(
    request: HttpRequest, payload: CreateUserRequest
) -> tuple[int, Any]:
    """
    Create a new fund member. Only accessible by is_main users.
    """
    if User.objects.filter(username=payload.username).exists():
        return 400, ErrorResponse(detail="Username already exists")

    user = User.objects.create_user(
        username=payload.username,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        is_main=payload.is_main,
        loan_request_amount=payload.loan_request_amount,
    )
    return 201, UserResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_main=user.is_main,
        balance=user.balance,
        loan_request_amount=user.loan_request_amount,
        has_active_loan=user.has_active_loan,
    )


@router.get(
    "/me",
    response={200: UserResponse, 401: ErrorResponse},
    auth=jwt_auth,
)
def get_me(request: HttpRequest) -> tuple[int, Any]:
    """Get the currently authenticated user's profile."""
    user: User = request.auth  # type: ignore[assignment]
    return 200, UserResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_main=user.is_main,
        balance=user.balance,
        loan_request_amount=user.loan_request_amount,
        has_active_loan=user.has_active_loan,
    )


@router.patch(
    "/me/loan-request",
    response={200: UserResponse, 400: ErrorResponse, 401: ErrorResponse},
    auth=jwt_auth,
)
def update_loan_request_amount(
    request: HttpRequest, payload: UpdateLoanRequestAmountRequest
) -> tuple[int, Any]:
    """
    Update the authenticated user's loan_request_amount.
    Set to 0 to opt out of loan assignment.
    """
    user: User = request.auth  # type: ignore[assignment]
    user.loan_request_amount = payload.loan_request_amount
    user.save(update_fields=["loan_request_amount"])
    return 200, UserResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_main=user.is_main,
        balance=user.balance,
        loan_request_amount=user.loan_request_amount,
        has_active_loan=user.has_active_loan,
    )


@router.get(
    "/users",
    response={200: list[UserResponse], 403: ErrorResponse},
    auth=main_user_auth,
)
def list_users(request: HttpRequest) -> tuple[int, Any]:
    """List all fund members. Only accessible by is_main users."""
    users = User.objects.all().order_by("username")
    result = [
        UserResponse(
            id=u.id,
            username=u.username,
            first_name=u.first_name,
            last_name=u.last_name,
            email=u.email,
            is_main=u.is_main,
            balance=u.balance,
            loan_request_amount=u.loan_request_amount,
            has_active_loan=u.has_active_loan,
        )
        for u in users
    ]
    return 200, result
