# GitHub Actions CI Workflows

This directory contains the CI/CD pipeline definitions for the Saghat project.

## Workflows

### `ci.yml` — Continuous Integration

Runs automatically on:

- Every **pull request** targeting `main` or `develop`
- Every **push** to `main`

#### Jobs

| Job    | Description                                                |
| ------ | ---------------------------------------------------------- |
| `lint` | Checks code formatting and linting                         |
| `test` | Runs the full test suite against real PostgreSQL and Redis |

---

### Job: `lint`

Runs on `ubuntu-latest` with no external services.

| Step          | Command                        |
| ------------- | ------------------------------ |
| Install uv    | `astral-sh/setup-uv@v5`        |
| Set up Python | `uv python install 3.12`       |
| Install deps  | `uv sync --frozen`             |
| Format check  | `uv run ruff format --check .` |
| Lint check    | `uv run ruff check .`          |

---

### Job: `test`

Runs on `ubuntu-latest` with PostgreSQL 16 and Redis 7 service containers.

**Services:**

| Service    | Image         | Port   |
| ---------- | ------------- | ------ |
| PostgreSQL | `postgres:16` | `5432` |
| Redis      | `redis:7`     | `6379` |

**Environment variables set for the job:**

| Variable                 | Value                                                            |
| ------------------------ | ---------------------------------------------------------------- |
| `DATABASE_URL`           | `postgresql://saghat:saghat_password@localhost:5432/saghat_test` |
| `REDIS_URL`              | `redis://localhost:6379/0`                                       |
| `SECRET_KEY`             | CI-only test secret                                              |
| `JWT_SECRET_KEY`         | CI-only test JWT secret                                          |
| `APP_ENV`                | `dev`                                                            |
| `DJANGO_SETTINGS_MODULE` | `saghat.settings.dev`                                            |
| `ALLOWED_HOSTS`          | `["localhost", "127.0.0.1"]`                                     |
| `STATIC_ROOT`            | `/tmp/static`                                                    |

| Step          | Command                           |
| ------------- | --------------------------------- |
| Install uv    | `astral-sh/setup-uv@v5`           |
| Set up Python | `uv python install 3.12`          |
| Install deps  | `uv sync --frozen`                |
| Migrate       | `uv run python manage.py migrate` |
| Test          | `uv run pytest --tb=short -v`     |

---

## Notes

- **Package manager:** [`uv`](https://github.com/astral-sh/uv) — never `pip` or `poetry`
- **Linter/formatter:** [`ruff`](https://github.com/astral-sh/ruff)
- **Test framework:** `pytest` + `pytest-django`
- **Settings module:** `saghat.settings.dev` (reads from environment variables via pydantic-settings)
- Service containers are accessed via `localhost` inside GitHub Actions runners
