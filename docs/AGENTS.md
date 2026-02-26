# Saghat — AI Agent Guide

This file is written for AI coding agents (Kilo Code, Roo Code, Copilot, etc.) to understand how to work effectively in the Saghat codebase. Read this before making any changes.

---

## 1. Project Overview

**Saghat** is a private investment-fund management system. Members pay a monthly membership fee (in USDT via Bitpin), and each month one eligible member is selected by a scoring algorithm to receive a loan from the pooled funds. The system tracks payments, loan assignments, and repayments.

Key business concepts:
- **Payment** — a monthly contribution by a fund member (membership fee + optional loan repayment).
- **Loan** — a monthly loan assignment to one member, selected by the scoring algorithm.
- **Config** — a singleton model holding fund-wide settings (minimum fees, repayment rules).
- **Jalali calendar** — all date logic uses the Iranian (Shamsi) calendar, not Gregorian.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | Django 5.2 |
| REST API | Django Ninja 1.3+ (FastAPI-style, Pydantic v2) |
| Database | PostgreSQL (via `psycopg[binary]` v3) |
| Cache | Redis (via `django-redis`) |
| Auth | Custom JWT (`python-jose`) — no DRF, no `djangorestframework-simplejwt` |
| Settings | `pydantic-settings` (`BaseSettings` reading from `.env`) |
| Package manager | `uv` (not pip, not poetry) |
| Linter/formatter | Ruff (`line-length = 100`, `target-version = "py312"`) |
| ASGI server | Uvicorn workers under Gunicorn (production) |
| Jalali dates | `jdatetime` library |
| Payment gateway | Bitpin API (USDT payments) |
| Testing | `pytest` + `pytest-django` |

---

## 3. Project Structure

```
saghat/                     ← Django project package
    settings/
        base.py             ← Pydantic Settings + Django config (source of truth)
        dev.py              ← Dev overrides (DEBUG=True, etc.)
        prod.py             ← Production overrides
    urls.py                 ← NinjaAPI instance + router mounting
    wsgi.py / asgi.py

apps/                       ← All Django apps live here
    common/
        auth.py             ← JWTAuth, MainUserAuth, create_access_token
        jalali.py           ← get_current_jalali(), gregorian_to_jalali()
    users/
        models.py           ← Custom User (extends AbstractUser)
        schemas.py          ← Pydantic request/response schemas
        api.py              ← Router + endpoints
        apps.py             ← AppConfig
        migrations/
    payments/
        models.py           ← Config, Payment, MembershipFeePayment, LoanPayment
        schemas.py
        api.py
        bitpin.py           ← Bitpin HTTP client
        apps.py
        migrations/
    loans/
        models.py           ← Loan, LoanState
        schemas.py
        api.py
        algorithm.py        ← Loan assignment scoring algorithm
        apps.py
        migrations/

docs/
    architecture.md         ← System architecture overview
    SKILLS.md               ← Coding patterns and best practices
    AGENTS.md               ← This file

manage.py
pyproject.toml              ← Dependencies + Ruff config
.env                        ← Local secrets (gitignored)
.env.example                ← Template for required env vars
Dockerfile
compose.yml
```

---

## 4. Key Conventions

### File naming (per app)

Every Django app follows this exact structure:

| File | Purpose |
|---|---|
| `models.py` | Django ORM models |
| `schemas.py` | Pydantic v2 request/response schemas |
| `api.py` | Django Ninja `Router` + endpoint functions |
| `apps.py` | `AppConfig` subclass |
| `migrations/` | Django migrations |

### Router naming

Each app's `api.py` exports a single `router` variable:

```python
from ninja import Router
router = Router(tags=["payments"])  # tag matches the app name
```

Routers are mounted in [`saghat/urls.py`](../saghat/urls.py):

```python
api.add_router("/auth",     users_router)
api.add_router("/payments", payments_router)
api.add_router("/loans",    loans_router)
```

### Schema naming conventions

| Suffix | Usage |
|---|---|
| `*Request` | Input schema for POST/PATCH body (e.g., `LoginRequest`, `PaymentRequest`) |
| `*Response` | Output schema for any endpoint (e.g., `UserResponse`, `LoanResponse`) |
| `*Filters` | Query parameter schema used with `Query(...)` (e.g., `LoanHistoryFilters`) |
| `ErrorResponse` | Standard error body — always `{"detail": "..."}` |

### Auth import pattern

Always import the pre-instantiated singletons — never instantiate auth classes inline:

```python
from apps.common.auth import jwt_auth, main_user_auth
```

---

## 5. How to Add a New Feature

Follow these steps in order:

### Step 1 — Define schemas in `apps/<app>/schemas.py`

```python
from pydantic import BaseModel, Field
from decimal import Decimal

class MyThingRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0)

class MyThingResponse(BaseModel):
    id: int
    name: str
    amount: Decimal
    model_config = {"from_attributes": True}

class ErrorResponse(BaseModel):  # or import from existing schemas
    detail: str
```

### Step 2 — Add the model (if needed) in `apps/<app>/models.py`

