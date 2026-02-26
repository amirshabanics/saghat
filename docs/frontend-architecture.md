# Frontend Architecture — Part 1

## Section 1: New Directory Structure

### Migration Overview

The repository moves from a flat root layout to a `src/`-namespaced monorepo. All Django code lives under `src/backend/`; the new React application lives under `src/frontend/`. Compose files are consolidated under `docker/`; deployment artefacts stay in `deploy/`.

### Target Directory Tree

```
saghat/                                  ← repo root
├── src/
│   ├── backend/                         ← Django project (moved from root)
│   │   ├── saghat/                      ← Django settings package (unchanged internally)
│   │   │   ├── __init__.py
│   │   │   ├── asgi.py
│   │   │   ├── urls.py
│   │   │   ├── wsgi.py
│   │   │   └── settings/
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── dev.py
│   │   │       └── prod.py
│   │   ├── apps/                        ← Django apps (unchanged internally)
│   │   │   ├── common/
│   │   │   ├── loans/
│   │   │   ├── payments/
│   │   │   └── users/
│   │   ├── manage.py
│   │   ├── conftest.py
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   ├── .python-version
│   │   ├── Dockerfile                   ← was root/Dockerfile
│   │   └── .env.example                 ← was root/.env.example
│   │
│   └── frontend/                        ← New React application
│       ├── public/
│       ├── src/
│       │   ├── assets/
│       │   ├── components/
│       │   │   └── ui/                  ← shadcn/ui generated components
│       │   ├── features/                ← feature-sliced modules
│       │   ├── hooks/
│       │   ├── lib/
│       │   │   └── api.ts               ← typed API client (fetch/axios)
│       │   ├── pages/
│       │   ├── router/
│       │   │   └── index.tsx            ← React Router configuration
│       │   ├── store/
│       │   │   └── index.ts             ← Zustand stores
│       │   ├── types/
│       │   ├── App.tsx
│       │   └── main.tsx
│       ├── .env.example                 ← frontend env vars (VITE_* prefix)
│       ├── components.json              ← shadcn/ui config
│       ├── index.html
│       ├── package.json
│       ├── tailwind.config.ts
│       ├── tsconfig.json
│       ├── tsconfig.app.json
│       ├── tsconfig.node.json
│       ├── vite.config.ts
│       └── Dockerfile                   ← multi-stage: build → nginx/caddy
│
├── docker/                              ← all Compose files (moved/created here)
│   ├── compose.yml                      ← dev orchestration (includes backend + frontend)
│   ├── compose.backend.yml              ← backend services: db, redis, web
│   ├── compose.frontend.yml             ← frontend service: frontend dev server
│   └── compose.prod.yml                 ← production overrides + Caddy
│
├── deploy/                              ← server provisioning (unchanged)
│   ├── Caddyfile
│   ├── setup-server.sh
│   └── README.md
│
├── docs/
│   ├── architecture.md
│   ├── frontend-architecture.md         ← this file
│   ├── AGENTS.md
│   └── SKILLS.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml                       ← backend CI (updated paths)
│       └── ci-frontend.yml              ← frontend CI (lint, type-check, build)
│
├── .gitignore
├── .dockerignore
└── README.md
```

### Key Structural Decisions

| Concern               | Decision                                                                                         |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Backend isolation     | `src/backend/` is a self-contained Python project; `pyproject.toml` and `uv.lock` stay inside it |
| Frontend isolation    | `src/frontend/` is a self-contained Node project; `package.json` and lockfile stay inside it     |
| Compose consolidation | All compose files move to `docker/`; the root no longer contains any compose file                |
| Deploy artefacts      | `deploy/` stays at root — it contains server-side scripts, not container definitions             |
| `conftest.py`         | Moves to `src/backend/conftest.py` alongside `manage.py`                                         |

---

## Section 2: Docker & Environment Variable Strategy

### 2.1 Environment Files

Two env files live under `docker/`:

**`docker/.env.backend`** — injected into all backend containers (`db`, `redis`, `web`)

