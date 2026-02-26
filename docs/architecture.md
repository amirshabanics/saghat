# Saghat — Architecture Document

> صندوق وام دوستانه تتری  
> A friendly USDT loan fund built on Django 5.2.1 + Django Ninja

---

## 1. Project Structure

```
saghat/
├── docs/
│   └── architecture.md          # this file
├── dockerfiles/
│   ├── Dockerfile.web           # Django app image
│   └── Dockerfile.worker        # (future) Celery worker image
├── saghat/                      # Django project root (core config)
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py              # shared settings
│   │   ├── dev.py               # development overrides
│   │   └── prod.py              # production overrides
│   ├── urls.py                  # root URL conf (mounts Ninja router)
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   ├── users/
│   │   ├── __init__.py
│   │   ├── models.py            # User (AbstractUser)
│   │   ├── schemas.py           # Pydantic/Ninja schemas
│   │   ├── api.py               # Ninja router endpoints
│   │   ├── admin.py
│   │   └── migrations/
│   ├── payments/
│   │   ├── __init__.py
│   │   ├── models.py            # Payment, MembershipFeePayment, LoanPayment
│   │   ├── schemas.py
│   │   ├── api.py
│   │   ├── services.py          # business logic (pay flow)
│   │   ├── bitpin.py            # Bitpin API client
│   │   ├── admin.py
│   │   └── migrations/
│   ├── loans/
│   │   ├── __init__.py
│   │   ├── models.py            # Loan, Config
│   │   ├── schemas.py
│   │   ├── api.py
│   │   ├── services.py          # loan assignment algorithm
│   │   ├── admin.py
│   │   └── migrations/
│   └── common/
│       ├── __init__.py
│       ├── auth.py              # JWT helpers / Ninja auth backend
│       ├── jalali.py            # jdatetime utilities
│       └── pagination.py        # shared pagination schema
├── manage.py
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── docker-compose.override.yml  # dev overrides
├── .env.example
├── .env                         # gitignored
├── .python-version
└── .gitignore
```

---

## 2. Dependencies (pyproject.toml)

```toml
[project]
name = "saghat"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "django>=5.2.1,<6",
    "django-ninja>=1.3",
    "psycopg[binary]>=3.2",
    "redis>=5.2",
    "django-redis>=5.4",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "python-jose[cryptography]>=3.3",   # JWT
    "passlib[bcrypt]>=1.7",
    "jdatetime>=5.0",
    "httpx>=0.28",                       # Bitpin API calls
    "python-decouple>=3.8",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-django>=4.9",
    "pytest-asyncio>=0.24",
    "factory-boy>=3.3",
    "ruff>=0.9",
    "mypy>=1.14",
    "django-stubs>=5.1",
]
```

---

## 3. Environment Variables (.env.example)

```dotenv
# Django
DJANGO_SETTINGS_MODULE=saghat.settings.prod
SECRET_KEY=change-me
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgres://saghat:saghat@db:5432/saghat

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
JWT_SECRET_KEY=change-me-jwt
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Bitpin
BITPIN_API_BASE_URL=https://api.bitpin.ir
BITPIN_API_KEY=
BITPIN_API_SECRET=
```

`pydantic-settings` loads these via a `Settings` class in `saghat/settings/base.py`.

---

## 4. Model Design

### 4.1 User (`apps/users/models.py`)

```python
class User(AbstractUser):
    balance: Decimal          # sum of all MembershipFeePayment amounts
    is_main: bool             # admin-level flag (default False)
    loan_request_amount: Decimal  # amount user wants if they win (default 0)

    # Inherited from AbstractUser: username, email, password, is_active, …
```

Constraints:

- `loan_request_amount >= 0`
- `balance >= 0` (maintained by service layer, not DB constraint)

### 4.2 Config (`apps/loans/models.py`)

Singleton pattern — only one row should exist (enforced at service layer).

```python
class Config(models.Model):
    min_membership_fee: Decimal
    max_month_for_loan_payment: int
    min_amount_for_loan_payment: Decimal
```

### 4.3 Payment (`apps/payments/models.py`)

```python
class Payment(models.Model):
    id: UUID                  # primary key, auto-generated
    user: FK(User, on_delete=PROTECT)
    amount: Decimal           # total payment amount (membership + loan repayment)
    created_at: datetime      # UTC, auto_now_add
    jalali_year: int
    jalali_month: int
    bitpin_payment_id: str    # unique, from Bitpin

    class Meta:
        unique_together = [("user", "jalali_year", "jalali_month")]
        indexes = [("jalali_year", "jalali_month")]
```

### 4.4 MembershipFeePayment (`apps/payments/models.py`)

```python
class MembershipFeePayment(models.Model):
    payment: OneToOneField(Payment, on_delete=CASCADE, related_name="membership_fee")
    amount: Decimal
```