```python
class MyThing(models.Model):
    name: str = models.CharField(max_length=100)
    amount: Decimal = models.DecimalField(max_digits=20, decimal_places=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "my_things"

    def __str__(self) -> str:
        return self.name
```

Then run:
```bash
uv run manage.py makemigrations
uv run manage.py migrate
```

### Step 3 — Add the endpoint in `apps/<app>/api.py`

```python
from typing import Any
from django.http import HttpRequest
from ninja import Router
from apps.common.auth import jwt_auth
from apps.myapp.models import MyThing
from apps.myapp.schemas import MyThingRequest, MyThingResponse, ErrorResponse

router = Router(tags=["mythings"])

@router.post(
    "/",
    response={201: MyThingResponse, 400: ErrorResponse},
    auth=jwt_auth,
)
def create_my_thing(request: HttpRequest, payload: MyThingRequest) -> tuple[int, Any]:
    user = request.auth  # type: ignore[assignment]
    thing = MyThing.objects.create(name=payload.name, amount=payload.amount)
    return 201, MyThingResponse(id=thing.id, name=thing.name, amount=thing.amount)
```

### Step 4 — Mount the router (only for new apps)

If this is a brand-new Django app, add to `saghat/urls.py`:

```python
from apps.myapp.api import router as myapp_router
api.add_router("/mythings", myapp_router)
```

And register the app in `saghat/settings/base.py`:

```python
INSTALLED_APPS = [
    ...
    "apps.myapp.apps.MyAppConfig",
]
```

### Step 5 — Lint and format

```bash
uv run ruff check .
uv run ruff format .
```

### Step 6 — Write tests

```bash
# Run all tests
uv run pytest

# Run tests for a specific app
uv run pytest apps/myapp/
```

---

## 6. Common Patterns (Copy-Paste Ready)

### Pattern: Authenticated endpoint returning a single object

```python
@router.get(
    "/{item_id}",
    response={200: ItemResponse, 401: ErrorResponse, 404: ErrorResponse},
    auth=jwt_auth,
)
def get_item(request: HttpRequest, item_id: int) -> tuple[int, Any]:
    user: User = request.auth  # type: ignore[assignment]
    try:
        item = Item.objects.select_related("user").get(pk=item_id, user=user)
    except Item.DoesNotExist:
        return 404, ErrorResponse(detail="Item not found")
    return 200, ItemResponse.model_validate(item)
```

### Pattern: Admin-only list endpoint with filters

```python
from ninja import Query

@router.get(
    "/",
    response={200: list[ItemResponse], 403: ErrorResponse},
    auth=main_user_auth,
)
def list_items(
    request: HttpRequest,
    filters: ItemFilters = Query(...),
) -> tuple[int, Any]:
    qs = Item.objects.select_related("user").order_by("-created_at")
    if filters.user_id is not None:
        qs = qs.filter(user_id=filters.user_id)
    return 200, [ItemResponse.model_validate(i) for i in qs]
```

### Pattern: Atomic write with conflict check

```python
from django.db import transaction

@router.post(
    "/",
    response={201: ItemResponse, 409: ErrorResponse},
    auth=jwt_auth,
)
def create_item(request: HttpRequest, payload: ItemRequest) -> tuple[int, Any]:
    user: User = request.auth  # type: ignore[assignment]
    if Item.objects.filter(user=user, month=payload.month).exists():
        return 409, ErrorResponse(detail="Item already exists for this month")
    with transaction.atomic():
        item = Item.objects.create(user=user, **payload.model_dump())
    return 201, ItemResponse.model_validate(item)
```

### Pattern: Using Jalali date

```python
from apps.common.jalali import get_current_jalali

jalali = get_current_jalali()
# jalali.year → int (e.g. 1403)
# jalali.month → int (1–12)
```

### Pattern: Checking settings at runtime

```python
from saghat.settings.base import settings

if settings.BITPIN_API_KEY:
    # production path — call external API
    ...
else:
    # dev path — skip external call
    ...
```

### Pattern: UUID primary key model

```python
import uuid

class MyModel(models.Model):
    id: uuid.UUID = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

### Pattern: TextChoices enum

```python
class MyState(models.TextChoices):
    PENDING   = "pending",   "Pending"
    COMPLETED = "completed", "Completed"
    FAILED    = "failed",    "Failed"

class MyModel(models.Model):
    state: str = models.CharField(
        max_length=20,
        choices=MyState.choices,
        default=MyState.PENDING,
    )
```

---

## 7. Testing

### Running tests

```bash
# All tests
uv run pytest

# With verbose output
uv run pytest -v

# Specific file
uv run pytest apps/users/tests/test_api.py

# Specific test
uv run pytest apps/users/tests/test_api.py::test_login_success
```

### Test file location

Place test files in `apps/<app>/tests/`:

```
apps/users/
    tests/
        __init__.py
        test_api.py
        test_models.py
```

### Django Ninja TestClient

```python
from ninja.testing import TestClient
from apps.users.api import router

client = TestClient(router)

