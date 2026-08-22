# RouteCare AI

AI-powered scheduling and route optimization platform for home healthcare
providers (therapists, PTAs, nurses, and the agencies that employ them).

> **Status: Phase 2 — Patient Management.**
> Auth/RBAC (Phase 1B) and shared backend infrastructure (Phase 1C) are
> in place; patient CRUD (list/search/filter/sort/paginate, create,
> view, edit, soft-delete) is now implemented end to end, backend and
> frontend. Excel import, scheduling, maps/routes, optimization, and
> analytics are still not built. See
> [`docs/10_Development_Roadmap.md`](docs/10_Development_Roadmap.md)
> for what's built in each subsequent phase, and
> [`docs/13_Coding_Standards.md`](docs/13_Coding_Standards.md) for how
> new modules should use the shared infrastructure.

---

## Tech Stack

| Layer          | Technology                              |
|----------------|------------------------------------------|
| Frontend       | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Backend        | FastAPI (Python), SQLAlchemy, Alembic    |
| Database       | PostgreSQL + PostGIS                     |
| Background jobs| Celery + Redis                           |
| Optimization   | Google OR-Tools *(added Phase 6)*        |
| Maps           | OpenStreetMap, Nominatim, OSRM *(added Phase 5)* |

Full architecture rationale lives in `docs/03_System_Architecture.md`.

---

## Project Structure

```
routecare-ai/
├── frontend/         Next.js + TypeScript + Tailwind + shadcn/ui
├── backend/          FastAPI + SQLAlchemy + Alembic
├── database/         DB notes (schema lives in backend/app/models once added)
├── docker/           Postgres init scripts, etc.
├── docs/             Architecture & planning documents
├── scripts/          Standalone dev utilities
└── docker-compose.yml
```

Backend module layout (per `docs/03_System_Architecture.md`):

```
backend/app/
├── main.py                # FastAPI app + middleware/exception/router wiring + health endpoints
├── core/
│   ├── config.py           # typed Settings, fails startup on insecure production config
│   ├── security.py         # bcrypt hashing, JWT encode/decode, opaque token helpers
│   ├── permissions.py      # UserRole, require_role, require_clinic_access, ensure_self_or_role
│   ├── dependencies.py     # get_current_user, get_current_clinic_id
│   ├── exceptions.py       # NotFoundError/UnauthorizedError/.../AppError + standardized envelope
│   ├── middleware.py       # RequestContextMiddleware (X-Request-ID + access log), SecurityHeadersMiddleware
│   ├── request_context.py  # contextvars backing request_id/user_id/clinic_id
│   ├── logging_config.py   # structured JSON logging
│   ├── health.py           # check_database/check_redis for readiness
│   └── rate_limiting.py    # no-op extension points (no backend wired up yet)
├── database/                # SQLAlchemy engine, session, declarative Base, portable GUID type, pagination.paginate()
├── models/                  # ORM models: Clinic, User, RefreshToken, PasswordResetToken, AuditLog, Patient, mixins.py
├── modules/
│   ├── auth/                 # register/login/logout/refresh/change-password/reset/me router
│   └── patients/              # patient list/create/get/update/delete router
├── schemas/                 # Pydantic request/response schemas; common.py has PaginationParams/PaginatedResponse
├── services/                # business logic (auth_service.py, patient_service.py, geocoding.py)
└── workers/                 # Celery app + task skeleton (no business tasks yet)
```

Frontend layout:

```
frontend/
├── app/
│   ├── login/                 # sign-in page
│   └── patients/               # list, new, and [id] (view/edit) pages
├── components/
│   ├── ui/                     # shadcn/ui primitives (button, input, table, alert-dialog, ...)
│   ├── layout/                 # AppHeader (nav + logout)
│   └── patients/                # PatientForm, shared by the new and edit flows
├── lib/
│   ├── api.ts                  # fetch wrapper, standardized ApiError, 401 -> refresh -> retry
│   ├── auth.ts                  # localStorage token storage
│   └── use-require-auth.ts      # client-side route guard
└── types/patient.ts            # TS types mirroring backend/app/schemas/patient.py
```

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- (For local, non-Docker development) Node.js 20+ and Python 3.12+