### 4.5 LoanPayment (`apps/payments/models.py`)

```python
class LoanPayment(models.Model):
    payment: OneToOneField(Payment, on_delete=CASCADE, related_name="loan_payment")
    loan: FK(Loan, on_delete=PROTECT, related_name="payments")
    amount: Decimal
```

### 4.6 Loan (`apps/loans/models.py`)

```python
class LoanState(str, Enum):
    INITIAL = "initial"
    ACTIVE  = "active"
    NO_ONE  = "no_one"

class Loan(models.Model):
    id: UUID                  # primary key
    user: FK(User, null=True, blank=True, on_delete=SET_NULL)
    amount: Decimal
    state: CharField(choices=LoanState, default=LoanState.INITIAL)
    jalali_year: int
    jalali_month: int
    created_at: datetime      # UTC, auto_now_add
    min_amount_for_each_payment: Decimal
    log: JSONField(default=dict)

    class Meta:
        unique_together = [("jalali_year", "jalali_month")]
```

---

## 5. API Design

All endpoints are mounted under `/api/v1/` via a single Ninja `NinjaAPI` instance.

### 5.1 Auth

#### `POST /api/v1/auth/login`

**Request:**

```json
{ "username": "string", "password": "string" }
```

**Response 200:**

```json
{ "access_token": "string", "token_type": "bearer" }
```

**Response 401:**

```json
{ "detail": "Invalid credentials" }
```

---

### 5.2 Users

#### `POST /api/v1/users/create`

Auth: JWT required, `request.user.is_main == True`

**Request:**

```json
{
  "username": "string",
  "password": "string",
  "loan_request_amount": "decimal",
  "is_main": false
}
```

**Response 201:**

```json
{
  "id": "int",
  "username": "string",
  "is_main": false,
  "loan_request_amount": "decimal",
  "balance": "0"
}
```

**Response 403:** caller is not a main user.

---

### 5.3 Payments

#### `POST /api/v1/payments/pay`

Auth: JWT required (any user)

**Request:**

```json
{
  "membership_fee": "decimal",
  "loan": "decimal",
  "loan_request_amount": "decimal",
  "bitpin_payment_id": "string"
}
```

**Response 201:**

```json
{
  "payment_id": "uuid",
  "jalali_year": 1403,
  "jalali_month": 12,
  "membership_fee": "decimal",
  "loan": "decimal"
}
```

**Validation errors (422):**

- `membership_fee < config.min_membership_fee`
- `loan < active_loan.min_amount_for_each_payment` (when user has active loan)
- `bitpin_payment_id` already used
- User already paid this Jalali month
- Bitpin verification fails or amounts mismatch

---

### 5.4 Loans

#### `POST /api/v1/loans/start`

Auth: JWT required (any user)

**Response 200:**

```json
{
  "loan_id": "uuid",
  "state": "active | no_one",
  "winner_username": "string | null",
  "amount": "decimal",
  "jalali_year": 1403,
  "jalali_month": 12
}
```

**Error 400:** Not all users have paid for current month.  
**Error 409:** Loan already assigned for current month.

---

#### `GET /api/v1/loans/history`

Auth: JWT required, `is_main == True`

**Query params:**

- `jalali_year_gt: int` (optional)
- `jalali_year_lt: int` (optional)
- `jalali_month_gt: int` (optional)
- `jalali_month_lt: int` (optional)

**Response 200:**

```json
[
  {
    "loan_id": "uuid",
    "state": "active",
    "winner_username": "string | null",
    "amount": "decimal",
    "jalali_year": 1403,
    "jalali_month": 11,
    "log": { ... }
  }
]
```

---

#### `GET /api/v1/loans/my-history`

Auth: JWT required (any user)

**Response 200:** Same shape as `/history` but filtered to `request.user`.

---

## 6. Loan Assignment Algorithm

### 6.1 Pseudocode

