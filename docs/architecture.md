# Saghat — Architecture Document

> صندوق وام دوستانه تتری  
> A friendly USDT loan fund built on Django 5.2.1 + Django Ninja

---

## 1. Project Structure

```
saghat/                          # repo root
├── docs/
│   └── architecture.md          # this file
├── saghat/                      # Django project root (core config)
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py              # shared settings (pydantic-settings)
│   │   ├── dev.py               # development overrides + verbose logging
│   │   └── prod.py              # production overrides (DEBUG=False, quieter logging)
│   ├── urls.py                  # root URL conf (mounts Ninja router)
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   ├── users/
│   │   ├── __init__.py
│   │   ├── models.py            # User (AbstractUser + balance, is_main, loan_request_amount)
│   │   ├── schemas.py           # Pydantic/Ninja schemas
│   │   ├── api.py               # Ninja router endpoints
│   │   ├── apps.py
│   │   ├── management/
│   │   │   └── commands/
│   │   │       └── setup_fund.py  # `manage.py setup_fund` command
│   │   └── migrations/
│   ├── payments/
│   │   ├── __init__.py
│   │   ├── models.py            # Config, Payment, MembershipFeePayment, LoanPayment
│   │   ├── schemas.py
│   │   ├── api.py
│   │   ├── bitpin.py            # Bitpin API client + BitpinPaymentInfo model
│   │   ├── apps.py
│   │   └── migrations/
│   ├── loans/
│   │   ├── __init__.py
│   │   ├── models.py            # Loan, LoanState
│   │   ├── schemas.py
│   │   ├── api.py
│   │   ├── algorithm.py         # scoring & loan assignment algorithm
│   │   ├── apps.py
│   │   └── migrations/
│   └── common/
│       ├── __init__.py
│       ├── auth.py              # JWT helpers / Ninja auth backends (JWTAuth, MainUserAuth)
│       └── jalali.py            # jdatetime utilities (JalaliDate NamedTuple)
├── manage.py
├── pyproject.toml               # project metadata + uv dependency groups
├── uv.lock                      # locked dependency tree
├── Dockerfile                   # single-stage image (uv + gunicorn)
├── compose.yml                  # Docker Compose (db, redis, web)
├── .env.example                 # template for .env
├── .env                         # gitignored
├── .python-version              # pinned Python version (3.12)
└── .gitignore
```

---

## 2. Dependencies (pyproject.toml)

```toml
[project]
name = "saghat"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "django>=5.2.1,<5.3",
    "django-ninja>=1.3.0",
    "psycopg[binary]>=3.2",
    "pydantic-settings>=2.7",
    "python-jose[cryptography]>=3.3",   # JWT
    "jdatetime>=5.0",
    "httpx>=0.28",                       # Bitpin API calls
    "redis>=5.2",
    "django-redis>=5.4",
    "uvicorn[standard]>=0.34",
    "gunicorn>=23.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "ruff>=0.9",
]
```

> **Note:** `passlib`, `pydantic` (standalone), `python-decouple`, `mypy`, `factory-boy`, and `pytest-asyncio` are **not** in the actual dependency list. The package manager is `uv`; use `uv sync` to install.

---

## 3. Environment Variables (.env.example)

```dotenv
SECRET_KEY=your-secret-key-here
DEBUG=True
APP_ENV=dev
ALLOWED_HOSTS=["localhost","127.0.0.1"]
DATABASE_URL=postgresql://saghat:saghat@db:5432/saghat
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=your-jwt-secret-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
BITPIN_API_BASE_URL=https://api.bitpin.ir
BITPIN_API_KEY=
STATIC_ROOT=/static_root
DJANGO_SETTINGS_MODULE=saghat.settings.dev
```

`pydantic-settings` loads these via a `Settings` class in [`saghat/settings/base.py`](saghat/settings/base.py).

