# Saghat — صندوق وام دوستانه تتری

A Django REST API backend for managing a friendly USDT loan fund (صندوق وام دوستانه تتری).

## Overview

Saghat is a cooperative loan fund where members make monthly USDT membership fee payments and take turns receiving interest-free loans. Each month, after all members have paid, a scoring algorithm selects the most deserving member to receive a loan. The fund operates on transparency and fairness — members who have waited longer, contributed more, and borrowed less are prioritised.

## Tech Stack

- **Python 3.12+**
- **Django 5.2.1** — web framework
- **Django Ninja** — fast REST API with automatic OpenAPI docs
- **PostgreSQL 17** — primary database (via psycopg3)
- **Redis 7** — caching layer (via django-redis)
- **JWT Authentication** — stateless auth via `python-jose`
- **Bitpin** — payment verification API
- **Jalali (Persian) calendar** — month tracking via `jdatetime`
- **pydantic-settings** — environment-based configuration

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OR: Python 3.12+, PostgreSQL 17, Redis 7

### With Docker

```bash
cp .env.example .env
# Edit .env with your values
docker compose up --build
```

### Local Development

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your SECRET_KEY, DATABASE_URL, JWT_SECRET_KEY, etc.

# Run migrations
uv run python manage.py migrate

# Set up initial fund configuration
uv run python manage.py setup_fund

# Create superuser (main user — can manage members and view all loans)
uv run python manage.py createsuperuser

# Run development server
uv run python manage.py runserver
```

## API Documentation

Once running, visit: **http://localhost:8000/api/docs**

### Endpoints

#### Authentication (`/api/auth/`)

| Method | Path                        | Auth      | Description                |
| ------ | --------------------------- | --------- | -------------------------- |
| POST   | `/api/auth/login`           | None      | Login and get JWT token    |
| POST   | `/api/auth/users`           | Main user | Create a new fund member   |
| GET    | `/api/auth/me`              | JWT       | Get current user profile   |
| PATCH  | `/api/auth/me/loan-request` | JWT       | Update loan request amount |
| GET    | `/api/auth/users`           | Main user | List all members           |

#### Payments (`/api/payments/`)

| Method | Path                        | Auth | Description            |
| ------ | --------------------------- | ---- | ---------------------- |
| POST   | `/api/payments/pay`         | JWT  | Submit monthly payment |
| GET    | `/api/payments/config`      | JWT  | Get fund configuration |
| GET    | `/api/payments/my-payments` | JWT  | List my payments       |

#### Loans (`/api/loans/`)

| Method | Path                    | Auth      | Description                             |
| ------ | ----------------------- | --------- | --------------------------------------- |
| POST   | `/api/loans/start`      | JWT       | Start loan assignment for current month |
| GET    | `/api/loans/history`    | Main user | All loan history with filters           |
| GET    | `/api/loans/my-history` | JWT       | My loan history                         |
| GET    | `/api/loans/{loan_id}`  | JWT       | Get loan details                        |

## Environment Variables

See [`.env.example`](.env.example) for all required variables.

| Variable                 | Required | Default                    | Description                                                       |
| ------------------------ | -------- | -------------------------- | ----------------------------------------------------------------- |
| `SECRET_KEY`             | ✅       | —                          | Django secret key                                                 |
| `DEBUG`                  | ❌       | `False`                    | Enable debug mode                                                 |
| `APP_ENV`                | ❌       | `dev`                      | Environment selector: `dev` or `prod`                             |
| `ALLOWED_HOSTS`          | ❌       | `["*"]`                    | Allowed host list (JSON array string)                             |
| `DATABASE_URL`           | ✅       | —                          | PostgreSQL connection URL (`postgresql://user:pass@host:port/db`) |
| `REDIS_URL`              | ❌       | `redis://localhost:6379/0` | Redis connection URL                                              |
| `JWT_SECRET_KEY`         | ✅       | —                          | JWT signing secret                                                |
| `JWT_ALGORITHM`          | ❌       | `HS256`                    | JWT algorithm                                                     |
| `JWT_EXPIRE_MINUTES`     | ❌       | `10080` (7 days)           | JWT token expiry in minutes                                       |
| `BITPIN_API_BASE_URL`    | ❌       | `https://api.bitpin.ir`    | Bitpin API base URL                                               |
| `BITPIN_API_KEY`         | ❌       | `None`                     | Bitpin API key (omit to skip verification in dev)                 |
| `STATIC_ROOT`            | ❌       | `/static_root`             | Directory for collected static files                              |
| `DJANGO_SETTINGS_MODULE` | ❌       | `saghat.settings.dev`      | Settings module to use (`dev` or `prod`)                          |

## Business Logic