def test_login_returns_token() -> None:
    # Create user first
    from apps.users.models import User
    User.objects.create_user(username="alice", password="secret123")

    response = client.post("/login", json={"username": "alice", "password": "secret123"})
    assert response.status_code == 200
    assert "access_token" in response.json()
```

### pytest-django marker

```python
import pytest

@pytest.mark.django_db
def test_something() -> None:
    ...
```

---

## 8. Running the Project

### Development

```bash
# Install dependencies
uv sync

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY

# Apply migrations
uv run manage.py migrate

# Create a superuser / main user
uv run manage.py setup_fund  # custom management command

# Start dev server
uv run manage.py runserver
```

API docs available at: `http://127.0.0.1:8000/api/docs`

### Production (Docker)

```bash
docker compose up --build
```

The `compose.yml` starts:
- `web` — Gunicorn + Uvicorn workers serving the Django app
- `db` — PostgreSQL
- `redis` — Redis cache

### Environment Variables

See `.env.example` for all required variables. Key ones:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key |
| `DATABASE_URL` | ✅ | PostgreSQL DSN (`postgresql://user:pass@host/db`) |
| `JWT_SECRET_KEY` | ✅ | Secret for signing JWT tokens |
| `REDIS_URL` | ✅ | Redis DSN (`redis://localhost:6379/0`) |
| `APP_ENV` | ✅ | `dev` or `prod` |
| `BITPIN_API_KEY` | ❌ | Leave empty in dev to skip payment verification |

---

## 9. Important Files Map

| File | What it does |
|---|---|
| [`saghat/urls.py`](../saghat/urls.py) | Creates `NinjaAPI` instance, mounts all routers |
| [`saghat/settings/base.py`](../saghat/settings/base.py) | Pydantic `Settings` class + Django config dict |
| [`apps/common/auth.py`](../apps/common/auth.py) | `JWTAuth`, `MainUserAuth`, `create_access_token`, `decode_access_token` |
| [`apps/common/jalali.py`](../apps/common/jalali.py) | `get_current_jalali()`, `gregorian_to_jalali()` |
| [`apps/users/models.py`](../apps/users/models.py) | `User` model (extends `AbstractUser`) |
| [`apps/loans/models.py`](../apps/loans/models.py) | `Loan`, `LoanState` |
| [`apps/loans/algorithm.py`](../apps/loans/algorithm.py) | Loan assignment scoring algorithm |
| [`apps/payments/models.py`](../apps/payments/models.py) | `Config`, `Payment`, `MembershipFeePayment`, `LoanPayment` |
| [`apps/payments/bitpin.py`](../apps/payments/bitpin.py) | Bitpin payment gateway HTTP client |
| [`pyproject.toml`](../pyproject.toml) | Dependencies, Ruff config |
| [`.env.example`](../.env.example) | Template for required environment variables |

---

## 10. Do's and Don'ts

### ✅ Do

- **Do** use `uv run` for all Python commands (`uv run manage.py`, `uv run pytest`, `uv run ruff`).
- **Do** import `jwt_auth` / `main_user_auth` singletons from `apps.common.auth`.
- **Do** declare all possible HTTP status codes in the `response={}` dict of every endpoint.
- **Do** use `transaction.atomic()` for any multi-step write sequence.
- **Do** use `update_fields=[...]` when saving only specific model fields.
- **Do** use `select_related` / `prefetch_related` to avoid N+1 queries.
- **Do** use `model_config = {"from_attributes": True}` on response schemas built from ORM objects.
- **Do** use `TextChoices` for all enum-like model fields.
- **Do** use `db_table` in every model's `Meta` class.
- **Do** use `DecimalField` (not `FloatField`) for all monetary values.
- **Do** use `get_current_jalali()` for the current Jalali year/month.
- **Do** use f-strings for string interpolation.
- **Do** run `uv run ruff check . && uv run ruff format .` before committing.
- **Do** write docstrings on every endpoint function.

### ❌ Don't

- **Don't** use `pip install` — use `uv add <package>` to add dependencies.
- **Don't** import `django.conf.settings` for app-level config — use `saghat.settings.base.settings`.
- **Don't** use `.dict()` or `.json()` — use `.model_dump()` / `.model_dump_json()` (Pydantic v2).
- **Don't** use `class Config: orm_mode = True` — use `model_config = {"from_attributes": True}`.
- **Don't** use `@validator` — use `@field_validator` (Pydantic v2).
- **Don't** return raw dicts from endpoints — always use typed response schemas.
- **Don't** hardcode secrets — all secrets must come from `.env` via `Settings`.
- **Don't** use `FloatField` for money — always use `DecimalField`.
- **Don't** call `.save()` without `update_fields` when only updating specific columns.
- **Don't** use Django REST Framework — this project uses Django Ninja exclusively.
- **Don't** use `os.path` — use `pathlib.Path`.
- **Don't** use signals for business logic — use explicit function calls.
- **Don't** skip `select_related` / `prefetch_related` on list endpoints.
- **Don't** use Gregorian dates for business logic — use `get_current_jalali()`.