> **Key differences from earlier drafts:**
>
> - `JWT_EXPIRE_MINUTES` (not `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) — default `10080` (7 days)
> - `APP_ENV` selects `dev` or `prod` environment
> - `ALLOWED_HOSTS` is a JSON array string
> - No `BITPIN_API_SECRET` field — only `BITPIN_API_KEY` (Token auth)
> - `STATIC_ROOT` is configurable (default `/static_root`)
> - `DJANGO_SETTINGS_MODULE` is set explicitly in `.env`

---

## 4. Model Design

### 4.1 User (`apps/users/models.py`)

```python
class User(AbstractUser):
    balance: Decimal          # sum of all MembershipFeePayment amounts (max_digits=20, decimal_places=8, default=0)
    is_main: bool             # admin-level flag (default False)
    loan_request_amount: Decimal  # amount user wants if they win (max_digits=20, decimal_places=8, default=0)

    # Inherited from AbstractUser: username, email, password, is_active, …

    class Meta:
        db_table = "users"

    @property
    def has_active_loan(self) -> bool: ...  # checks loans.filter(state=LoanState.ACTIVE).exists()
```

Constraints:

- `loan_request_amount >= 0`
- `balance >= 0` (maintained by service layer, not DB constraint)

### 4.2 Config (`apps/payments/models.py`)

Singleton pattern — only one row should exist. Use `Config.get_config()` (get_or_create pk=1) to retrieve it.

```python
class Config(models.Model):
    min_membership_fee: Decimal        # default=20, max_digits=20, decimal_places=8
    max_month_for_loan_payment: int    # default=24
    min_amount_for_loan_payment: Decimal  # default=20, max_digits=20, decimal_places=8

    class Meta:
        db_table = "config"

    @classmethod
    def get_config(cls) -> "Config": ...  # get_or_create(pk=1)
```

### 4.3 Payment (`apps/payments/models.py`)

```python
class Payment(models.Model):
    id: UUID                  # primary key, auto-generated (uuid4)
    user: FK(User, on_delete=PROTECT, related_name="payments")
    amount: Decimal           # total payment amount (membership + loan repayment), max_digits=20, decimal_places=8
    created_at: datetime      # UTC, auto_now_add
    jalali_year: int          # PositiveIntegerField
    jalali_month: int         # PositiveIntegerField
    bitpin_payment_id: str    # CharField(max_length=255), from Bitpin

    class Meta:
        db_table = "payments"
        unique_together = [("user", "jalali_year", "jalali_month")]
```

### 4.4 MembershipFeePayment (`apps/payments/models.py`)

```python
class MembershipFeePayment(models.Model):
    payment: OneToOneField(Payment, on_delete=CASCADE, related_name="membership_fee")
    amount: Decimal           # max_digits=20, decimal_places=8; must be >= Config.min_membership_fee

    class Meta:
        db_table = "membership_fee_payments"
```

### 4.5 LoanPayment (`apps/payments/models.py`)

```python
class LoanPayment(models.Model):
    payment: OneToOneField(Payment, on_delete=CASCADE, related_name="loan_payment")
    loan: FK("loans.Loan", on_delete=PROTECT, related_name="payments")
    amount: Decimal           # max_digits=20, decimal_places=8; must be >= Loan.min_amount_for_each_payment

    class Meta:
        db_table = "loan_payments"
```

### 4.6 Loan (`apps/loans/models.py`)

```python
class LoanState(models.TextChoices):
    INITIAL = "initial", "Initial"
    ACTIVE  = "active",  "Active"
    NO_ONE  = "no_one",  "No One"

class Loan(models.Model):
    id: UUID                           # primary key, uuid4
    user: FK(User, on_delete=PROTECT, related_name="loans", null=True, blank=True)
    amount: Decimal                    # max_digits=20, decimal_places=8, null=True, blank=True
    state: CharField(choices=LoanState, default=LoanState.INITIAL, max_length=20)
    jalali_year: int                   # PositiveIntegerField
    jalali_month: int                  # PositiveIntegerField
    created_at: datetime               # UTC, auto_now_add
    min_amount_for_each_payment: Decimal  # copied from Config at creation; null=True, blank=True
    log: JSONField(default=dict)       # audit trail (see below)

    class Meta:
        db_table = "loans"
        unique_together = [("jalali_year", "jalali_month")]

    @property
    def total_paid(self) -> Decimal: ...       # sum of all LoanPayment.amount for this loan
    @property
    def remaining_balance(self) -> Decimal: ...  # amount - total_paid
    @property
    def is_settled(self) -> bool: ...           # remaining_balance <= 0
```

`log` JSON structure:

```json
{
  "not_participated": [
    { "user_id": "...", "username": "...", "reason": "..." }
  ],
  "participated": [{ "user_id": "...", "username": "...", "point": "..." }],
  "selected": "user_id | null",
  "random_pool": ["user_id", "..."]
}
```

---

## 5. API Design

All endpoints are mounted under `/api/` via a single Ninja `NinjaAPI` instance (`title="Saghat API"`, `version="1.0.0"`, interactive docs at `/api/docs`).

Router prefixes (from [`saghat/urls.py`](saghat/urls.py)):

| Router                 | Prefix          |
| ---------------------- | --------------- |
| `apps/users/api.py`    | `/api/auth`     |
| `apps/payments/api.py` | `/api/payments` |
| `apps/loans/api.py`    | `/api/loans`    |

---

### 5.1 Auth / Users (`/api/auth`)

#### `POST /api/auth/login`

Auth: none (`auth=None`)

**Request** ([`LoginRequest`](apps/users/schemas.py:7)):

```json
{ "username": "string", "password": "string" }
```

**Response 200** ([`LoginResponse`](apps/users/schemas.py:12)):

```json
{
  "access_token": "string",
  "token_type": "bearer",
  "user_id": 1,
  "username": "string",
  "is_main": false
}
```

**Response 401:**

```json
{ "detail": "Invalid username or password" }
```

---

#### `POST /api/auth/users`

Auth: `MainUserAuth` — JWT required, `is_main == True`

**Request** ([`CreateUserRequest`](apps/users/schemas.py:20)):

```json
{
  "username": "string", // min_length=3, max_length=150; letters/digits/._- only
  "password": "string", // min_length=8
  "first_name": "", // optional, default ""
  "last_name": "", // optional, default ""
  "email": "", // optional, default ""
  "is_main": false, // optional, default false
  "loan_request_amount": "0" // optional, default 0, >= 0
}
```

**Response 201** ([`UserResponse`](apps/users/schemas.py:40)):

```json
{
  "id": 1,
  "username": "string",
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "is_main": false,
  "balance": "0",
  "loan_request_amount": "0",
  "has_active_loan": false
}
```

**Response 400:** username already exists.
**Response 403:** caller is not a main user.

---

#### `GET /api/auth/users`

Auth: `MainUserAuth` — JWT required, `is_main == True`

**Response 200:** `list[UserResponse]` — all fund members ordered by username.
**Response 403:** caller is not a main user.

---

#### `GET /api/auth/me`

Auth: `JWTAuth` — any active user

**Response 200** ([`UserResponse`](apps/users/schemas.py:40)): the authenticated user's profile.
**Response 401:** invalid or missing token.

---

#### `PATCH /api/auth/me/loan-request`

Auth: `JWTAuth` — any active user

**Request** ([`UpdateLoanRequestAmountRequest`](apps/users/schemas.py:54)):

```json
{ "loan_request_amount": "decimal" } // >= 0; set to 0 to opt out
```

**Response 200** ([`UserResponse`](apps/users/schemas.py:40)): updated user profile.
**Response 400:** validation error.
**Response 401:** invalid or missing token.

---

### 5.2 Payments (`/api/payments`)

#### `POST /api/payments/pay`

Auth: `JWTAuth` — any active user

**Request** ([`PaymentRequest`](apps/payments/schemas.py:7)):

```json
{
  "membership_fee": "decimal", // > 0; must be >= Config.min_membership_fee
  "loan": "decimal | null", // > 0 if provided; required when user has active loan, must be null otherwise
  "loan_request_amount": "decimal | null", // >= 0; updates user.loan_request_amount if provided
  "bitpin_payment_id": "string" // Bitpin transaction ID to verify
}
```

**Response 201** ([`PaymentResponse`](apps/payments/schemas.py:39)):

```json
{
  "id": "uuid",
  "user_id": 1,
  "amount": "decimal",
  "jalali_year": 1403,
  "jalali_month": 12,
  "bitpin_payment_id": "string",
  "membership_fee": { "amount": "decimal" },
  "loan_payment": { "loan_id": "uuid", "amount": "decimal" } | null
}
```

**Error 400:**

- `membership_fee < Config.min_membership_fee`
- `loan < active_loan.min_amount_for_each_payment` (when user has active loan)
- `loan` provided but user has no active loan
- `loan` omitted but user has an active loan
- Bitpin payment verification failed

**Error 409:** user already paid for the current Jalali month.

---

#### `GET /api/payments/config`

Auth: `JWTAuth` — any active user

**Response 200** ([`ConfigResponse`](apps/payments/schemas.py:56)):

```json
{
  "min_membership_fee": "decimal",
  "max_month_for_loan_payment": 24,
  "min_amount_for_loan_payment": "decimal"
}
```

---

#### `GET /api/payments/my-payments`

Auth: `JWTAuth` — any active user

**Response 200:** `list[PaymentResponse]` — all payments by the authenticated user, ordered by Jalali date descending.

---

### 5.3 Loans (`/api/loans`)

#### `POST /api/loans/start`

Auth: `JWTAuth` — any active user

Triggers loan assignment for the current Jalali month.

**Response 201** ([`StartLoanResponse`](apps/loans/schemas.py:34)):

```json
{
  "loan": {
    "id": "uuid",
    "user_id": 1 | null,
    "username": "string | null",
    "amount": "decimal | null",
    "state": "active | no_one | initial",
    "jalali_year": 1403,
    "jalali_month": 12,
    "min_amount_for_each_payment": "decimal | null",
    "total_paid": "decimal",
    "remaining_balance": "decimal",
    "log": { "not_participated": [...], "participated": [...], "selected": "...", "random_pool": [...] },
    "payments": [
      { "id": "uuid", "amount": "decimal", "jalali_year": 1403, "jalali_month": 12 }
    ]
  },
  "message": "string"
}
```

**Error 400:** not all active users have paid for the current month.
**Error 409:** loan assignment already done for the current month.

---

#### `GET /api/loans/history`

Auth: `MainUserAuth` — JWT required, `is_main == True`

**Query params** ([`LoanHistoryFilters`](apps/loans/schemas.py:43)):

| Param             | Type             | Description                       |
| ----------------- | ---------------- | --------------------------------- |
| `jalali_year_gt`  | `int` (optional) | loans with `jalali_year > value`  |
| `jalali_year_lt`  | `int` (optional) | loans with `jalali_year < value`  |
| `jalali_month_gt` | `int` (optional) | loans with `jalali_month > value` |
| `jalali_month_lt` | `int` (optional) | loans with `jalali_month < value` |

**Response 200:** `list[LoanResponse]` — all loans ordered by Jalali date descending.
**Response 403:** caller is not a main user.

---

#### `GET /api/loans/my-history`

Auth: `JWTAuth` — any active user

**Response 200:** `list[LoanResponse]` — loans belonging to the authenticated user, ordered by Jalali date descending.

---

#### `GET /api/loans/{loan_id}`

Auth: `JWTAuth` — any active user

Path param: `loan_id` (UUID string)

**Response 200** ([`LoanResponse`](apps/loans/schemas.py:17)): full loan detail.
**Response 403:** regular user attempting to view another user's loan.
**Response 404:** loan not found or invalid UUID format.

> **Access control:** `is_main` users can view any loan; regular users can only view their own loans.

---

## 6. Loan Assignment Algorithm

The algorithm lives in [`apps/loans/algorithm.py`](apps/loans/algorithm.py) and is invoked from the `POST /api/loans/start` endpoint.

### 6.1 Data Structures

```python
@dataclass
class NotParticipatedEntry:
    user_id: int
    username: str
    reason: str   # e.g. "has_active_loan", "loan_request_amount is 0 (opted out)", etc.

@dataclass
class ParticipatedEntry:
    user_id: int
    username: str
    point: str    # "unlimited", "0", or a decimal string

@dataclass
class AssignmentLog:
    not_participated: list[NotParticipatedEntry]
    participated: list[ParticipatedEntry]
    selected: Optional[int]   # user_id of winner, or None
    random_pool: list[int]    # user_ids in the random pool

@dataclass
class UserScore:
    user_id: int
    username: str
    score: Optional[Decimal]  # None means "unlimited" (infinity)
    loan_request_amount: Decimal
```

### 6.2 `run_loan_assignment(jalali_year, jalali_month)` — Main Flow

```
function run_loan_assignment(jalali_year, jalali_month):

    config = Config.get_config()
    all_users = User.objects.filter(is_active=True)

    # 1. Guard: all active users must have paid this month
    paid_user_ids = Payment.objects.filter(jalali_year, jalali_month).values_list("user_id")
    unpaid = [u for u in all_users if u.id not in paid_user_ids]
    if unpaid:
        raise ValueError("Not all users have paid for {year}/{month}. Unpaid: {names}")

    # 2. Compute saghat_balance = sum of all active user.balance
    saghat_balance = User.objects.filter(is_active=True).aggregate(Sum("balance"))

    # 3. Determine eligibility for each user (order matters)
    for user in all_users:
        if not user.is_main and user.loan_request_amount > user.balance:
            → not_participated (reason: "loan_request_amount > balance")
        elif user.has_active_loan:
            → not_participated (reason: "User has an active loan")
        elif user.loan_request_amount <= 0:
            → not_participated (reason: "loan_request_amount is 0 (opted out)")
        else:
            → eligible_users

    # 4. If no eligible users → create Loan(state=NO_ONE) and return

    # 5. Compute score for each eligible user via compute_user_score()
    #    score is None ("unlimited") or a Decimal

    # 6. Filter by fund balance: keep only users where loan_request_amount <= saghat_balance
    fundable_scores = [us for us in user_scores if us.loan_request_amount <= saghat_balance]

    # 7. If no fundable users → create Loan(state=NO_ONE, note="No user fits saghat_balance")

    # 8. Determine max-score group
    #    None (unlimited) > any Decimal
    if any score is None (unlimited):
        max_score_group = all users with score=None
    else:
        max_score_group = all users with score == max(scores)

    # 9. Random selection from max_score_group
    winner = random.choice(max_score_group)

    # 10. Create Loan(state=ACTIVE, user=winner, amount=winner.loan_request_amount,
    #                 min_amount_for_each_payment=config.min_amount_for_loan_payment)
    #     with full AssignmentLog stored in loan.log JSON field
    return loan
```

> **Note:** The loan record is created atomically inside a `transaction.atomic()` block. The conflict guard (loan already exists for this month) is enforced at the API layer before calling `run_loan_assignment`.

### 6.3 `compute_user_score(user)` — Score Computation

Returns `None` (unlimited/infinity) or a `Decimal`. The denominator is evaluated **first**; if any denominator factor is zero, `None` is returned immediately.

```
function compute_user_score(user) -> Optional[Decimal]:

    # ── Denominator factors (checked first) ──────────────────────────────────

    # D1: total amount of user's most recent Payment record
    last_payment = Payment.objects.filter(user).order_by("-jalali_year", "-jalali_month").first()
    if last_payment is None or last_payment.amount <= 0:
        return None  # unlimited

    # D2: count of all LoanPayment records for this user
    total_user_loan_payments = LoanPayment.objects.filter(payment__user=user).count()
    if total_user_loan_payments == 0:
        return None  # unlimited

    # D3: log(sum of all active loan amounts received)
    total_loan_amount = Loan.objects.filter(user, state=ACTIVE).aggregate(Sum("amount"))
    if total_loan_amount <= 0:
        return None  # unlimited
    log_total_loan_amount = log(total_loan_amount)
    if log_total_loan_amount <= 0:
        return None

    # D4: count of active loans received
    total_loan_user_get = Loan.objects.filter(user, state=ACTIVE).count()
    if total_loan_user_get == 0:
        return None  # unlimited

    # D5: log(loan_request_amount)
    if user.loan_request_amount <= 0:
        return None
    log_loan_request = log(user.loan_request_amount)
    if log_loan_request <= 0:
        return None

    denominator = D1 * D2 * D3 * D4 * D5
    if denominator <= 0:
        return None  # unlimited

    # ── Numerator factors ─────────────────────────────────────────────────────

    # N1: log(most recent active loan amount) — 0 if no prior loan or amount <= 0
    previous_loan = Loan.objects.filter(user, state=ACTIVE).order_by("-created_at").first()
    log_previous_loan = log(previous_loan.amount) if amount > 0 and log > 0 else 0

    # N2: log(user.balance) — 0 if balance <= 0 or log <= 0
    log_balance = log(user.balance) if balance > 0 and log > 0 else 0

    # N3: months user paid without having an active loan
    #     = total Payment count - distinct (jalali_year, jalali_month) months with a LoanPayment
    total_payments_count = Payment.objects.filter(user).count()
    months_with_loan_payment = LoanPayment.objects.filter(payment__user=user)
                                    .values("payment__jalali_year", "payment__jalali_month")
                                    .distinct().count()
    total_month_no_loan = max(0, total_payments_count - months_with_loan_payment)

    numerator = N1 * N2 * N3
    if numerator <= 0:
        return Decimal("0")   # finite zero score (not unlimited)

    return numerator / denominator
```

### 6.4 Score Interpretation

| Score value          | Meaning                                                         |
| -------------------- | --------------------------------------------------------------- |
| `None` ("unlimited") | User has no prior loan history — highest priority               |
| `Decimal > 0`        | Computed ratio — higher = more deserving                        |
| `Decimal("0")`       | Numerator is zero (e.g. zero balance or no months without loan) |

Users with `score = None` always beat users with any finite score. Among tied scores, one is chosen at random.

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

### 8.1 Docker Compose (`compose.yml`)

```yaml
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
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  web:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - .:/app
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    develop:
      watch:
        - action: sync
          path: .
          target: /app
          ignore: [.venv/]
        - action: rebuild
          path: ./pyproject.toml
        - action: rebuild
          path: ./Dockerfile
    command: >
      sh -c "uv run python manage.py migrate &&
             uv run python manage.py collectstatic --noinput &&
             uv run gunicorn saghat.wsgi:application --bind 0.0.0.0:8000 --workers 4"

volumes:
  postgres_data:
  redis_
```

Key points:

- Both `db` and `redis` have health checks; `web` waits for both to be **healthy** before starting.
- The `develop.watch` block enables Docker Compose Watch for live sync during development (`docker compose watch`).
- The startup command runs migrations, collects static files, then starts Gunicorn with 4 workers.

### 8.2 Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# System deps for psycopg (libpq-dev) and build tools
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user (uid/gid 999)
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

# uv environment variables
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Install dependencies (cached layer — only re-runs when pyproject.toml/uv.lock change)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy source and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT []
USER nonroot

ENV DJANGO_SETTINGS_MODULE=saghat.settings.prod
EXPOSE 8000

CMD ["uv", "run", "gunicorn", "saghat.wsgi:application", \
     "--bind", "0.0.0.0:8000", "--reload", "--workers", "4"]
```

Key points:

- Base image is `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` — ships with `uv` pre-installed.
- Uses BuildKit cache mounts (`--mount=type=cache`) for fast rebuilds.
- Runs as non-root user `nonroot` (uid/gid 999) for security.
- `UV_NO_DEV=1` excludes dev dependencies from the image.
- Production settings (`saghat.settings.prod`) are baked in via `ENV`.
- Gunicorn serves the WSGI app with 4 workers.

### 8.3 Running with Docker

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env: set SECRET_KEY, JWT_SECRET_KEY, and optionally BITPIN_API_KEY

# Build and start all services
docker compose up --build

# Or use Docker Compose Watch for live sync during development
docker compose watch

# Run management commands inside the container
docker compose exec web uv run python manage.py setup_fund
docker compose exec web uv run python manage.py createsuperuser
```

---

## 9. Settings Architecture

### `saghat/settings/base.py`

Settings are loaded via `pydantic-settings` ([docs.djangoproject.com](https://docs.djangoproject.com/en/4.2/topics/settings)) from the `.env` file. The `Settings` class uses `SettingsConfigDict(env_file=".env", extra="ignore")`.

#### `Settings` Pydantic model

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn
from typing import Optional
from enum import Enum

class AppEnv(str, Enum):
    dev = "dev"
    prod = "prod"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Django
    STATIC_ROOT: str = "/static_root"
    SECRET_KEY: str                          # required
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ["*"]

    APP_ENV: AppEnv = AppEnv.dev             # "dev" | "prod"

    # Database
    DATABASE_URL: PostgresDsn               # required; e.g. postgres://user:pass@host:5432/db

    # Redis
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str                      # required
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7   # 7 days (10080 minutes)

    # Bitpin
    BITPIN_API_BASE_URL: str = "https://api.bitpin.ir"
    BITPIN_API_KEY: Optional[str] = None    # optional; no BITPIN_API_SECRET field

settings = Settings()
```

> **Note:** The JWT expiry env var is `JWT_EXPIRE_MINUTES` (not `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). There is no `BITPIN_API_SECRET` field in the `Settings` class.

#### Django configuration derived from `settings`

```python
SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ALLOWED_HOSTS = settings.ALLOWED_HOSTS

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "apps.users.apps.UsersConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.loans.apps.LoansConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "saghat.urls"
WSGI_APPLICATION = "saghat.wsgi.application"
ASGI_APPLICATION = "saghat.asgi.application"

# Database — parsed from PostgresDsn object (not dj-database-url)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": settings.DATABASE_URL.path.lstrip("/"),
        "USER": settings.DATABASE_URL.hosts()[0]["username"],
        "PASSWORD": settings.DATABASE_URL.hosts()[0]["password"],
        "HOST": settings.DATABASE_URL.hosts()[0]["host"],
        "PORT": str(settings.DATABASE_URL.hosts()[0]["port"] or 5432),
    }
}

