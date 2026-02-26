from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from jose import jwt, JWTError
from ninja.security import HttpBearer
from django.http import HttpRequest
from saghat.settings.base import settings


def create_access_token(user_id: int) -> str:
    """Create a signed JWT access token for the given user ID."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> Optional[int]:
    """Decode a JWT access token and return the user ID, or None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        return int(user_id) if user_id else None
    except JWTError:
        return None


class JWTAuth(HttpBearer):
    """Bearer auth that authenticates any active user."""

    def authenticate(self, request: HttpRequest, token: str) -> Optional[Any]:
        from apps.users.models import User

        user_id = decode_access_token(token)
        if user_id is None:
            return None
        try:
            user = User.objects.get(pk=user_id, is_active=True)
            request.user = user
            return user
        except User.DoesNotExist:
            return None


class MainUserAuth(HttpBearer):
    """Auth that only allows is_main users."""

    def authenticate(self, request: HttpRequest, token: str) -> Optional[Any]:
        from apps.users.models import User

        user_id = decode_access_token(token)
        if user_id is None:
            return None
        try:
            user = User.objects.get(pk=user_id, is_active=True, is_main=True)
            request.user = user
            return user
        except User.DoesNotExist:
            return None


jwt_auth = JWTAuth()
main_user_auth = MainUserAuth()