### Monthly Payment Flow

1. User submits `POST /api/payments/pay` with `membership_fee`, optional `loan` repayment, optional `loan_request_amount`, and `bitpin_payment_id`
2. System verifies the total amount with the Bitpin API (skipped if `BITPIN_API_KEY` is not set)
3. User's `balance` increases by `membership_fee`
4. One payment per user per Jalali month is enforced

### Loan Assignment

1. Any authenticated user triggers `POST /api/loans/start`
2. All active users must have paid for the current Jalali month
3. Eligible users: no active loan, `loan_request_amount > 0`, `loan_request_amount <= user.balance`
4. Scoring algorithm selects the winner (higher score = more deserving)
5. Random selection among tied users
6. Fund balance check: `loan_request_amount <= sum(all user balances)`
7. A `Loan` record is created with state `active` (winner found) or `no_one` (no eligible user)

### Scoring Algorithm

```
Score = Numerator / Denominator
```

If **Denominator = 0**, score is **unlimited** (highest priority).

**Numerator** (higher = more deserving):

- `log(previous_loan_amount)` — had a larger previous loan
- `log(balance)` — has contributed more to the fund
- `months_without_loan` — has been waiting longer without a loan

**Denominator** (higher = less priority):

- `last_payment_amount` — paid more in their most recent month
- `loan_payment_count` — has made more loan repayments
- `log(total_loan_amount_received)` — has received more in total loans
- `total_loans_received` — has received more loans overall
- `log(loan_request_amount)` — is requesting a larger loan

Users with no prior loan history receive an **unlimited** score (highest priority), ensuring new members are eventually served.

## Project Structure

```
saghat/                  # Django project config
  settings/
    base.py              # Core settings (pydantic-settings based)
    dev.py               # Development overrides
    prod.py              # Production overrides
  urls.py                # Root URL configuration
  wsgi.py / asgi.py      # WSGI/ASGI entry points

apps/
  common/                # Shared utilities
    auth.py              # JWT auth classes (JWTAuth, MainUserAuth)
    jalali.py            # Jalali calendar helpers
  users/                 # User management
    models.py            # Custom User model (AbstractUser + balance, is_main, loan_request_amount)
    api.py               # Auth & user endpoints
    schemas.py           # Request/response schemas
    management/
      commands/
        setup_fund.py    # `manage.py setup_fund` command
  payments/              # Payment processing
    models.py            # Config, Payment, MembershipFeePayment, LoanPayment
    api.py               # Payment endpoints
    schemas.py           # Request/response schemas
    bitpin.py            # Bitpin API client
  loans/                 # Loan assignment
    models.py            # Loan model with state machine
    api.py               # Loan endpoints
    algorithm.py         # Scoring & assignment algorithm
    schemas.py           # Request/response schemas

docs/
  architecture.md        # Detailed architecture documentation
```

## Management Commands

### `setup_fund`

Set up or update the fund configuration:

```bash
uv run python manage.py setup_fund
uv run python manage.py setup_fund --min-fee 25 --max-months 36 --min-payment 25
```

Options:

- `--min-fee DECIMAL` — Minimum monthly membership fee in USDT (default: `20`)
- `--max-months INT` — Maximum loan repayment months (default: `24`)
- `--min-payment DECIMAL` — Minimum monthly loan payment in USDT (default: `20`)

## Testing

Run the full test suite with:

```bash
uv run pytest
```

Run a specific app's tests:

```bash
uv run pytest apps/users/tests/
uv run pytest apps/loans/tests/
uv run pytest apps/payments/tests/
```

### Test Categories

| Category       | Location                                                       | Description                                                      |
| -------------- | -------------------------------------------------------------- | ---------------------------------------------------------------- |
| **Unit**       | `*/tests/test_models.py`, `apps/loans/tests/test_algorithm.py` | Model properties, constraints, and the scoring algorithm         |
| **End-to-end** | `*/tests/test_api.py`                                          | Full HTTP request/response cycles via Django Ninja's test client |

Shared fixtures (`regular_user`, `main_user`, `config`) are defined in [`conftest.py`](conftest.py) at the project root. Bitpin is mocked in API tests so no real network calls are made.

## Development Notes

- **Bitpin verification** is automatically skipped when `BITPIN_API_KEY` is not set in `.env`, making local development easier.
- The settings module uses [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for type-safe environment variable loading.
- Custom management commands follow the [Django management command pattern](https://docs.djangoproject.com/en/4.1/howto/custom-management-commands/) — placed under `apps/users/management/commands/`.
- All API endpoints return structured error responses with a `detail` field.
- The `is_main` flag on `User` grants admin-level access to protected endpoints (user creation, full loan history).
