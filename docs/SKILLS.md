# Saghat — Coding Skills & Best Practices

This document captures the coding patterns, conventions, and best practices that **must** be followed when writing code for the Saghat project. All examples are drawn from the actual codebase.

---

## Table of Contents

1. [Django Best Practices](#1-django-best-practices)
2. [Django Ninja Best Practices](#2-django-ninja-best-practices)
3. [Code Style](#3-code-style)
4. [Testing Patterns](#4-testing-patterns)
5. [Security](#5-security)
6. [Project-Specific Patterns](#6-project-specific-patterns)

---

## 1. Django Best Practices

### 1.1 Model Design

Always set `db_table` in `Meta` to control the actual PostgreSQL table name:

```python
# apps/loans/models.py
class Loan(models.Model):
    class Meta:
        db_table = "loans"
        unique_together = [("jalali_year", "jalali_month")]
```

Use `models.TextChoices` for enum-like fields — never raw strings:

```python
# apps/loans/models.py
class LoanState(models.TextChoices):
    INITIAL = "initial", "Initial"
    ACTIVE  = "active",  "Active"
    NO_ONE  = "no_one",  "No One"

class Loan(models.Model):
    state: str = models.CharField(
        max_length=20,
        choices=LoanState.choices,
        default=LoanState.INITIAL,
    )
```

Use `DecimalField` (not `FloatField`) for all monetary / financial values:

```python
balance: Decimal = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
```

Use `UUIDField` as primary key for entities that are exposed in URLs:

```python
id: uuid.UUID = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

Use `settings.AUTH_USER_MODEL` (not a direct import) for ForeignKey to User:

```python
user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.PROTECT,
    related_name="loans",
    null=True,
    blank=True,
)
```

Add `__str__` to every model for readable admin/shell output:

```python
def __str__(self) -> str:
    return f"Loan({self.jalali_year}/{self.jalali_month}, state={self.state})"
```

Use `@property` for computed fields that derive from existing data:

```python
@property
def total_paid(self) -> Decimal:
    from django.db.models import Sum
    result = self.payments.aggregate(total=Sum("amount"))["total"]
    return result or Decimal("0")

@property
def remaining_balance(self) -> Decimal:
    if self.amount is None:
        return Decimal("0")
    return self.amount - self.total_paid
```

### 1.2 QuerySet Optimization

Always use `select_related` for ForeignKey / OneToOne traversals and `prefetch_related` for reverse FK / M2M:

```python
# apps/loans/api.py — avoids N+1 on loan.user and loan.payments
qs = (
    Loan.objects.select_related("user")
    .prefetch_related("payments__payment")
    .order_by("-jalali_year", "-jalali_month")
)
```

Use `update_fields` when saving only specific columns — never call a bare `.save()` after changing one field:

```python
# apps/users/api.py
user.loan_request_amount = payload.loan_request_amount
user.save(update_fields=["loan_request_amount"])
```

Use `.exists()` for existence checks instead of fetching the full object:

```python
if User.objects.filter(username=payload.username).exists():
    return 400, ErrorResponse(detail="Username already exists")
```

### 1.3 Migration Best Practices

- Run `uv run manage.py makemigrations` after every model change.
- Never edit a migration that has already been applied in production.
- Keep migrations small and focused — one logical change per migration.
- Use `RunPython` with a reverse function for data migrations.
- Always test migrations with `uv run manage.py migrate --run-syncdb` in a clean DB.

### 1.4 `transaction.atomic()`

Wrap any sequence of writes that must succeed or fail together:

```python
# apps/payments/api.py
with transaction.atomic():
    user.balance = user.balance + payload.membership_fee
    user.save(update_fields=["balance", "loan_request_amount"])

    payment = Payment.objects.create(...)
    MembershipFeePayment.objects.create(payment=payment, ...)
    if active_loan is not None:
        LoanPayment.objects.create(payment=payment, loan=active_loan, ...)
```

### 1.5 Custom Model Managers and QuerySets

Prefer custom managers for reusable query logic. Example pattern (not yet in codebase but recommended):

```python
class ActiveLoanManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(state=LoanState.ACTIVE)

class Loan(models.Model):
    objects = models.Manager()
    active = ActiveLoanManager()
```

### 1.6 Django Signals

**Avoid signals** for business logic — they make code hard to trace. Use them only for:

- Sending notifications after a model save (e.g., email on user creation).
- Invalidating caches.

Never use signals to trigger other database writes that belong in a `transaction.atomic()` block.

---

## 2. Django Ninja Best Practices

### 2.1 Router Organization

Each Django app owns exactly one `router` in its `api.py`. The router is mounted in `saghat/urls.py`:

```python
# saghat/urls.py
from ninja import NinjaAPI
from apps.users.api    import router as users_router
from apps.payments.api import router as payments_router
from apps.loans.api    import router as loans_router

api = NinjaAPI(title="Saghat API", version="1.0.0", docs_url="/docs")
api.add_router("/auth",     users_router)
api.add_router("/payments", payments_router)
api.add_router("/loans",    loans_router)
```

Each app's router is tagged for Swagger grouping:

```python
# apps/loans/api.py
router = Router(tags=["loans"])
```

### 2.2 Schema Design with Pydantic v2

Use `BaseModel` from `pydantic` (not `ninja.Schema`) for schemas. Always use Pydantic v2 APIs:

| ❌ Pydantic v1 (forbidden) | ✅ Pydantic v2 (required)               |
| -------------------------- | --------------------------------------- |
| `.dict()`                  | `.model_dump()`                         |
| `.json()`                  | `.model_dump_json()`                    |
| `class Config:`            | `model_config = {...}`                  |
| `@validator`               | `@field_validator` / `@model_validator` |

Use `model_config = {"from_attributes": True}` on response schemas that are built from ORM objects:

```python
# apps/users/schemas.py
class UserResponse(BaseModel):
    id: int
    username: str
    balance: Decimal
    has_active_loan: bool

    model_config = {"from_attributes": True}
```

Use `Field(...)` for validation constraints:

```python
class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=8)
    loan_request_amount: Decimal = Field(default=Decimal("0"), ge=0)
```

Use `@field_validator` for custom field-level validation:

```python
@field_validator("username")
@classmethod
def username_alphanumeric(cls, v: str) -> str:
    if not re.match(r"^[\w.-]+$", v):
        raise ValueError("Username may only contain letters, digits, underscores, dots, and hyphens")
    return v
```

### 2.3 Authentication

Import the pre-instantiated singletons from `apps.common.auth` — never instantiate auth classes inline:

```python
from apps.common.auth import jwt_auth, main_user_auth

@router.get("/me", response={200: UserResponse, 401: ErrorResponse}, auth=jwt_auth)
def get_me(request: HttpRequest) -> tuple[int, Any]: ...

@router.post("/users", response={201: UserResponse, 403: ErrorResponse}, auth=main_user_auth)
def create_user(request: HttpRequest, payload: CreateUserRequest) -> tuple[int, Any]: ...
```

Use `auth=None` to explicitly mark public endpoints:

```python
@router.post("/login", response={200: LoginResponse, 401: ErrorResponse}, auth=None)
def login(request: HttpRequest, payload: LoginRequest) -> tuple[int, Any]: ...
```

Access the authenticated user via `request.auth`:

```python
user: User = request.auth  # type: ignore[assignment]
```

### 2.4 Error Handling

Return typed error tuples — never raise `HttpError` directly. Always declare all possible status codes in the `response` dict:

```python
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
    if duplicate:
        return 409, ErrorResponse(detail="Payment already submitted for this month")
    if invalid:
        return 400, ErrorResponse(detail="Membership fee below minimum")
    ...
    return 201, PaymentResponse(...)
```

### 2.5 Response Schemas

Always define explicit response schemas. Never return raw dicts. Use `list[SomeSchema]` for list endpoints:

```python
@router.get("/users", response={200: list[UserResponse], 403: ErrorResponse}, auth=main_user_auth)
def list_users(request: HttpRequest) -> tuple[int, Any]:
    users = User.objects.all().order_by("username")
    return 200, [UserResponse(...) for u in users]
```

### 2.6 Query Parameters

Use a Pydantic schema with `Query(...)` for structured query parameter filtering:

```python
# apps/loans/schemas.py
class LoanHistoryFilters(BaseModel):
    jalali_year_gt: Optional[int] = None
    jalali_year_lt: Optional[int] = None

# apps/loans/api.py
from ninja import Query

@router.get("/history", response={200: list[LoanResponse], 403: ErrorResponse}, auth=main_user_auth)
def get_all_loan_history(
    request: HttpRequest,
    filters: LoanHistoryFilters = Query(...),
) -> tuple[int, Any]:
    qs = Loan.objects.all()
    if filters.jalali_year_gt is not None:
        qs = qs.filter(jalali_year__gt=filters.jalali_year_gt)
    return 200, [_build_loan_response(loan) for loan in qs]
```

### 2.7 Helper Functions

Extract complex ORM-to-schema mapping into private helper functions (prefix with `_`):

```python
# apps/loans/api.py
def _build_loan_response(loan: Loan) -> LoanResponse:
    """Helper to build a LoanResponse from a Loan ORM object."""
    payments = loan.payments.select_related("payment").order_by(...)
    ...
    return LoanResponse(...)
```

### 2.8 Pagination

For large datasets, use offset/limit pagination. Recommended pattern:

```python
class PaginatedResponse(BaseModel):
    count: int
    results: list[SomeSchema]

@router.get("/items", response={200: PaginatedResponse})
def list_items(request: HttpRequest, offset: int = 0, limit: int = 20) -> tuple[int, Any]:
    qs = Item.objects.all()
    total = qs.count()
    items = qs[offset : offset + limit]
    return 200, PaginatedResponse(count=total, results=[...])
```

---

## 3. Code Style

### 3.1 Ruff

All code must pass Ruff linting and formatting. Configuration in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
```

Run before committing:

```bash
uv run ruff check .
uv run ruff format .
```

### 3.2 Type Hints

Type hints are **mandatory** everywhere — function signatures, local variables where the type is not obvious, and class attributes:

```python
def decode_access_token(token: str) -> Optional[int]: ...

user: User = request.auth  # type: ignore[assignment]
active_loan: Loan | None = None
```

Use `X | Y` union syntax (Python 3.10+) for new code. Use `Optional[X]` only when importing from `typing` is already present.

### 3.3 Pydantic v2 Patterns

- Use `.model_dump()` not `.dict()`
- Use `.model_dump_json()` not `.json()`
- Use `model_config = {"from_attributes": True}` not `class Config: orm_mode = True`
- Use `@field_validator` not `@validator`

### 3.4 String Formatting

Use f-strings — never `.format()` or `%` formatting:

```python
# ✅
return 409, ErrorResponse(detail=f"Loan assignment already done for {jalali.year}/{jalali.month}")

# ❌
return 409, ErrorResponse(detail="Loan assignment already done for {}/{}".format(jalali.year, jalali.month))
```

### 3.5 Path Handling

Use `pathlib.Path` over `os.path` for all filesystem operations:

```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
```

### 3.6 Settings

All settings are accessed via the `settings` singleton from `saghat.settings.base`:

```python
from saghat.settings.base import settings
token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

Never import from `django.conf.settings` for app-level settings — use the typed `Settings` Pydantic model.

---

## 4. Testing Patterns

### 4.1 Framework

Use `pytest` with `pytest-django`. Test files live alongside the app code or in a `tests/` subdirectory:

```
apps/users/
    tests/
        test_api.py
        test_models.py
```

Configure pytest in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "saghat.settings.dev"
```

### 4.2 Database Tests

Use `django.test.TestCase` for tests that need database access:

```python
from django.test import TestCase
from apps.users.models import User

class UserModelTest(TestCase):
    def test_has_active_loan_false_by_default(self) -> None:
        user = User.objects.create_user(username="test", password="testpass123")
        self.assertFalse(user.has_active_loan)
```

### 4.3 API Tests

Use Django Ninja's `TestClient` for API endpoint tests:

```python
from ninja.testing import TestClient
from apps.users.api import router

client = TestClient(router)

def test_login_invalid_credentials() -> None:
    response = client.post("/login", json={"username": "bad", "password": "bad"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
```

### 4.4 Factory Patterns

Use factory functions (or `factory_boy`) to create test data:

```python
def make_user(username: str = "testuser", is_main: bool = False) -> User:
    return User.objects.create_user(
        username=username,
        password="testpass123",
        is_main=is_main,
    )
```

### 4.5 Mocking External Services

Mock the Bitpin API client in tests to avoid real HTTP calls:

```python
from unittest.mock import patch, MagicMock

def test_pay_skips_bitpin_when_no_api_key(self) -> None:
    with patch("apps.payments.api.app_settings") as mock_settings:
        mock_settings.BITPIN_API_KEY = None
        response = self.client.post("/api/payments/pay", ...)
        # Bitpin client is never called
```

---

## 5. Security

### 5.1 Passwords

Never store plain-text passwords. Always use Django's `create_user()` or `set_password()`:

```python
# ✅ Correct
user = User.objects.create_user(username=payload.username, password=payload.password)

# ❌ Never do this
user = User(username=payload.username, password=payload.password)
user.save()
```

### 5.2 JWT Token Validation

Tokens are validated in `apps/common/auth.py`. The `decode_access_token` function returns `None` on any error — callers must handle `None`:

```python
user_id = decode_access_token(token)
if user_id is None:
    return None  # Django Ninja treats None as 401 Unauthorized
```

### 5.3 Permission Checks at the API Layer

Perform authorization checks at the start of the endpoint function, before any DB writes:

```python
# apps/loans/api.py
user: User = request.auth  # type: ignore[assignment]
if not user.is_main and loan.user_id != user.id:
    return 403, ErrorResponse(detail="You do not have permission to view this loan")
```

### 5.4 Environment Variables for Secrets

All secrets live in `.env` and are loaded via the `Settings` Pydantic model. Never hardcode secrets:

```python
# saghat/settings/base.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    SECRET_KEY: str          # required — no default
    JWT_SECRET_KEY: str      # required — no default
    BITPIN_API_KEY: Optional[str] = None  # optional
```

The `.env` file is in `.gitignore`. Use `.env.example` to document required variables.

---

## 6. Project-Specific Patterns

### 6.1 Authentication Flow

Two auth levels exist in this project:

| Auth class     | Singleton        | Who can use it            |
| -------------- | ---------------- | ------------------------- |
| `JWTAuth`      | `jwt_auth`       | Any active user           |
| `MainUserAuth` | `main_user_auth` | Only `is_main=True` users |

Both are defined in [`apps/common/auth.py`](../apps/common/auth.py) and imported as singletons:

```python
from apps.common.auth import jwt_auth, main_user_auth
```

After authentication, the user object is available as `request.auth`:

```python
user: User = request.auth  # type: ignore[assignment]
```

### 6.2 Adding a New API Endpoint

1. **Define schemas** in `apps/<app>/schemas.py`:

   ```python
   class MyRequest(BaseModel):
       name: str = Field(..., min_length=1)

   class MyResponse(BaseModel):
       id: int
       name: str
       model_config = {"from_attributes": True}
   ```

2. **Add the endpoint** to `apps/<app>/api.py`:

   ```python
   @router.post(
       "/my-endpoint",
       response={201: MyResponse, 400: ErrorResponse},
       auth=jwt_auth,
   )
   def my_endpoint(request: HttpRequest, payload: MyRequest) -> tuple[int, Any]:
       user: User = request.auth  # type: ignore[assignment]
       # ... business logic ...
       return 201, MyResponse(...)
   ```

3. **No changes needed** to `saghat/urls.py` — the router is already mounted.

4. **Write tests** in `apps/<app>/tests/test_api.py`.

5. **Run Ruff**: `uv run ruff check . && uv run ruff format .`

### 6.3 Adding a New Model with Migration

1. **Define the model** in `apps/<app>/models.py` with `db_table` in `Meta`.
2. **Run**: `uv run manage.py makemigrations`
3. **Review** the generated migration in `apps/<app>/migrations/`.
4. **Apply**: `uv run manage.py migrate`
5. **Register** in Django admin if needed.

### 6.4 Jalali Date Utilities

The project uses the Iranian (Jalali/Shamsi) calendar for all date-based business logic. Use the helpers from [`apps/common/jalali.py`](../apps/common/jalali.py):

```python
from apps.common.jalali import get_current_jalali, gregorian_to_jalali

# Get current Jalali year and month
jalali = get_current_jalali()
print(jalali.year, jalali.month)  # e.g. 1403, 12

# Convert a Gregorian datetime
from datetime import datetime
jdate = gregorian_to_jalali(datetime.now())
```

`JalaliDate` is a `NamedTuple` with `.year` and `.month` fields. It is used as the primary time dimension for payments and loans.

### 6.5 Settings Access Pattern

Always import the typed `settings` singleton — not `django.conf.settings` — for app-level config:

```python
from saghat.settings.base import settings

if settings.BITPIN_API_KEY:
    # only call Bitpin in production
    ...
```

### 6.6 Bitpin Integration

The Bitpin payment gateway client lives in [`apps/payments/bitpin.py`](../apps/payments/bitpin.py). Use the factory function:

```python
from apps.payments.bitpin import get_bitpin_client

bitpin_client = get_bitpin_client()
is_valid, reason = bitpin_client.verify_payment_amount(payment_id, total_amount)
```

In development, set `BITPIN_API_KEY=` (empty) in `.env` to skip Bitpin verification.