# Cache (django-redis)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(settings.REDIS_URL),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

AUTH_USER_MODEL = "users.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Internationalisation
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_ROOT = settings.STATIC_ROOT   # "/static_root" by default
STATIC_URL = "static/"
```

---

## 10. Authentication Design

### Overview

- Django Ninja's [`HttpBearer`](apps/common/auth.py:32) is subclassed in [`apps/common/auth.py`](apps/common/auth.py)
- On login (`POST /api/auth/login`), a JWT is issued using `python-jose` with `sub` (user ID as string) and `exp` claims
- The bearer auth classes decode the token, look up the user, and set `request.user`
- Token expiry is controlled by `JWT_EXPIRE_MINUTES` in settings (default: `60 * 24 * 7` = 7 days / 10080 minutes)

### Two Auth Classes

There are two distinct auth backends, both defined in [`apps/common/auth.py`](apps/common/auth.py):

#### [`JWTAuth`](apps/common/auth.py:32) — any active user

Used on endpoints accessible to all fund members.

```python
class JWTAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> User | None:
        user_id = decode_access_token(token)   # returns None on JWTError
        if user_id is None:
            return None
        try:
            user = User.objects.get(pk=user_id, is_active=True)
            request.user = user
            return user
        except User.DoesNotExist:
            return None