---

## Quick Start (Docker — recommended)

1. Copy the root environment file and adjust values if needed:

   ```bash
   cp .env.example .env
   ```

2. Start everything:

   ```bash
   docker compose up --build
   ```

3. Verify:

   - Backend health check: http://localhost:8000/health
   - Backend interactive API docs: http://localhost:8000/docs
   - Frontend: http://localhost:3000

That's it — Postgres (with PostGIS enabled automatically) and Redis start
alongside the backend and frontend, with hot-reload on both.

---

## Local Development (without Docker)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # point DATABASE_URL at your local Postgres
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### Database only (if you want Postgres/Redis via Docker but run the apps locally)

```bash
docker compose up postgres redis
```

Then verify connectivity:

```bash
python3 scripts/check_db_connection.py
```

---

## Migrations (Alembic)

`0001_create_auth_tables` creates `clinics`, `users`, `refresh_tokens`,
`password_reset_tokens`, and `audit_logs`; `0002_create_patients_table`
adds `patients`. Both target PostgreSQL:

```bash
cd backend
alembic upgrade head
```

`backend/alembic/env.py` reads `DATABASE_URL` from the same settings object
the app uses, so migrations always target the same database as the running
API. Future model changes follow the usual autogenerate flow:

```bash
alembic revision --autogenerate -m "description of the change"
alembic upgrade head
```

---

## Authentication

Full endpoint list: `POST /api/v1/auth/{register,login,logout,refresh,
change-password,request-password-reset,reset-password}`, `GET /api/v1/auth/me`.
All error responses share one shape (see "Shared Backend Infrastructure" below):
`{"success": false, "error": {"code", "message", "details"}, "request_id"}`.

**JWT flow.** Login/register/refresh return a short-lived **access token**
(default 30 min; `ACCESS_TOKEN_EXPIRE_MINUTES`) carrying `user_id`,
`clinic_id` (nullable — `null` for `SYSTEM_ADMIN`), `role`, and `exp` as
claims. Send it as `Authorization: Bearer <access_token>` on every
protected request. It is stateless and cannot be individually revoked —
that's what its short lifetime is for.

**Refresh token lifecycle.** The refresh token is *not* a JWT: it's a
high-entropy random string, returned to the client once, with only its
SHA-256 hash stored in the `refresh_tokens` table (default lifetime 7
days; `REFRESH_TOKEN_EXPIRE_DAYS`). Calling `POST /auth/refresh`
**rotates** it — the presented token is revoked and a brand-new
access+refresh pair is issued. If an already-revoked (previously
rotated-out) refresh token is ever presented again, that's treated as a
replay/theft signal and **every** refresh token for that user is
revoked, forcing re-login on all devices. `change-password` and
`reset-password` do the same proactively. `logout` revokes just the one
token it's given.

**RBAC.** Four roles — `SYSTEM_ADMIN`, `CLINIC_ADMIN`, `OFFICE_SCHEDULER`,
`THERAPIST` — defined in `app/core/permissions.py`. Any endpoint depends
on `get_current_user` (resolves + validates the bearer token) and, where
needed, `require_role(*roles)` (403s if the caller's role isn't allowed)
and/or `get_current_clinic_id` (resolves the caller's tenant; 403s for a
`SYSTEM_ADMIN` with no clinic context). Every future module should
compose these three rather than re-implementing auth/tenant checks.

**Password reset (backend only).** No email delivery service is
integrated yet. `POST /auth/request-password-reset` always returns the
same generic message regardless of whether the email exists (prevents
user enumeration); outside `ENVIRONMENT=production` it also returns the
raw `reset_token` directly in the response body so the flow is testable
without email. Swap that for a real email send once a provider is
chosen — the extension point is marked in
`app/services/auth_service.request_password_reset`.

**Rate limiting.** Not implemented yet. `app/core/rate_limiting.py`
defines no-op dependencies (`rate_limit_login`, `rate_limit_password_reset`,
`rate_limit_register`) already wired into the relevant routes as clearly
marked extension points for whichever backend (Redis counter, slowapi,
...) gets chosen later.