```
function assign_loan(jalali_year, jalali_month):

    # 0. Guard: loan already exists for this month?
    if Loan.exists(jalali_year, jalali_month):
        raise ConflictError

    # 1. Guard: all active users must have paid this month
    all_users = User.objects.filter(is_active=True)
    paid_users = Payment.objects.filter(jalali_year=jalali_year, jalali_month=jalali_month)
                                 .values_list("user_id", flat=True)
    if set(all_users.values_list("id", flat=True)) != set(paid_users):
        raise NotAllPaidError

    # 2. Create Loan in INITIAL state
    loan = Loan.create(state=INITIAL, jalali_year=..., jalali_month=...)

    # 3. Compute saghat_balance = sum of all user.balance
    saghat_balance = sum(u.balance for u in all_users)

    # 4. Determine eligible users
    not_participated = []
    candidates = []

    for user in all_users:
        reason = None

        has_active_loan = Loan.objects.filter(user=user, state=ACTIVE).exists()
        if has_active_loan:
            reason = "has_active_loan"
        elif user.loan_request_amount <= 0:
            reason = "loan_request_amount_zero"
        elif not user.is_main and user.loan_request_amount > user.balance:
            reason = "insufficient_balance"
        elif user.loan_request_amount > saghat_balance:
            reason = "fund_insufficient"

        if reason:
            not_participated.append({"user_id": user.id, "reason": reason})
        else:
            candidates.append(user)

    # 5. Score each candidate
    scored = []
    for user in candidates:
        score = compute_score(user)
        scored.append({"user_id": user.id, "username": user.username, "point": str(score)})

    # 6. Handle no candidates
    if not scored:
        loan.state = NO_ONE
        loan.log = {"not_participated": not_participated, "participated": [], "selected": null, "random_pool": []}
        loan.save()
        return loan

    # 7. Find max score (infinity beats all finite scores)
    max_score = max(s["point"] for s in scored)   # compare as Decimal/inf
    top_pool = [s["user_id"] for s in scored if s["point"] == max_score]

    # 8. Random selection from top pool
    winner_id = random.choice(top_pool)
    winner = User.objects.get(id=winner_id)

    # 9. Activate loan
    loan.user = winner
    loan.amount = winner.loan_request_amount
    loan.state = ACTIVE
    loan.min_amount_for_each_payment = config.min_amount_for_loan_payment
    loan.log = {
        "not_participated": not_participated,
        "participated": scored,
        "selected": str(winner_id),
        "random_pool": [str(uid) for uid in top_pool]
    }
    loan.save()
    return loan
```

### 6.2 Score Computation

```
function compute_score(user) -> Decimal | Infinity:

    # --- Numerator ---
    prev_loan = Loan.objects.filter(user=user, state=ACTIVE).order_by("-created_at").first()
    prev_loan_amount = prev_loan.amount if prev_loan else 0

    n1 = log(prev_loan_amount)  if prev_loan_amount > 0  else 0
    n2 = log(user.balance)      if user.balance > 0      else 0

    # months user paid on time without having a loan (last month context)
    n3 = count_months_paid_without_loan(user)

    numerator = n1 * n2 * n3   # if any factor is 0, numerator = 0

    # --- Denominator ---
    last_month_payment = get_last_month_total_payment(user)   # total paid last month
    total_loan_payments_count = LoanPayment.objects.filter(payment__user=user).count()
    total_loan_amount_received = Loan.objects.filter(user=user).aggregate(Sum("amount"))["amount__sum"] or 0
    total_loans_received = Loan.objects.filter(user=user).count()
    loan_request = user.loan_request_amount

    d1 = last_month_payment
    d2 = total_loan_payments_count
    d3 = log(total_loan_amount_received) if total_loan_amount_received > 0 else 0
    d4 = total_loans_received
    d5 = log(loan_request)               if loan_request > 0              else 0

    denominator = d1 * d2 * d3 * d4 * d5

    if denominator == 0:
        return Infinity
    return Decimal(numerator) / Decimal(denominator)
```

---

## 7. Data Flow Diagrams

### 7.1 Payment Flow

```
Client
  │
  ├─ POST /api/v1/payments/pay
  │     { membership_fee, loan, loan_request_amount, bitpin_payment_id }
  │
  ▼
PaymentService.pay(user, payload)
  │
  ├─ 1. Load Config (min_membership_fee, min_amount_for_loan_payment)
  ├─ 2. Validate membership_fee >= config.min_membership_fee
  ├─ 3. Find active Loan for user (if any)
  │       └─ Validate payload.loan >= loan.min_amount_for_each_payment
  ├─ 4. Verify bitpin_payment_id via BitpinClient.get_payment(id)
  │       └─ Validate sum(membership_fee + loan) <= bitpin_payment.amount
  ├─ 5. Compute current Jalali year/month via jdatetime
  ├─ 6. Check no duplicate Payment(user, jalali_year, jalali_month)
  │
  ├─ 7. DB Transaction:
  │       a. Create Payment(user, amount=total, jalali_year, jalali_month, bitpin_payment_id)
  │       b. Create MembershipFeePayment(payment, amount=membership_fee)
  │       c. If payload.loan > 0: Create LoanPayment(payment, loan=active_loan, amount=loan)
  │       d. user.balance += membership_fee; user.loan_request_amount = payload.loan_request_amount
  │       e. user.save()
  │
  └─ 8. Return PaymentResponse
```

### 7.2 Loan Assignment Flow