```dotenv
# Django
SECRET_KEY=
DEBUG=False
APP_ENV=prod
ALLOWED_HOSTS=["api.example.com"]
DJANGO_SETTINGS_MODULE=saghat.settings.prod
STATIC_ROOT=/static_root

# Database
DATABASE_URL=postgresql://saghat:saghat@db:5432/saghat

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

# Bitpin
BITPIN_API_BASE_URL=https://api.bitpin.ir
BITPIN_API_KEY=

# Postgres container bootstrap (used by the db service image directly)
POSTGRES_DB=saghat
POSTGRES_USER=saghat
POSTGRES_PASSWORD=saghat
```

**`docker/.env.frontend`** — injected into the frontend container only

```dotenv
# All Vite public env vars must be prefixed VITE_
VITE_API_BASE_URL=https://api.example.com
VITE_APP_ENV=production
```

> **Rule:** Backend secrets (keys, DB passwords) never appear in `.env.frontend`. Frontend vars are all `VITE_`-prefixed and are baked into the static bundle at build time — they must never contain secrets.

### 2.2 Compose File Responsibilities

| File                          | Services             | Purpose                                    |
| ----------------------------- | -------------------- | ------------------------------------------ |
| `docker/compose.backend.yml`  | `db`, `redis`, `web` | Backend stack definition                   |
| `docker/compose.frontend.yml` | `frontend`           | Frontend dev server                        |
| `docker/compose.yml`          | _(merges both)_      | Local dev: one command starts everything   |
| `docker/compose.prod.yml`     | overrides + `caddy`  | Production: removes dev mounts, adds Caddy |

### 2.3 Individual Compose File Structures

**`docker/compose.backend.yml`**

```yaml
services:
  db:
    image: postgres:17-alpine
    env_file:
      - .env.backend # provides POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    volumes:
      - postgres_data:/var/lib/postgresql/data
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
      context: ../src/backend
      dockerfile: Dockerfile
    env_file:
      - .env.backend # provides all Django settings as env vars
    ports:
      - "8000:8000"
    volumes:
      - ../src/backend:/app
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    develop:
      watch:
        - action: sync
          path: ../src/backend
          target: /app
          ignore:
            - .venv/
        - action: rebuild
          path: ../src/backend/pyproject.toml
        - action: rebuild
          path: ../src/backend/Dockerfile

volumes:
  postgres_data:
  redis_data:
```

**`docker/compose.frontend.yml`**

```yaml
services:
  frontend:
    build:
      context: ../src/frontend
      dockerfile: Dockerfile
      target: dev # multi-stage: dev stage runs vite dev server
    env_file:
      - .env.frontend
    ports:
      - "5173:5173"
    volumes:
      - ../src/frontend:/app
      - /app/node_modules # anonymous volume prevents host override of node_modules
    develop:
      watch:
        - action: sync
          path: ../src/frontend/src
          target: /app/src
        - action: rebuild
          path: ../src/frontend/package.json
```

**`docker/compose.yml`** — merges both stacks for local development