```

#### [`MainUserAuth`](apps/common/auth.py:49) — `is_main` users only

Used on admin-level endpoints (create user, list users, loan history).

```python
class MainUserAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> User | None:
        user_id = decode_access_token(token)
        if user_id is None:
            return None
        try:
            user = User.objects.get(pk=user_id, is_active=True, is_main=True)
            request.user = user
            return user
        except User.DoesNotExist:
            return None
```

### Token Lifecycle

| Step           | Detail                                                                                                                                                                                 |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Issue**      | [`create_access_token(user_id)`](apps/common/auth.py:9) — signs `{"sub": str(user_id), "exp": now + JWT_EXPIRE_MINUTES}` with `JWT_SECRET_KEY` using `JWT_ALGORITHM` (default `HS256`) |
| **Verify**     | [`decode_access_token(token)`](apps/common/auth.py:20) — decodes with `python-jose`; returns `int` user ID or `None` on any `JWTError`                                                 |
| **Expiry**     | Controlled by `JWT_EXPIRE_MINUTES` env var (default 10080 min = 7 days)                                                                                                                |
| **Revocation** | Not supported — tokens are stateless; invalidation requires changing `JWT_SECRET_KEY`                                                                                                  |

### Auth Usage per Endpoint

| Endpoint                          | Auth class                                |
| --------------------------------- | ----------------------------------------- |
| `POST /api/auth/login`            | none                                      |
| `POST /api/auth/users`            | `MainUserAuth`                            |
| `GET /api/auth/users`             | `MainUserAuth`                            |
| `GET /api/auth/me`                | `JWTAuth`                                 |
| `PATCH /api/auth/me/loan-request` | `JWTAuth`                                 |
| `POST /api/payments/pay`          | `JWTAuth`                                 |
| `GET /api/payments/config`        | `JWTAuth`                                 |
| `GET /api/payments/my-payments`   | `JWTAuth`                                 |
| `POST /api/loans/start`           | `JWTAuth`                                 |
| `GET /api/loans/history`          | `MainUserAuth`                            |
| `GET /api/loans/my-history`       | `JWTAuth`                                 |
| `GET /api/loans/{loan_id}`        | `JWTAuth` (ownership enforced in handler) |

---

## 11. Jalali Utilities (`apps/common/jalali.py`)

```python
import jdatetime
from datetime import datetime
from typing import NamedTuple