```
Client
  │
  ├─ POST /api/v1/loans/start
  │
  ▼
LoanService.start_loan()
  │
  ├─ 1. Get current Jalali year/month
  ├─ 2. Check no Loan exists for this month  ──► 409 Conflict
  ├─ 3. Check all active users paid this month ──► 400 Not All Paid
  ├─ 4. Compute saghat_balance
  ├─ 5. For each user: evaluate eligibility → candidates / not_participated
  ├─ 6. For each candidate: compute_score()
  ├─ 7. If no candidates → Loan(state=NO_ONE)
  ├─ 8. Else: find max_score, build random_pool, pick winner
  ├─ 9. Loan(state=ACTIVE, user=winner, amount=winner.loan_request_amount)
  └─ 10. Return LoanResponse
```

---

## 8. Infrastructure

### 8.1 Docker Compose

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: saghat
      POSTGRES_USER: saghat
      POSTGRES_PASSWORD: saghat
    volumes:
      - postgres_/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U saghat"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_/data

  web:
    build:
      context: .
      dockerfile: dockerfiles/Dockerfile.web
      cache_from:
        - type=local,src=/tmp/.buildx-cache
      cache_to:
        - type=local,dest=/tmp/.buildx-cache-new,mode=max
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    ports:
      - "8000:8000"
    command: >
      sh -c "python manage.py migrate &&
             python manage.py runserver 0.0.0.0:8000"

volumes:
  postgres_data:
  redis_
```

### 8.2 Dockerfile.web

```dockerfile
FROM python:3.10-slim AS base
WORKDIR /app

# Install uv
RUN pip install uv

# Cache dependency layer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY . .

EXPOSE 8000
```

---

## 9. Settings Architecture

### `saghat/settings/base.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    DEBUG: bool = False
    DATABASE_URL: str
    REDIS_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BITPIN_API_BASE_URL: str
    BITPIN_API_KEY: str
    BITPIN_API_SECRET: str

    class Config:
        env_file = ".env"

settings = Settings()

# Django settings derived from pydantic Settings object
DATABASES = {"default": env.db_url("DATABASE_URL")}
CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": settings.REDIS_URL}}
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "apps.users",
    "apps.payments",
    "apps.loans",
]
AUTH_USER_MODEL = "users.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
```

---

## 10. Authentication Design

- Django Ninja's `HttpBearer` is subclassed in `apps/common/auth.py`
- On login, a JWT is issued using `python-jose` with `exp` claim
- The bearer auth class decodes the token and sets `request.user`
- `is_main` checks are done inside endpoint functions (not middleware)

```python
# apps/common/auth.py
class JWTAuth(HttpBearer):
    def authenticate(self, request, token: str) -> User | None:
        payload = decode_jwt(token)
        return User.objects.get(id=payload["sub"])
```

---

## 11. Jalali Utilities (`apps/common/jalali.py`)

```python
import jdatetime
from datetime import datetime

def get_current_jalali() -> tuple[int, int]:
    """Return (jalali_year, jalali_month) for now (Tehran time)."""
    jdt = jdatetime.datetime.now(tz=jdatetime.datetime.now().tzinfo)
    return jdt.year, jdt.month

def gregorian_to_jalali(dt: datetime) -> tuple[int, int]:
    jdt = jdatetime.datetime.fromgregorian(datetime=dt)
    return jdt.year, jdt.month
```

---

## 12. Bitpin Integration (`apps/payments/bitpin.py`)

```python
import httpx
from decimal import Decimal

class BitpinClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str): ...

    def get_payment(self, payment_id: str) -> dict:
        """Fetch payment details from Bitpin API."""
        response = httpx.get(f"{self.base_url}/payments/{payment_id}", headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def verify_amount(self, payment_id: str, expected: Decimal) -> bool:
        data = self.get_payment(payment_id)
        return Decimal(data["amount"]) >= expected
```

---

## 13. Key Design Decisions

| Decision         | Choice               | Rationale                                       |
| ---------------- | -------------------- | ----------------------------------------------- |
| API framework    | Django Ninja         | Pydantic-native, type-safe, fast                |
| Auth             | JWT (python-jose)    | Stateless, no session storage needed            |
| DB driver        | psycopg3 (binary)    | Modern async-ready PostgreSQL driver            |
| Jalali dates     | jdatetime            | Mature, well-tested Persian calendar lib        |
| HTTP client      | httpx                | Sync + async, modern replacement for requests   |
| Settings         | pydantic-settings    | Type-safe env config, IDE autocomplete          |
| UUID PKs         | Payment, Loan        | Avoids enumeration attacks on financial records |
| Loan.log         | JSONField            | Flexible audit trail without extra tables       |
| Config singleton | Single DB row        | Simple; enforced in service layer               |
| balance field    | Denormalized on User | Fast eligibility checks without aggregation     |