---

## Shared Backend Infrastructure

Cross-cutting infrastructure every future module (patients, scheduling,
...) builds on top of, rather than reimplementing per module. Full
conventions and code examples: [`docs/13_Coding_Standards.md`](docs/13_Coding_Standards.md).

- **Error handling.** Raise `NotFoundError` / `UnauthorizedError` /
  `ForbiddenError` / `ConflictError` / `ValidationError` /
  `BusinessRuleError` (`app/core/exceptions.py`) instead of a bare
  `HTTPException`. Every error becomes
  `{"success": false, "error": {"code", "message", "details"}, "request_id"}`.
  Success responses are **not** wrapped in a matching envelope — see the
  "when to wrap" note in the coding standards doc for why.
- **Request correlation.** Every response carries an `X-Request-ID`
  header (reused if the client sends a safe one, generated otherwise)
  via `RequestContextMiddleware`. The same ID appears in the error body
  and in every structured log line for that request.
- **Structured logging.** All logs are single-line JSON
  (`app/core/logging_config.py`), auto-tagged with `request_id`/
  `user_id`/`clinic_id` when available. Never log passwords, tokens, or
  patient PII — see the logging conventions doc section for the full rule.
- **Pagination.** `PaginationParams` (`app/schemas/common.py`) as a
  dependency + `paginate()` (`app/database/pagination.py`) for any list
  endpoint; page size is capped at 100 (default 25) and enforced by
  FastAPI's own validation, not by convention.
- **Filtering/sorting.** Deliberately not a generic abstraction — typed
  query params per endpoint. Documented pattern + example in the coding
  standards doc.
- **Tenant isolation.** `get_current_user`, `get_current_clinic_id`
  (`app/core/dependencies.py`), `require_role`, `require_clinic_access`
  (`app/core/permissions.py`) are the four dependencies every protected,
  clinic-scoped, or resource-owning endpoint should compose.
- **Health.** `GET /health/live` (process up, no dependency checks) vs.
  `GET /health/ready` (checks PostgreSQL + Redis, 503s if either is down).
- **Background jobs.** `app/workers/celery_app.py` + `tasks.py` — Celery
  is wired up (JSON serialization only, broker/backend from
  `REDIS_URL`) with a `ping` task proving the plumbing works; no
  business tasks exist yet (Excel import lands in Phase 3). Run a
  worker with `celery -A app.workers.celery_app worker --loglevel=info`,
  or `docker compose up worker`.
- **Production config safety.** `Settings` refuses to start with
  `ENVIRONMENT=production` if `JWT_SECRET_KEY`/`DATABASE_URL` still hold
  their insecure development defaults.

---

## Patient Management

Backend: `GET/POST /api/v1/patients`, `GET/PATCH/DELETE /api/v1/patients/{id}`
(`app/modules/patients/router.py`, `app/services/patient_service.py`,
`app/models/patient.py`). Scheduling-related information only, per
docs/04_Database_Design.md — no clinical/medical fields.

- **Access**: `CLINIC_ADMIN` and `OFFICE_SCHEDULER` get full CRUD;
  `THERAPIST` gets read-only (list/get) — there's no `therapist_id`/
  assignment on `Patient` yet, so "assigned patients" scoping is
  deferred to Phase 4 (Scheduling) once appointments exist to scope by.
  `SYSTEM_ADMIN` has no clinic and can't reach clinic patient data at all.
- **Cross-tenant safety**: `GET/PATCH/DELETE /patients/{id}` scope the
  query by `clinic_id` directly and return a plain 404 for a wrong-clinic
  ID — deliberately not the 403 `require_clinic_access` gives elsewhere,
  since patient records are called out as sensitive PII and a 403 would
  confirm the record exists in another clinic.
- **Soft delete**: `DELETE` sets `deleted_at`; every list/get query
  filters `deleted_at IS NULL`, so deleted patients are invisible to
  normal reads but recoverable at the DB level.