class JalaliDate(NamedTuple):
    year: int
    month: int

def get_current_jalali() -> JalaliDate:
    """Return current Jalali year and month."""
    now = jdatetime.datetime.now()
    return JalaliDate(year=now.year, month=now.month)

def gregorian_to_jalali(dt: datetime) -> JalaliDate:
    """Convert a Gregorian datetime to Jalali year/month."""
    jdt = jdatetime.datetime.fromgregorian(datetime=dt)
    return JalaliDate(year=jdt.year, month=jdt.month)
```

> **Note:** The return type is a `JalaliDate` `NamedTuple` (not a plain `tuple[int, int]`). `jdatetime.datetime.now()` uses the local system time — in production this is UTC (as set by `TIME_ZONE = "UTC"` in Django settings).

---

## 12. Bitpin Integration (`apps/payments/bitpin.py`)

[Bitpin](https://bitpin.ir) is an Iranian cryptocurrency exchange. Saghat uses it to verify that users have actually transferred the correct USDT amount before recording a payment.

### Classes

```python
class BitpinPaymentInfo(BaseModel):
    """Parsed payment info from Bitpin API response."""
    payment_id: str
    amount: Decimal
    status: str    # e.g. "completed", "pending", "failed"
    currency: str  # e.g. "USDT"

class BitpinClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Token {api_key}"
```

### API Endpoint

```
GET {BITPIN_API_BASE_URL}/v1/mch/payments/{payment_id}/
```

Authentication: `Token {BITPIN_API_KEY}` header (omitted if `BITPIN_API_KEY` is not set).

### `get_payment(payment_id)` → `Optional[BitpinPaymentInfo]`

Fetches payment details. Returns `None` on any error (HTTP error, missing fields, timeout). Uses `httpx.Client` with a 10-second timeout.

### `verify_payment_amount(payment_id, expected_amount)` → `tuple[bool, str]`

Validates that:

1. The payment exists (`get_payment` returns non-None)
2. The payment status is one of: `"completed"`, `"paid"`, `"confirmed"`, `"done"`
3. `payment.amount >= expected_amount`

Returns `(True, "")` on success, or `(False, reason_string)` on failure.

### `get_bitpin_client()` — Factory Function

```python
def get_bitpin_client() -> BitpinClient:
    from saghat.settings.base import settings as app_settings
    return BitpinClient(
        base_url=app_settings.BITPIN_API_BASE_URL,
        api_key=app_settings.BITPIN_API_KEY,
    )
```

### Dev Mode (No API Key)

When `BITPIN_API_KEY` is not set (empty or `None`), the `Authorization` header is omitted. The payment API endpoint in [`apps/payments/api.py`](apps/payments/api.py) skips Bitpin verification entirely when `BITPIN_API_KEY` is falsy, making local development possible without a real Bitpin account.

---

## 13. Management Commands

### `setup_fund` (`apps/users/management/commands/setup_fund.py`)

Sets up or updates the singleton [`Config`](apps/payments/models.py) record (pk=1) that controls fund parameters.

**Usage:**

```bash
# Default values (min_fee=20, max_months=24, min_payment=20)
uv run python manage.py setup_fund