Per the [Docker Compose `include` spec](https://docs.docker.com/compose/multiple-compose-files/extends/) and the [base + environment override pattern](https://docker.recipes/docs/compose-overrides), the top-level dev file uses `include` to pull in both stacks:

```yaml
# docker/compose.yml — local development
# Run: docker compose -f docker/compose.yml up

include:
  - compose.backend.yml
  - compose.frontend.yml
```

This keeps each stack independently runnable (`docker compose -f docker/compose.backend.yml up`) while allowing a single command to start everything.

**`docker/compose.prod.yml`** — production overrides

Per [Docker's production guidance](https://docs.docker.com/compose/how-tos/production), this file is applied on top of `compose.backend.yml`:

```yaml
# Usage:
#   docker compose -f docker/compose.backend.yml -f docker/compose.prod.yml up -d --build

services:
  web:
    volumes: [] # no source bind-mount in production
    ports: [] # Caddy handles external traffic
    restart: unless-stopped

  db:
    restart: unless-stopped

  redis:
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp" # HTTP/3 / QUIC
    volumes:
      - ../deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_/data
      - caddy_config:/config
      - caddy_logs:/var/log/caddy
    depends_on:
      - web

volumes:
  caddy_data:
  caddy_config:
  caddy_logs:
```

### 2.4 How `compose.yml` Includes Both Stacks

```
docker compose -f docker/compose.yml up
        │
        ├── include: compose.backend.yml  →  db + redis + web  (env_file: .env.backend)
        └── include: compose.frontend.yml →  frontend           (env_file: .env.frontend)
```

Services from both files share the same default Docker network, so `frontend` can reach `web` at `http://web:8000` for SSR or health checks if needed.

### 2.5 pydantic-settings Update

Currently [`saghat/settings/base.py:13`](../src/backend/saghat/settings/base.py:13) reads:

```python
model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```

**Change to:**

```python
model_config = SettingsConfigDict(extra="ignore")
```

**Rationale:**

- Docker injects all variables from `docker/.env.backend` directly into the container's environment via the `env_file:` directive in the compose file. pydantic-settings reads from `os.environ` by default — no `env_file` argument is needed.
- Removing `env_file=".env"` eliminates the implicit dependency on a `.env` file being present at the working directory, which is fragile in containerised environments and causes silent failures when the file is missing.
- Local development without Docker can still use a `.env` file by setting `ENV_FILE` or by exporting variables in the shell — but the settings class itself remains environment-agnostic.
- CI already injects all required variables as GitHub Actions `env:` block entries (see [`.github/workflows/ci.yml:65`](../.github/workflows/ci.yml:65)), confirming the pattern works without file-based loading.

---

## Section 3: Frontend Architecture

### 3.1 Route Structure

All routes live in [`src/frontend/src/router/index.tsx`](../src/frontend/src/router/index.tsx).

| Path         | Component               | Protected | Requires `is_main` |
| ------------ | ----------------------- | --------- | ------------------ |
| `/login`     | `LoginPage`             | No        | No                 |
| `/dashboard` | `DashboardPage`         | Yes       | No                 |
| `/pay`       | `PaymentPage`           | Yes       | No                 |
| `/admin`     | `AdminDashboard`        | Yes       | Yes                |
| `/`          | redirect → `/dashboard` | Yes       | No                 |

**Protection mechanism:**

- `<ProtectedRoute>` — wraps any route that requires authentication; redirects to `/login` if no token is present in `localStorage`.
- `<AdminRoute>` — extends `<ProtectedRoute>`; additionally checks `authStore.user.is_main`; redirects to `/dashboard` if false.

```
<BrowserRouter>
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute />}>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/pay" element={<PaymentPage />} />
        <Route element={<AdminRoute />}>
          <Route path="/admin" element={<AdminDashboard />} />
        </Route>
      </Route>
    </Route>
  </Routes>
</BrowserRouter>
```

---

### 3.2 Zustand Store Design

Stores live in [`src/frontend/src/store/`](../src/frontend/src/store/).

#### `authStore` — [`src/frontend/src/store/authStore.ts`](../src/frontend/src/store/authStore.ts)

```ts
interface AuthState {
  token: string | null; // JWT access token (persisted to localStorage)
  user: UserMe | null; // result of GET /api/auth/me
  isLoading: boolean;

  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
}
```

- On app mount, if `localStorage` contains a token, `fetchMe()` is called to rehydrate `user`.
- `login()` calls `POST /api/auth/login`, stores the token, then calls `fetchMe()`.
- `logout()` clears token from state and `localStorage`, resets `user` to `null`.

#### `configStore` — [`src/frontend/src/store/configStore.ts`](../src/frontend/src/store/configStore.ts)

```ts
interface ConfigState {
  config: PaymentsConfig | null; // result of GET /api/payments/config
  isLoading: boolean;

  fetchConfig: () => Promise<void>;
}

interface PaymentsConfig {
  min_membership_fee: number;
  max_month_for_loan_payment: number;
  min_amount_for_loan_payment: number;
}
```

- `fetchConfig()` is called once after successful login (or on `AppLayout` mount) and the result is cached for the session lifetime.
- Config values are displayed in the `<Header>` and used for form validation on the Payment page.

---

### 3.3 API Client Design

The API client lives in [`src/frontend/src/lib/api.ts`](../src/frontend/src/lib/api.ts).

**Base URL** is read from the Vite env var `import.meta.env.VITE_API_BASE_URL` (set in [`src/frontend/.env.example`](../src/frontend/.env.example)).

**Auth header injection** — a thin wrapper around `fetch` reads the token from `localStorage` and attaches `Authorization: Bearer <token>` to every request that requires authentication.

```ts
// src/lib/api.ts (structure)

const BASE = import.meta.env.VITE_API_BASE_URL;

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...init,
  });
  if (!res.ok) throw await res.json();
  return res.json() as Promise<T>;
}

// Typed endpoint functions
export const api = {
  // Auth
  login: (body: LoginRequest) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  me: () => request<UserMe>("/api/auth/me"),
  users: () => request<UserMe[]>("/api/auth/users"),

  // Config
  paymentsConfig: () => request<PaymentsConfig>("/api/payments/config"),

  // Payments
  myPayments: () => request<Payment[]>("/api/payments/my-payments"),
  pay: (body: PayRequest) =>
    request<Payment>("/api/payments/pay", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Loans
  myLoanHistory: () => request<Loan[]>("/api/loans/my-history"),
  allLoanHistory: () => request<Loan[]>("/api/loans/history"),
  startLoan: () => request<LoanResult>("/api/loans/start", { method: "POST" }),
  loanDetail: (id: number) => request<Loan>(`/api/loans/${id}`),
};
```

All request/response types are defined in [`src/frontend/src/types/`](../src/frontend/src/types/) and mirror the backend schemas exactly.

---

### 3.4 Component Tree

```
App.tsx
└── BrowserRouter
    └── Routes
        ├── /login → LoginPage
        │   └── LoginForm (shadcn Card + Input + Button)
        │
        └── ProtectedRoute (checks token)
            └── AppLayout
                ├── Header                          ← always visible when logged in
                │   ├── ConfigBadges                ← min fee / max months / min payment
                │   └── UserMenu                    ← username + logout button
                └── <Outlet />
                    ├── /dashboard → DashboardPage
                    │   ├── PaymentsList            ← GET /api/payments/my-payments
                    │   └── LoansList               ← GET /api/loans/my-history
                    │
                    ├── /pay → PaymentPage
                    │   ├── MembershipFeeForm       ← POST /api/payments/pay (type: membership)
                    │   ├── LoanRepaymentForm       ← POST /api/payments/pay (type: loan)
                    │   └── LoanAssignmentSection   ← POST /api/loans/start + result display
                    │
                    └── AdminRoute (checks is_main)
                        └── /admin → AdminDashboard
                            ├── AllPaymentsTable    ← GET /api/payments/my-payments (all users)
                            └── AllLoansTable       ← GET /api/loans/history
```

**Shared / UI components** (in [`src/frontend/src/components/`](../src/frontend/src/components/)):

| Component        | Purpose                                               |
| ---------------- | ----------------------------------------------------- |
| `ProtectedRoute` | Redirects unauthenticated users to `/login`           |
| `AdminRoute`     | Redirects non-admin users to `/dashboard`             |
| `AppLayout`      | Wraps `<Header>` + `<Outlet>` for authenticated pages |
| `Header`         | Top nav: config badges + user menu                    |
| `ConfigBadges`   | Displays the three config values from `configStore`   |
| `PaymentsList`   | Renders a table of `Payment` objects                  |
| `LoansList`      | Renders a table of `Loan` objects                     |
| `LoadingSpinner` | Reusable loading indicator                            |
| `ErrorAlert`     | Reusable error display (shadcn Alert)                 |

---

### 3.5 Auth Flow

```
User visits /dashboard
        │
        ▼
ProtectedRoute checks localStorage["access_token"]
        │
   ┌────┴────┐
   │ missing │ ──→ <Navigate to="/login" />
   └────┬────┘
        │ present
        ▼
authStore.fetchMe() called (if user is null)
        │
   ┌────┴──────────┐
   │ 401 returned  │ ──→ authStore.logout() → <Navigate to="/login" />
   └────┬──────────┘
        │ 200 returned
        ▼
user hydrated in authStore → render page
```

**Login sequence:**

1. User submits [`LoginForm`](../src/frontend/src/pages/LoginPage.tsx) with `username` + `password`.
2. `authStore.login()` calls `api.login()` → `POST /api/auth/login`.
3. On success: `access_token` is written to `localStorage["access_token"]` and to `authStore.token`.
4. `authStore.fetchMe()` is called → `GET /api/auth/me` → `authStore.user` is populated.
5. `configStore.fetchConfig()` is called → `GET /api/payments/config` → `configStore.config` is populated.
6. Router navigates to `/dashboard`.

**Logout sequence:**

1. User clicks logout in `<UserMenu>`.
2. `authStore.logout()` removes `localStorage["access_token"]`, sets `token = null`, `user = null`.
3. Router navigates to `/login`.

**Token storage:** `localStorage` only — no cookies, no `sessionStorage`. The token key is `"access_token"`. The token is never sent to any origin other than `VITE_API_BASE_URL`.

**Admin guard:** After `fetchMe()` resolves, `<AdminRoute>` reads `authStore.user.is_main`. If `false`, it renders `<Navigate to="/dashboard" replace />` before the admin page mounts.

---

## Section 4: Caddy Configuration

The existing [`deploy/Caddyfile`](../deploy/Caddyfile) proxies all traffic to Django. It must be updated to also serve the React SPA static bundle and handle SPA client-side routing fallback.

### 4.1 Routing Logic

```
Incoming request
        │
        ├── /api/*          → reverse_proxy web:8000  (Django)
        ├── /static/*       → file_server from /static_root/  (Django collected statics)
        ├── /_health        → respond "OK" 200
        ├── /               → file_server from /srv/frontend/
        │       └── file not found → serve /srv/frontend/index.html  (SPA fallback)
        └── (everything else) → same SPA fallback
```

### 4.2 Dev Variant (HTTP only, no domain)

Used when the server has no domain name — identical to the current production setup but now also serves the frontend bundle.

```caddyfile
# deploy/Caddyfile  (dev / IP-only variant)
# Usage: caddy run --config /etc/caddy/Caddyfile

:80 {
    # ------------------------------------------------------------------
    # Health check — returns 200 without hitting any upstream
    # ------------------------------------------------------------------
    handle /_health {
        respond "OK" 200
    }

    # ------------------------------------------------------------------
    # Django API — proxy /api/* to Gunicorn
    # ------------------------------------------------------------------
    handle /api/* {
        reverse_proxy web:8000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            header_up Host {host}
        }
    }

    # ------------------------------------------------------------------
    # Django collected static files
    # ------------------------------------------------------------------
    handle /static/* {
        root * /static_root
        file_server
    }

    # ------------------------------------------------------------------
    # React SPA — serve built assets; fall back to index.html for
    # any path that does not match a real file (client-side routing)
    # ------------------------------------------------------------------
    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server
    }

    # ------------------------------------------------------------------
    # Security & logging
    # ------------------------------------------------------------------
    header {
        -Server
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 100mb
            roll_keep 5
            roll_keep_for 720h
        }
        format json
        level INFO
    }
}
```

### 4.3 Prod Variant (HTTPS with automatic TLS via domain)

Caddy obtains and renews a Let's Encrypt certificate automatically when a bare domain name is used as the site address. No extra TLS configuration is required.

```caddyfile
# deploy/Caddyfile  (prod / domain + auto-TLS variant)
# Replace example.com with the real domain.

example.com {
    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    handle /_health {
        respond "OK" 200
    }

    # ------------------------------------------------------------------
    # Django API
    # ------------------------------------------------------------------
    handle /api/* {
        reverse_proxy web:8000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            header_up Host {host}
        }
    }

    # ------------------------------------------------------------------
    # Django collected static files
    # ------------------------------------------------------------------
    handle /static/* {
        root * /static_root
        file_server
    }

    # ------------------------------------------------------------------
    # React SPA with SPA fallback
    # ------------------------------------------------------------------
    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server
    }

    # ------------------------------------------------------------------
    # Security & logging
    # ------------------------------------------------------------------
    header {
        -Server
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 100mb
            roll_keep 5
            roll_keep_for 720h
        }
        format json
        level INFO
    }
}
```

**Key differences between variants:**

| Concern      | Dev (`:80`)                     | Prod (`example.com`)                         |
| ------------ | ------------------------------- | -------------------------------------------- |
| TLS          | None — plain HTTP               | Automatic via ACME / Let's Encrypt           |
| HSTS header  | Omitted                         | Added with `preload`                         |
| Site address | `:80` (all interfaces, port 80) | Bare domain — Caddy binds 80 + 443 + 443/udp |
| HTTP/3       | Not applicable                  | Enabled automatically by Caddy on 443/udp    |

### 4.4 Compose Volume Wiring

The frontend build output must be mounted into the Caddy container. In [`docker/compose.prod.yml`](../docker/compose.prod.yml) the `caddy` service already mounts `../deploy/Caddyfile`. Add the frontend dist volume:

```yaml
caddy:
  image: caddy:2-alpine
  volumes:
    - ../deploy/Caddyfile:/etc/caddy/Caddyfile:ro
    - ../src/frontend/dist:/srv/frontend:ro # ← Vite build output
    - static_root:/static_root:ro # ← Django collectstatic output
    - caddy_data:/data
    - caddy_config:/config
    - caddy_logs:/var/log/caddy
```

`static_root` is a named volume populated by `docker compose run web python manage.py collectstatic --noinput` before the stack starts.

---

## Section 5: CI/CD Pipeline

The existing [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) has two jobs (`lint` and `test`) that run against the backend at the repo root. After the monorepo migration both jobs must be scoped to `src/backend/**` and two new jobs are added.

### 5.1 Job Overview

```
on: push / pull_request
        │
        ├── paths: src/backend/**  →  backend  (lint + test)
        ├── paths: src/frontend/** →  frontend (lint + type-check + build)
        └── needs: [backend, frontend]  →  docker-build (build both Dockerfiles)
```

Per [docs.github.com](https://docs.github.com/actions/reference/workflow-syntax-for-github-actions), `on.<event>.paths` filters mean a job's parent workflow only runs when at least one matching file changes. Because all three jobs live in one workflow file, the `docker-build` job uses `needs:` to wait for both upstream jobs — but those upstream jobs only run when their respective paths are touched. GitHub skips a job whose `needs` dependency was skipped, so `docker-build` only runs when at least one of the two upstream jobs actually ran and passed.

Per [docs.astral.sh](https://docs.astral.sh/uv/guides/integration/github/), the recommended pattern for uv in GitHub Actions is `astral-sh/setup-uv@v5` (already used in the existing workflow).

### 5.2 Updated `ci.yml`

```yaml
name: CI

on:
  pull_request:
    branches:
      - main
      - develop
  push:
    branches:
      - main

jobs:
  # ──────────────────────────────────────────────────────────────────
  # Backend: lint + test (runs only when backend files change)
  # ──────────────────────────────────────────────────────────────────
  backend-lint:
    name: Backend — Lint & Format
    runs-on: ubuntu-latest
    if: >
      github.event_name == 'push' ||
      contains(toJson(github.event.pull_request.changed_files), 'src/backend/')
    defaults:
      run:
        working-directory: src/backend

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Set up Python
        run: uv python install

      - name: Install dependencies
        run: uv sync --frozen

      - name: Check formatting
        run: uv run ruff format --check .

      - name: Lint
        run: uv run ruff check .

  backend-test:
    name: Backend — Tests
    runs-on: ubuntu-latest
    if: >
      github.event_name == 'push' ||
      contains(toJson(github.event.pull_request.changed_files), 'src/backend/')
    defaults:
      run:
        working-directory: src/backend

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: saghat_test
          POSTGRES_USER: saghat
          POSTGRES_PASSWORD: saghat_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U saghat -d saghat_test"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql://saghat:saghat_password@localhost:5432/saghat_test
      REDIS_URL: redis://localhost:6379/0
      SECRET_KEY: test-secret-key-for-ci-only-not-production
      JWT_SECRET_KEY: test-jwt-secret-key-for-ci-only-not-production
      APP_ENV: dev
      DJANGO_SETTINGS_MODULE: saghat.settings.dev
      ALLOWED_HOSTS: '["localhost", "127.0.0.1"]'
      JWT_EXPIRE_MINUTES: 60
      BITPIN_API_KEY: ""
      STATIC_ROOT: /tmp/static

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Set up Python
        run: uv python install

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run migrations
        run: uv run python manage.py migrate

      - name: Run tests
        run: uv run pytest --tb=short -v

  # ──────────────────────────────────────────────────────────────────
  # Frontend: lint + type-check + build (runs only when frontend files change)
  # ──────────────────────────────────────────────────────────────────
  frontend:
    name: Frontend — Lint, Type-check & Build
    runs-on: ubuntu-latest
    if: >
      github.event_name == 'push' ||
      contains(toJson(github.event.pull_request.changed_files), 'src/frontend/')
    defaults:
      run:
        working-directory: src/frontend

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version-file: src/frontend/.nvmrc
          cache: npm
          cache-dependency-path: src/frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type-check
        run: npm run type-check

      - name: Build
        run: npm run build

  # ──────────────────────────────────────────────────────────────────
  # Docker build verification — runs after both upstream jobs pass
  # ──────────────────────────────────────────────────────────────────
  docker-build:
    name: Docker — Build Verification
    runs-on: ubuntu-latest
    needs: [backend-lint, backend-test, frontend]
    if: >
      always() &&
      !contains(needs.*.result, 'failure') &&
      !contains(needs.*.result, 'cancelled')

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build backend image
        uses: docker/build-push-action@v6
        with:
          context: src/backend
          file: src/backend/Dockerfile
          push: false
          tags: saghat-backend:ci

      - name: Build frontend image
        uses: docker/build-push-action@v6
        with:
          context: src/frontend
          file: src/frontend/Dockerfile
          push: false
          tags: saghat-frontend:ci
```

### 5.3 Path Filter Strategy

The `if:` conditions above use a pragmatic approach: on `push` events all jobs run (since `changed_files` is not available on push without extra API calls); on `pull_request` events the `changed_files` JSON is inspected for the relevant path prefix. A cleaner alternative is to use the [`dorny/paths-filter`](https://github.com/dorny/paths-filter) action:

```yaml
# Alternative path-filter approach (more robust for large PRs)
- name: Detect changed paths
  id: filter
  uses: dorny/paths-filter@v3
  with:
    filters: |
      backend:
        - 'src/backend/**'
      frontend:
        - 'src/frontend/**'

# Then gate each job with:
#   if: steps.filter.outputs.backend == 'true'
#   if: steps.filter.outputs.frontend == 'true'
```

Either approach satisfies the requirement; the `dorny/paths-filter` variant is more reliable for PRs that touch many files.

### 5.4 Job Dependency Graph

```
push / pull_request
        │
        ├── backend-lint   (paths: src/backend/**)
        ├── backend-test   (paths: src/backend/**)
        └── frontend       (paths: src/frontend/**)
                │
                └── docker-build  (needs: backend-lint + backend-test + frontend)
                                  (skipped if all upstreams were skipped)
```