- **Geocoding boundary**: `app/services/geocoding.py` defines a
  `GeocodingProvider` protocol; `latitude`/`longitude` are stored only
  when supplied directly (no external geocoding call happens yet). A
  real provider (Nominatim, per Phase 5) swaps in behind
  `get_geocoding_provider()` without touching patient CRUD.

Frontend: `/patients` (search/ZIP filter/sort/pagination + loading,
empty, and error states), `/patients/new`, `/patients/[id]` (view, edit,
delete with an `AlertDialog` confirmation). None of this existed before
Phase 2, so it also includes the minimal supporting pieces patient pages
need: `/login`, a localStorage token store (`lib/auth.ts`) with an
automatic 401 → refresh → retry cycle (`lib/api.ts`), and a client-side
route guard (`lib/use-require-auth.ts`). This is intentionally minimal —
no global auth context, no data-fetching library — and is expected to
grow (e.g. a proper `AuthProvider`) as more authenticated pages arrive.

---

## Environment Variables

See `.env.example` (root), `backend/.env.example`, and
`frontend/.env.example` for the full list. Key ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (backend) |
| `REDIS_URL` | Redis connection string (backend/Celery) |
| `JWT_SECRET_KEY` | Signing key for auth tokens *(set a real secret before any real use)* |
| `NEXT_PUBLIC_API_BASE_URL` | Where the frontend expects the API |

---

## Known Notes

- **Fonts at build time:** the frontend uses `next/font/google` (Inter),
  which fetches font files from Google Fonts during `npm run build`.
  This requires outbound internet access in whatever environment runs
  the build (CI, your machine, etc.) — it's expected `next/font`
  behavior, not a bug.
- **Dependency freshness:** `npm audit` will flag Next.js advisories
  from very broad historical version ranges; the app pins the latest
  `14.2.x` patch release. Run `npm audit` periodically and upgrade as
  new patches land.
- **Password hashing uses `bcrypt` directly, not `passlib`.** `passlib`
  1.7.4 (last released 2020) is incompatible with `bcrypt>=4.1` — it
  probes a `bcrypt.__about__` attribute that no longer exists, so every
  hash/verify call raises. `app/core/security.py` calls the `bcrypt`
  library directly instead.
- **Patient/scheduling/import modules are still empty placeholders** —
  only `app/modules/auth/` is implemented so far.
- **Plain ASGI middleware, not `BaseHTTPMiddleware`.** `RequestContextMiddleware`/
  `SecurityHeadersMiddleware` are plain ASGI classes rather than
  Starlette's `BaseHTTPMiddleware` — the latter can run the wrapped app
  in a separate anyio task depending on Starlette version, which breaks
  the "set a contextvar deep inside the route, read it back after
  `call_next`" pattern request correlation relies on. See
  `app/core/middleware.py`'s docstring. This also means mypy's Starlette
  stubs flag them with a (harmless, `# type: ignore`d) structural typing
  mismatch in `app/main.py`.
- **Lint/format config (`backend/pyproject.toml`) was added in Phase
  1C.** Pre-existing Phase 1A/1B files that would reformat under `black`
  but weren't touched this phase were deliberately left as-is to avoid
  unrelated churn — run `black backend/app backend/tests` once to
  normalize the whole tree when convenient.

---

## Documentation

All product/architecture docs referenced during development live in
[`docs/`](docs/):

- `00_Vision.md`
- `01_Product_Requirements_Document.md`
- `02_User_Stories.md`
- `03_System_Architecture.md`
- `04_Database_Design.md`
- `05_API_Design.md`
- `06_UI_UX_Guidelines.md`
- `07_AI_Optimization_Engine.md`
- `08_Import_System.md`
- `09_Security_Privacy_Compliance.md`
- `10_Development_Roadmap.md`
- `11_Claude_Development_Prompts.md`
- `12_MVP_Launch_Strategy.md`
- `13_Coding_Standards.md`

## Core Principle

AI recommends. Humans decide. RouteCare AI never automatically changes a
schedule without explicit user approval — this rule applies to every
feature built on top of this foundation.