# Custom values
uv run python manage.py setup_fund --min-fee 25 --max-months 36 --min-payment 25
```

**Arguments:**

| Argument        | Type      | Default | Description                            |
| --------------- | --------- | ------- | -------------------------------------- |
| `--min-fee`     | `Decimal` | `20`    | Minimum monthly membership fee in USDT |
| `--max-months`  | `int`     | `24`    | Maximum loan repayment months          |
| `--min-payment` | `Decimal` | `20`    | Minimum monthly loan payment in USDT   |

**Behaviour:**

- Uses `Config.objects.get_or_create(pk=1)` — safe to run multiple times.
- Prints `Created fund config: ...` or `Updated fund config: ...` on success.
- Must be run after `migrate` on a fresh database before the first payment can be accepted.

**Example output:**

```
Created fund config: min_fee=20 USDT, max_months=24, min_payment=20 USDT
```

---

## 14. Testing

### 14.1 Test Structure

Tests live alongside each app under a `tests/` sub-package:

```
conftest.py                          # shared fixtures (project root)
apps/
  users/tests/
    test_models.py                   # User model unit tests
    test_api.py                      # User API end-to-end tests
  loans/tests/
    test_models.py                   # Loan model unit tests
    test_algorithm.py                # Loan assignment algorithm unit tests
    test_api.py                      # Loan API end-to-end tests
  payments/tests/
    test_models.py                   # Payment model unit tests
    test_api.py                      # Payment API end-to-end tests
```

### 14.2 Running Tests

```bash
# Run the full test suite
uv run pytest

# Run a specific app's tests
uv run pytest apps/users/tests/
uv run pytest apps/loans/tests/
uv run pytest apps/payments/tests/

# Run a single test file
uv run pytest apps/loans/tests/test_algorithm.py

# Run a single test by name
uv run pytest apps/loans/tests/test_algorithm.py::TestComputeUserScore::test_no_prior_loans
```

pytest is configured in [`pyproject.toml`](pyproject.toml) with:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "saghat.settings.dev"
python_files = ["tests.py", "test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

### 14.3 Test Categories

| Category       | Files                                                          | Description                                                                                   |
| -------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Unit**       | `*/tests/test_models.py`, `apps/loans/tests/test_algorithm.py` | Test model properties, constraints, and the scoring algorithm in isolation                    |
| **End-to-end** | `*/tests/test_api.py`                                          | Test full HTTP request/response cycles via Django Ninja's `TestClient`; hit the real database |

### 14.4 Shared Fixtures (`conftest.py`)

Three fixtures are available to all test modules:

| Fixture        | Type     | Description                                                                                                                                           |
| -------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regular_user` | `User`   | A non-admin user (`is_main=False`, `balance=100`, `loan_request_amount=50`)                                                                           |
| `main_user`    | `User`   | An admin user (`is_main=True`, `balance=500`, `loan_request_amount=200`)                                                                              |
| `config`       | `Config` | The singleton [`Config`](apps/payments/models.py) record (`min_membership_fee=20`, `max_month_for_loan_payment=24`, `min_amount_for_loan_payment=20`) |

All fixtures depend on `db` (pytest-django's database access marker), so they automatically enable database access for any test that uses them.

### 14.5 Mocking External Services

**Bitpin** ([`apps/payments/bitpin.py`](apps/payments/bitpin.py)) is the only external HTTP dependency. In tests it is mocked using `unittest.mock.patch` so no real network calls are made:

```python
from unittest.mock import patch, MagicMock
from apps.payments.bitpin import BitpinPaymentInfo

with patch("apps.payments.api.get_bitpin_client") as mock_client:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.verify_payment_amount.return_value = (True, "")
    # ... make the API call
```

When `BITPIN_API_KEY` is not set (the default in `saghat.settings.dev`), the payment API skips Bitpin verification entirely, so many API tests can run without any mocking at all.

---

## 15. Key Design Decisions

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
