# RouteCare AI

AI-powered scheduling and route optimization platform for home healthcare
providers (therapists, PTAs, nurses, and the agencies that employ them).

> **Status: Phase 10 — End-to-End MVP Validation & Clinic Pilot Prep.**
> Auth/RBAC (Phase 1B), shared backend infrastructure (Phase 1C), patient
> management (Phase 2), TheraOffice Excel import (Phase 3), therapist
> management/scheduling (Phase 4), the maps/travel-time foundation
> (Phase 5), the schedule optimization engine (Phase 6), the optimization
> workflow/What-If/weekly mode (Phase 7), the operational analytics
> dashboard (Phase 8), and production hardening - real rate limiting,
> audit logging, pooled HTTP clients, request-size limits, non-root
> production Docker images (Phase 9) - are all in place. Phase 10
> validated the complete clinic workflow end-to-end (clinic setup →
> import → schedule → optimize → accept/reject → What-If → analytics),
> added a deterministic demo-data seed script, an end-to-end backend test
> covering that full journey, and fixed the integration issues that
> surfaced along the way (see "Known Notes" below for what was found and
> fixed this phase). The optimizer still only ever *recommends* - nothing
> changes on the calendar until a human explicitly accepts or applies it,
> which always re-validates against the live schedule first. See
> [`docs/10_Development_Roadmap.md`](docs/10_Development_Roadmap.md) for
> the phase-by-phase history,
> [`docs/13_Coding_Standards.md`](docs/13_Coding_Standards.md) for how
> modules use the shared infrastructure, and
> [`docs/14_Production_Deployment.md`](docs/14_Production_Deployment.md)
> for the actual deployment/security/backup runbook.

---

## Tech Stack

| Layer          | Technology                              |
|----------------|------------------------------------------|
| Frontend       | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Backend        | FastAPI (Python), SQLAlchemy, Alembic    |
| Database       | PostgreSQL + PostGIS                     |
| Background jobs| Celery + Redis                           |
| Optimization   | Google OR-Tools (CP-SAT) *(added Phase 6)* |
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
│   ├── cache.py             # generic Redis-backed JSON get/set with TTL - geocoding/travel-time cache
│   └── rate_limiting.py    # Redis-backed fixed-window limits (login/register/reset + per-user
│                            # "expensive operation" limits) - see Phase 9 section below
├── database/                # SQLAlchemy engine, session, declarative Base, portable GUID type, pagination.paginate()
├── models/                  # ORM models: Clinic, User, RefreshToken, PasswordResetToken, AuditLog, Patient,
│                            # ImportJob, ImportRow, ImportRowError, Therapist, TherapistAvailability,
│                            # PatientAvailability, Appointment, OptimizationRequest,
│                            # OptimizationRecommendation, mixins.py (GeocodingStatus lives on patient.py)
├── modules/
│   ├── auth/                 # register/login/logout/refresh/change-password/reset/me router
│   ├── patients/              # patient list/create/get/update/delete/geocode + patient availability router
│   ├── imports/                # upload/mapping/preview/errors/confirm router
│   ├── therapists/              # therapist list/create/get/update/geocode + weekly availability router
│   ├── scheduling/               # appointment list(calendar)/create/get/update/cancel + /validate router
│   ├── maps/                      # /travel-time, /travel-time-matrix (read-only, all clinic roles)
│   ├── optimization/               # /requests, .../recommendations, .../accept, .../reject, /what-if, /what-if/apply
│   └── analytics/                   # /overview, /therapists, /efficiency, /optimization-impact
├── schemas/                 # Pydantic request/response schemas; common.py has PaginationParams/PaginatedResponse
├── services/                # business logic: auth_service.py, patient_service.py, geocoding.py,
│                            # import_service.py, column_mapping.py, duplicate_detection.py,
│                            # file_validation.py, excel_parser.py, therapist_service.py,
│                            # availability_service.py, appointment_service.py, scheduling_validation.py,
│                            # routing.py (pooled httpx.Client - see Phase 9), travel_time_service.py,
│                            # optimization_engine.py (pure CP-SAT/insertion-search algorithms, no DB),
│                            # optimization_service.py (orchestration), analytics_service.py (Phase 8
│                            # metric computation), audit_service.py (Phase 9 - shared AuditLog writer)
└── workers/                 # Celery app (task_soft_time_limit/task_time_limit - Phase 9) +
                              # tasks.py (demo) + import_tasks.py (validate/execute) +
                              # optimization_tasks.py (run_optimization_task)
```

Standalone dev utilities live in [`scripts/`](scripts/) at the repo root - notably
[`scripts/seed_demo_data.py`](scripts/seed_demo_data.py) (Phase 10), which creates a full
deterministic demo clinic through the real API; see "Demo Data" below.

Frontend layout:

```
frontend/
├── app/
│   ├── login/                 # sign-in page
│   ├── dashboard/               # analytics dashboard - date-range picker, stat tiles, charts,
│   │                            # therapist drill-down, optimization-impact panel (Phase 8)
│   ├── patients/                # list, new, and [id] (view/edit) pages
│   ├── imports/patients/         # the 5-step import wizard page
│   ├── therapists/                # list, new, and [id] (profile/edit + weekly availability) pages
│   ├── schedule/                  # day/week calendar, appointment create/edit/cancel
│   ├── map/                        # patient/therapist location map + travel-time calculator
│   └── optimize/                    # optimization dashboard - run/status/recommendations/What-If
├── components/
│   ├── ui/                     # shadcn/ui primitives (button, input, table, alert-dialog, progress, ...)
│   ├── layout/                 # AppHeader (nav + logout)
│   ├── analytics/                # StatTile, HorizontalBarList/DaySeriesChart (dependency-free SVG/CSS
│   │                              # charts - no charting library added), DateRangeControls,
│   │                              # TherapistBreakdownTable, EfficiencyPanel, OptimizationImpactPanel
│   ├── patients/                 # PatientForm, shared by the new and edit flows
│   ├── imports/                   # ImportStepper, Upload/Mapping/Preview/Results step components
│   ├── therapists/                 # TherapistForm, AvailabilityEditor
│   ├── scheduling/                  # AppointmentForm (live conflict check via /validate), AppointmentCard
│   ├── maps/                          # LocationCard (geocode status + action), MapView (Leaflet, dynamic-
│   │                                  # imported client-only), TravelTimeCalculator
│   └── optimization/                   # RecommendationCard (before/after driving time, compare/accept/
│                                       # reject/modify), WhatIfPanel (MOVE/ADD/REMOVE, evaluate + apply)
├── lib/
│   ├── api.ts                  # fetch wrapper (JSON + multipart), standardized ApiError, 401 -> refresh
│   │                            # -> retry, and a hard redirect to /login if the refresh itself fails
│   │                            # (Phase 10 fix - see "Known Notes")
│   ├── auth.ts                  # localStorage token storage
│   └── use-require-auth.ts      # client-side route guard
└── types/                      # TS types mirroring backend/app/schemas/{patient,import_job,therapist,
                                 # appointment,maps,optimization,analytics}.py and auth.py's UserPublic
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
adds `patients`; `0003_create_import_tables` adds `imports`,
`import_rows`, and `import_errors`; `0004_create_scheduling_tables`
adds `therapists`, `therapist_availability`, `patient_availability`,
and `appointments`; `0005_add_geocoding_fields` adds `geocoding_status`/
`geocoded_at`/`location_verified` to `patients` and `therapists` (no new
tables - travel-time results are cached in Redis, not persisted);
`0006_create_optimization_tables` adds `optimization_requests` and
`optimization_recommendations`; `0007_optimization_workflow_improvements`
adds the `WEEK_SCHEDULE_OPTIMIZATION` enum value, `target_date`/
`accepted_at`/`rejected_at`/`marginal_drive_minutes`/`marginal_distance_miles`
on `optimization_recommendations`, and drops
`optimization_requests.accepted_recommendation_id`. All target PostgreSQL:

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

**Rate limiting** (Phase 9). Redis-backed fixed-window counters in
`app/core/rate_limiting.py` - `rate_limit_login`/`rate_limit_password_reset`
(keyed by IP+email) and `rate_limit_register` (keyed by IP) guard the auth
routes; the generic `rate_limit(bucket, limit=, window_seconds=)` factory
guards per-user "expensive operation" endpoints (Excel import upload,
optimization-request creation, explicit geocode, travel-time-matrix).
Fails **open**, not closed - a Redis outage degrades to "not rate
limited" rather than locking every user out, matching `app/core/cache.py`'s
existing philosophy. See `docs/14_Production_Deployment.md` for the full
list of configurable limits.

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

## Patient Import (TheraOffice Excel)

Backend: `POST /api/v1/imports/patients` (upload), `GET /api/v1/imports`
(history), `GET /api/v1/imports/{id}` (status/progress),
`POST /api/v1/imports/{id}/mapping` (confirm column mapping, kicks off
background validation), `GET /api/v1/imports/{id}/preview` (paginated
row-by-row results), `GET /api/v1/imports/{id}/errors`,
`POST /api/v1/imports/{id}/confirm` (kicks off the background import).
Restricted to `CLINIC_ADMIN`/`OFFICE_SCHEDULER` - therapists can't bulk
import. Nothing is written to the `patients` table before `/confirm`.

- **File safety**: type is determined by sniffing the first bytes
  (ZIP/OLE2 signatures), never by filename or `Content-Type`; size-capped
  (10 MB default, `IMPORT_MAX_FILE_SIZE_BYTES`); a rejected file never
  touches disk. Accepted files are written atomically (temp file +
  `os.replace`) into a private, per-clinic directory
  (`IMPORT_STORAGE_DIR`, default `var/imports/`) that's never served by
  any endpoint. `app/services/file_validation.scan_for_malware` is a
  documented no-op extension point for a real scanner later.
- **Column mapping**: `app/services/column_mapping.py` suggests a
  mapping from the uploaded headers to Patient fields (exact alias match,
  then fuzzy fallback) - the user reviews/edits it before anything is
  parsed for real. Every row is then validated by literally constructing
  a `PatientCreate` from it (Phase 2's existing validation, not
  reimplemented).
- **Duplicates - detected and reported, never merged.** Matching never
  relies on name similarity alone: an exact match needs an exact signal
  (email/phone/name+ZIP); a "probable" match needs name similarity *and*
  a corroborating signal (same ZIP). Duplicates are skipped by default;
  the user can explicitly choose to import them as new records anyway.
  The import pipeline **only ever creates new `Patient` rows** - it never
  updates or deletes an existing one.
- **Background processing**: column-mapping confirmation and the actual
  import both dispatch a Celery task (`app/workers/import_tasks.py`) so
  large files don't block the request; `GET /imports/{id}` reports live
  progress (`processed_records`/`total_records`). Set
  `CELERY_TASK_ALWAYS_EAGER=true` for local dev/demos without a running
  worker+Redis (never in production - enforced by the same startup
  validator that guards `JWT_SECRET_KEY`).
- **Status lifecycle**: `PENDING` → `PROCESSING` → `PENDING` again once
  validated (ready for review) → `PROCESSING` again once confirmed →
  `COMPLETED`/`COMPLETED_WITH_ERRORS`/`FAILED`. `PENDING` is reused for
  both waiting points rather than inventing extra states; callers tell
  them apart by whether `valid_records` is populated yet.

Frontend: `/imports/patients` - a 5-step wizard (Upload → Column Mapping
→ Validation & Duplicate Review → Preview & Confirm → Results) with a
polling progress bar during both background phases, linked from the
"Import from Excel" button on `/patients`.

---

## Therapist Management & Scheduling

Backend: `GET/POST /api/v1/therapists`, `GET/PATCH /api/v1/therapists/{id}`,
`GET/PUT /api/v1/therapists/{id}/availability` (`app/modules/therapists/router.py`,
`app/services/therapist_service.py`, `app/services/availability_service.py`,
`app/models/therapist.py`, `app/models/therapist_availability.py`).
Appointments: `GET/POST /api/v1/appointments` (the list endpoint doubles
as the calendar - filter by `start_date`/`end_date`/`therapist_id`/
`patient_id`/`status`), `GET/PATCH/DELETE /api/v1/appointments/{id}`
(`DELETE` cancels, it never hard-deletes), `POST /api/v1/appointments/validate`
(dry-run check, same validation the create/update endpoints enforce -
used by the frontend for live conflict feedback before submit).
`GET/PUT /api/v1/patients/{id}/availability` was added alongside the
existing patient router. No AI optimization, route optimization, maps,
or What-If sandbox - out of scope for this phase by design.

- **No duplicate user accounts**: `Therapist` is 1:1 with `User` via a
  unique `user_id`. `POST /therapists` creates both rows atomically;
  `PATCH /therapists/{id}` splits the update between `User` fields
  (name/email/`is_active`) and `Therapist` profile fields and never
  constructs a new `User`. Deactivation reuses `User.is_active` rather
  than a separate flag.
- **Availability is recurring-weekly only** (`day_of_week` 0=Monday..
  6=Sunday, matching Python's `date.weekday()` - no date-specific
  overrides, per the task's "don't build a complex recurring-calendar
  standard" scope limit). A day with no rows is a day off; a break
  within a working day is an `is_available=False` row layered inside an
  otherwise-working window. `PUT` replaces a therapist's/patient's
  entire weekly set - simpler and less error-prone than a partial
  patch for a small, infrequently-edited list. Unconfigured patient
  availability means "available anytime," matching how flexible
  homecare patient scheduling actually is; rows only ever add
  constraints, never relax them.
- **Validation is centralized, not duplicated.** `create_appointment`,
  `update_appointment`, and the `/validate` dry-run endpoint all share
  the same `_validate`/`_validate_patient_availability` functions in
  `app/services/appointment_service.py`, which check (in order):
  therapist/patient exist and belong to the caller's clinic, the
  therapist is active, no overlap with an existing non-cancelled
  appointment (half-open `[start, end)` ranges), the requested time
  falls inside a working-hours rule and outside any break, and it's
  inside a configured patient-availability window if one exists.
  Failures raise `BusinessRuleError` with a clear message, e.g.
  *"Therapist already has an appointment from 1:00 PM to 2:00 PM."* -
  never a silent reschedule of the conflicting appointment.
- **Naive DATE/TIME columns, deliberately.** `Appointment.scheduled_date`/
  `start_time`/`end_time` are interpreted as clinic-local wall-clock
  time rather than `TIMESTAMPTZ`. Every scheduling query is already
  scoped to one clinic, so there's never a cross-timezone comparison in
  this system's usage pattern - see the docstring in
  `app/models/appointment.py` for the full reasoning if that changes
  later (e.g. a multi-timezone clinic network).
- **Row-level RBAC for `THERAPIST`**: a single `restrict_to_therapist_id`
  parameter, resolved once per request from the caller's own linked
  `Therapist` profile, threads through list/get/update/cancel so a
  therapist only ever sees or modifies their own appointments (a
  `therapist_id` query param is silently overridden, not rejected) and
  can't reassign an appointment to a different patient/therapist
  (`APPOINTMENT_FIELD_NOT_ALLOWED`). `CLINIC_ADMIN`/`OFFICE_SCHEDULER`
  manage all therapists/appointments in their clinic; `SYSTEM_ADMIN` has
  no clinic and can't reach any of it.

Frontend: `/therapists` (search/status filter/pagination), `/therapists/new`,
`/therapists/[id]` (profile view/edit, an Activate/Deactivate action, a
weekly `AvailabilityEditor`, and an upcoming-appointments summary).
`/schedule` is the main calendar - Day/Week toggle, a therapist filter
(Week view pins to one therapist, since a 7-day-by-all-therapists grid
isn't a scope requirement this phase), a "+ New Appointment" action, and
click-to-edit appointment cards grouped by therapist in Day/All view.
No drag-and-drop, per the task's explicit "keep it out if it needs a
large new dependency" guidance - click/edit covers the same manual-
scheduling workflow reliably. `AppointmentForm` debounces a call to
`POST /appointments/validate` as the user fills in the form and shows
the resulting conflicts inline *before* they submit, but the actual
create/update/cancel calls always re-validate server-side - the
frontend check is a UX convenience, never the source of truth.

---

## Maps & Travel-Time Engine

Backend: `POST /api/v1/patients/{id}/geocode`, `POST /api/v1/therapists/{id}/geocode`
(re-run geocoding from the current address on demand - e.g. for a
patient imported before geocoding existed, or one whose address
previously failed to resolve). `POST /api/v1/maps/travel-time` and
`POST /api/v1/maps/travel-time-matrix` compute driving distance/time
between any two (or up to `MAPS_MAX_MATRIX_POINTS`, default 25) of a
patient, a therapist, or a raw lat/long coordinate - read-only, open to
every clinic role. This phase is the location/travel-time *foundation*
only - no schedule optimization, route ordering, or automatic
appointment movement; see `app/services/travel_time_service.py`'s
docstring for exactly how the optimization engine (Phase 6) is meant to
consume it.

- **Provider-independent by design**: `app/services/geocoding.py`
  (`GeocodingProvider` Protocol, real `NominatimGeocodingProvider`) and
  `app/services/routing.py` (`RoutingProvider` Protocol, real
  `OSRMRoutingProvider`) mirror each other's shape. Neither commercial
  provider is hardcoded anywhere else in the codebase - swapping either
  out means changing one factory function
  (`get_geocoding_provider`/`get_routing_provider`), same seam Phase 2
  already established for geocoding. Public OpenStreetMap/Nominatim/OSRM
  demo servers are the defaults (`NOMINATIM_BASE_URL`/`OSRM_BASE_URL`),
  self-hostable later without touching any caller.
- **Never blocks on a slow/failed external call**: both providers have
  a configurable timeout (`GEOCODING_TIMEOUT_SECONDS`/
  `ROUTING_TIMEOUT_SECONDS`, default 5s) and turn every failure mode -
  invalid/incomplete address, no route found, network error, timeout,
  malformed response - into a plain `None`, never an exception. A
  geocoding failure leaves a patient/therapist in `FAILED` status rather
  than blocking their creation; a travel-time failure returns
  `{"reachable": false}` rather than a 500.
- **Manual overrides are never silently clobbered.** `Patient`/`Therapist`
  each track `geocoding_status` (`PENDING`/`GEOCODED`/`FAILED`/`MANUAL`),
  `geocoded_at`, and `location_verified`. Supplying coordinates directly
  always marks them `MANUAL` + verified; editing the address on an
  already-verified record does *not* trigger a silent re-geocode - see
  `app/services/patient_service.py`'s docstring for the full state
  machine (and `app/services/therapist_service.py`'s, which mirrors it
  for `home_address`).
- **Redis caching, tenant-scoped.** `app/core/cache.py` is a generic
  get/set-JSON-with-TTL wrapper around the same Redis already used for
  Celery; any Redis error is treated as a cache miss, so a cache outage
  degrades to "always call the provider" rather than breaking the
  feature. Geocoding results cache ~30 days
  (`GEOCODE_CACHE_TTL_SECONDS`), travel-time results ~24 hours
  (`TRAVEL_TIME_CACHE_TTL_SECONDS`) - both cache keys are namespaced per
  `clinic_id`, even though a geocoded address's coordinates aren't
  inherently clinic-specific data, per the explicit requirement that
  caching never create a cross-tenant data path.
- **Batched, not one-request-per-pair.** `get_travel_time_matrix`
  (`app/services/travel_time_service.py`) checks the cache per pair
  first; if anything is missing, it issues exactly one OSRM `/table`
  request for the whole matrix (OSRM computes the full N x N in one call
  regardless of which subset is actually needed) rather than N² separate
  `/route` calls. Matrix requests are capped at `MAPS_MAX_MATRIX_POINTS`
  points and always computed synchronously within the request - large,
  clinic-wide matrices for the optimization engine are Phase 6's problem
  (a background job), not this phase's.

Frontend: `/map` - patient and therapist markers on a Leaflet
(OpenStreetMap tiles) map, click-to-select with a details panel, and a
travel-time calculator (pick any two geocoded locations, see distance
and driving time). Patient markers show name/address/coordinates only
in the details panel - no phone/email/scheduling notes on the map
itself, per the "don't expose more than needed" guidance. Patients
without coordinates yet are listed separately with their geocoding
status rather than silently omitted. `Patient`/`Therapist` detail pages
also gained a `LocationCard` (geocoding status badge, coordinates, a
"Geocode now"/"Re-geocode" action) - the same component, reused, so
"has this record been geocoded" is answerable from either page or the
map.

---

## Schedule Optimization Engine

Introduced backend-only in Phase 6; Phase 7 (below) adds the user-facing
workflow, What-If apply, and weekly mode on top of the same engine.
`POST /api/v1/optimization/requests` (create + queue),
`GET /api/v1/optimization/requests/{id}` (status),
`GET /api/v1/optimization/requests/{id}/recommendations`,
`POST .../recommendations/{id}/accept`. Available to every clinic role; a
`THERAPIST` caller is restricted to their own schedule, same
`restrict_to_therapist_id` pattern as `app.modules.scheduling.router`.

- **Two modes, two different algorithms - see
  `app/services/optimization_engine.py`'s module docstring for the full
  reasoning.** `DAY_SCHEDULE_OPTIMIZATION` (re-order one therapist's
  existing day) is solved with **OR-Tools CP-SAT**: a permutation
  variable (`AllDifferent`) picks the visit order, per-visit start-time
  domains are built from the intersection of therapist working
  hours/breaks and patient availability
  (`compute_allowed_start_minutes`), and travel time between consecutive
  stops is looked up via `AddElement` on a flattened travel-time matrix
  indexed by an affine expression of the order variables (no
  variable-times-variable multiplication needed - `AddElement` is
  Or-Tools' native "index into an array by variable" primitive).
  `NEW_PATIENT_PLACEMENT` (find a slot for one not-yet-scheduled
  patient) is a bounded insertion-point search instead - it never
  disturbs any existing appointment, so the problem is "evaluate
  inserting before/between/after each day's visits and rank by marginal
  added travel time," not a joint reordering a solver would earn its
  keep on.
- **Objective**: `minimize total_drive_minutes*1.0 + total_gap_minutes*OPTIMIZATION_GAP_WEIGHT
  + appointments_moved*OPTIMIZATION_CHANGE_PENALTY_WEIGHT` - drive time
  is the anchor (task's explicit primary objective), gaps and
  unnecessary reshuffling are configurable soft penalties, not
  hardcoded. Distance is reported but not separately weighted - it's
  tightly correlated with drive time from the same routing calculation.
- **Hard constraints never silently violated.** If CP-SAT reports
  `INFEASIBLE`, or the insertion search finds no feasible slot anywhere
  in the window, the request still completes normally
  (`status=COMPLETED`) with a single recommendation flagged
  `solver_status="INFEASIBLE"` and a clear explanation - "no feasible
  schedule" is a valid, expected answer, never a failure. `FAILED` is
  reserved for the optimizer not being able to run at all (an
  ungeocoded patient/therapist, an unexpected error) - see
  `app/services/optimization_service.run_optimization`'s docstring.
- **Acceptance replays through the existing, already-validated
  appointment code - it never mutates an appointment directly except in
  one specific case.** `NEW_PATIENT_PLACEMENT` acceptance calls
  `appointment_service.create_appointment` unchanged, getting full
  re-validation for free. `DAY_SCHEDULE_OPTIMIZATION` acceptance
  deliberately does *not* call `update_appointment` in a loop - doing so
  one appointment at a time against the live DB produces false conflicts
  whenever two appointments are effectively swapping slots (each would
  still see the other's pre-move time as "existing"). Instead it
  re-validates the *entire* proposed day at once (every appointment's
  final position checked for overlap together, plus each changed
  appointment's working-hours/patient-availability rules via the same
  pure `scheduling_validation` functions create/update use) and only
  then applies every change in a single transaction. Any drift since the
  recommendation was generated - a cancelled appointment, a schedule
  change, an appointment that no longer exists - is rejected as
  `STALE_RECOMMENDATION`, never silently applied.
- **Background processing.** `app/workers/optimization_tasks.py`
  dispatches to `optimization_service.run_optimization`, same
  `CELERY_TASK_ALWAYS_EAGER` dev-mode pattern as imports. Creating a
  request always returns immediately (`status=PENDING`) - the solve
  never runs inside the request/response cycle.
- **What-If evaluation is stateless; applying is real.**
  `POST /optimization/what-if` creates no `OptimizationRequest`,
  persists nothing - it reuses `appointment_service.validate_appointment`
  for feasibility and a shared `_day_metrics` helper (built on the same
  pure `optimize_day_schedule`-adjacent `fixed_order_metrics` function)
  to report drive-time/distance before vs. after. Phase 7 adds
  `POST /optimization/what-if/apply`, which commits the change for real -
  see the Phase 7 section below.
- **Solver limits are configurable, not hardcoded.**
  `OPTIMIZATION_MAX_SOLVE_SECONDS` (default 10s) caps CP-SAT's search;
  it returns the best `FEASIBLE` solution found rather than failing if
  the time limit is hit before proving optimality.
  `OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY` (default 20) bounds the
  problem size a single `DAY_SCHEDULE_OPTIMIZATION` request will
  attempt, per the "don't optimize unnecessarily large search spaces"
  requirement.

---

## Optimization Workflow, What-If & Weekly Mode

Backend: `POST /api/v1/optimization/requests/{id}/recommendations/{id}/reject`
(new), `POST /api/v1/optimization/what-if/apply` (new - commits a
What-If scenario for real), and `mode: "WEEK_SCHEDULE_OPTIMIZATION"` on
the existing `POST /optimization/requests`. Frontend: `/optimize` - a
full dashboard (`app/optimize/page.tsx`) to select therapist/mode/date,
start optimization, watch it progress, review recommendations, and
accept/reject/modify - plus a standalone `WhatIfPanel`
(`components/optimization/what-if-panel.tsx`) usable on its own or
pre-filled from a recommendation's "Modify" action.

- **Weekly mode orchestrates the existing day algorithm - it does not
  duplicate it.** `_run_week_schedule_optimization`
  (`app/services/optimization_service.py`) snaps `target_date` to that
  week's Monday and calls the same `_compute_day_schedule_recommendation`
  function once per day (Monday-Sunday), the identical function a plain
  `DAY_SCHEDULE_OPTIMIZATION` request calls once. A day that can't even
  be attempted (e.g. an ungeocoded patient) becomes an `ERROR`-flagged
  recommendation for *that day only* - it never fails the whole week.
  Redis already caches travel-time by clinic+coordinate pair (Phase 5),
  so a patient seen on multiple days that week is only ever routed once
  - no new caching logic was needed for "reuse travel-time data."
- **Four distinguishable per-day outcomes**, all represented as an
  `OptimizationRecommendation` row tagged with its own `target_date`
  (new this phase - previously every recommendation shared its parent
  request's single date): a real reorder (`solver_status` `OPTIMAL`/
  `FEASIBLE`, `recommendation_data.appointments` non-empty), no changes
  needed (`OPTIMAL`, empty `appointments`, `reason_codes: ["NO_APPOINTMENTS"]`
  or `["ALREADY_OPTIMAL"]`), no feasible schedule (`INFEASIBLE`), or a
  day that failed to even run (`ERROR`, `explanation` holds why).
- **Acceptance is per-recommendation, not per-request** (see the schema
  section below) - each of a week's 7 recommendations can be accepted or
  left alone independently. The one exception: `NEW_PATIENT_PLACEMENT`'s
  up to 3 ranked alternatives all propose scheduling the *same* new
  patient, so accepting one blocks the others
  (`RECOMMENDATION_ALREADY_ACCEPTED`) - day/week recommendations never
  compete with each other by construction (exactly one per date).
- **Reject is a lightweight, reversible marker**
  (`OptimizationRecommendation.rejected_at`) - not a lock. A rejected
  recommendation can still be accepted later (a change of mind), which
  clears `rejected_at` cleanly; an already-*accepted* recommendation
  cannot be rejected.
- **"Modify" is not a separate backend concept - it's What-If.** The
  recommendation review UI's "Modify" button on a changed appointment
  opens the `WhatIfPanel` pre-filled with that appointment/date/time, so
  the user can tweak it, see the live feasibility/impact, and apply
  their own version instead of the AI's - reusing the exact same
  evaluate/apply endpoints a standalone What-If scenario uses, rather
  than inventing a second "modify recommendation" code path.
- **What-If now supports three scenario types** (`MOVE`, `ADD`, `REMOVE`)
  and an optional duration override on `MOVE`/`ADD`, covering every
  example the task listed (move to another time/day, add a new patient,
  remove an appointment, change duration). `POST /optimization/what-if/apply`
  re-validates against the *live* database via the same
  `appointment_service.validate_appointment`/`create_appointment`/
  `update_appointment`/`cancel_appointment` every other mutation path
  uses - never a cached/precomputed result - so a scenario that's gone
  stale between evaluate and apply (someone else changed the schedule in
  the meantime) is rejected with a clear message, not silently applied.

---

## Analytics & Efficiency Dashboard

Backend: `GET /api/v1/analytics/{overview,therapists,efficiency,optimization-impact}`
(`app/modules/analytics/router.py`, `app/services/analytics_service.py`).
All four accept `period` (`today`/`this_week`/`last_week`/`this_month`/`custom`)
plus `start_date`/`end_date` for `custom`; the latter three also accept
`?therapist_id=` to drill into one therapist. Frontend: `/dashboard`.

- **Every number is computed server-side** - the frontend only ever
  renders what these endpoints return, never recomputes a metric itself.
- **Driving time/distance isn't stored anywhere** - it's derived the
  same way the optimizer/What-If already do it: a therapist's actual
  chronological route for a day, built from geocoded appointment
  locations and run through the same `travel_time_service`/
  `optimization_engine.fixed_order_legs` machinery (a Phase 10-era
  primitive: total driving *including* home-adjacent legs is a different
  number from average driving *between* appointments, and both come from
  one pass over the same computed legs, never two separate calculations).
- **Only accepted recommendations count as savings.** Filtering on
  `accepted_at IS NOT NULL AND time_saved_minutes IS NOT NULL`
  structurally excludes rejected recommendations and What-If (which
  never persists a row at all) for free, and separates
  `NEW_PATIENT_PLACEMENT` (a marginal cost, not a saving - no
  `time_saved_minutes`) from genuine day/week-reorder savings.
- **RBAC mirrors the rest of the app**: `CLINIC_ADMIN`/`OFFICE_SCHEDULER`
  see clinic-wide numbers; `THERAPIST` is always restricted to their own
  data server-side, regardless of what `?therapist_id=` says.
- **No new charting dependency.** `components/analytics/bar-chart.tsx`'s
  horizontal-bar and day-series charts are plain CSS/SVG, matching the
  project's existing "don't add a dependency for something this simple"
  stance (`lib/api.ts`'s own docstring sets this precedent).

---

## Production Hardening & Security

A security/reliability pass (Phase 9) - see `docs/14_Production_Deployment.md`
for the full write-up (env vars, deployment requirements, security
assumptions, backup/restore, troubleshooting). Highlights:

- **Rate limiting** - see the Authentication section above.
- **Audit logging** (`app/services/audit_service.py`, the pre-existing
  `audit_logs` table): login/logout/failed-login (Phase 1B) plus
  patient create/update/delete, therapist create/deactivate/reactivate,
  appointment create/update/cancel, import confirmation, and
  optimization-recommendation acceptance. Every record carries
  `clinic_id` (tenant isolation) and the acting `user_id`; values are
  deliberately minimal (changed field *names*, never PII values).
- **Upload memory safety** - the import endpoint reads in bounded 1 MB
  chunks and aborts as soon as `IMPORT_MAX_FILE_SIZE_BYTES` is exceeded,
  instead of buffering an arbitrarily large upload into memory first.
  A generic `MaxBodySizeMiddleware` caps every other JSON endpoint at
  `MAX_REQUEST_BODY_BYTES` (default 1 MB).
- **Pooled HTTP clients** - `routing.py` and `geocoding.py` each reuse
  one `httpx.Client` per process instead of opening a fresh connection
  per call (previously a documented known limitation).
- **Celery reliability** - `task_soft_time_limit`/`task_time_limit`
  backstop a hung job; `run_optimization` refuses to recompute a request
  that isn't `PENDING`, so a redelivered/duplicate task message can
  never insert duplicate recommendation rows.
- **Production config validation** - `Settings` refuses to start with
  `ENVIRONMENT=production` if `JWT_SECRET_KEY`/`DATABASE_URL` hold dev
  defaults, `CORS_ORIGINS` is empty/`localhost`, or
  `CELERY_TASK_ALWAYS_EAGER` is true.
- **Production Docker** - `backend/Dockerfile.prod` (non-root `appuser`,
  healthchecked, no `--reload`) and `frontend/Dockerfile.prod`
  (multi-stage `next build`+`next start`, non-root `node` user,
  healthchecked) are separate from the dev Dockerfiles, which keep
  running as root with a bind-mounted, hot-reloading dev server on
  purpose - see each Dockerfile's own comments. `docker-compose.prod.yml`
  is a standalone (not an overlay) production compose file - see its
  header comment for why.

---

## Demo Data

`scripts/seed_demo_data.py` creates one deterministic, fictional home-
health clinic through the real HTTP API (not by writing to the database
directly, so every piece of seeded data goes through the same
validation/geocoding/audit logic a real user's browser would trigger):
3 therapists (different availability shapes, including a part-time one),
8 patients (a mix of near/far addresses and one with a real availability
constraint), a week of appointments (including one day deliberately laid
out in a non-optimal order so the optimizer has something to find), a
demonstrated scheduling-conflict rejection, and one real optimization
run + accepted recommendation so the dashboard/analytics have genuine
data to show immediately. Patient/therapist coordinates are supplied
directly (never geocoded live), so the script never depends on Nominatim
being reachable.

```bash
# With the dev stack already running (docker compose up, migrations applied):
python scripts/seed_demo_data.py
```

Prints the demo login (`dana.admin@routecare-demo.example.com` / a fixed
password) on success. Appointments are always seeded into the **current**
calendar week (not "next" week) specifically so the dashboard's default
`this_week` view shows real data immediately - see the script's own
`_this_monday()` docstring, a Phase 10 fix (a first version used "next
Monday," which left a fresh demo clinic's dashboard showing all zeros
until the following week).

---

## Testing

```bash
cd backend
pytest                              # full suite
pytest tests/test_e2e_workflow.py   # the Phase 10 end-to-end journey alone
```

`tests/test_e2e_workflow.py` walks one continuous scenario through the
real HTTP API - authentication, clinic isolation, therapist creation,
availability, patient creation, Excel import + duplicate detection,
appointment creation + conflict detection, travel-time calculation,
optimization + accept/reject, What-If evaluate/apply, analytics, and
audit logging - specifically to prove the pieces *compose* (e.g. a
patient who arrives via Excel import can be scheduled/optimized exactly
like a manually-created one), which the per-feature unit tests
elsewhere in the suite don't individually exercise. Routing/geocoding
are mocked throughout the whole suite - no test depends on live
OSRM/Nominatim.

---

## Environment Variables

See `.env.example` (root), `backend/.env.example`, and
`frontend/.env.example` for the full list. Key ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (backend) |
| `REDIS_URL` | Redis connection string (backend/Celery) |
| `JWT_SECRET_KEY` | Signing key for auth tokens *(set a real secret before any real use)* |
| `IMPORT_STORAGE_DIR` | Private, server-side directory for uploaded import files (default `var/imports/`) |
| `IMPORT_MAX_FILE_SIZE_BYTES` | Upload size cap for patient imports (default 10 MB) |
| `CELERY_TASK_ALWAYS_EAGER` | Dev/demo only - runs Celery tasks in-process without a worker/Redis. Never `true` in production |
| `NOMINATIM_BASE_URL` | Geocoding provider base URL (default the public Nominatim demo server) |
| `NOMINATIM_USER_AGENT` | Required by Nominatim's usage policy - identify your deployment before going to production |
| `OSRM_BASE_URL` | Routing provider base URL (default the public OSRM demo server) |
| `GEOCODE_CACHE_TTL_SECONDS` / `TRAVEL_TIME_CACHE_TTL_SECONDS` | Redis cache lifetimes for geocoding/travel-time results |
| `MAPS_MAX_MATRIX_POINTS` | Cap on points per `/maps/travel-time-matrix` request (default 25) |
| `OPTIMIZATION_MAX_SOLVE_SECONDS` | CP-SAT time limit per `DAY_SCHEDULE_OPTIMIZATION` solve (default 10s) |
| `OPTIMIZATION_GAP_WEIGHT` / `OPTIMIZATION_CHANGE_PENALTY_WEIGHT` | Soft-constraint weights, relative to 1.0 on drive-minutes |
| `OPTIMIZATION_DEFAULT_SEARCH_DAYS` | Default search window for `NEW_PATIENT_PLACEMENT` (default 14 days) |
| `OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY` | Solver problem-size cap per day (default 20) |
| `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` / `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | Login attempts per (IP, email) - default 5 / 15 min |
| `RATE_LIMIT_REGISTER_MAX_ATTEMPTS` / `..._WINDOW_SECONDS` | Registrations per IP - default 5 / 1 hour |
| `RATE_LIMIT_PASSWORD_RESET_MAX_ATTEMPTS` / `..._WINDOW_SECONDS` | Reset requests per (IP, email) - default 3 / 1 hour |
| `RATE_LIMIT_IMPORT_UPLOAD_MAX` / `RATE_LIMIT_OPTIMIZATION_MAX` / `RATE_LIMIT_GEOCODE_MAX` / `RATE_LIMIT_TRAVEL_MATRIX_MAX` (+ each `..._WINDOW_SECONDS`) | Per-user limits on expensive operations - see `app/core/config.py` for defaults |
| `MAX_REQUEST_BODY_BYTES` | Generic JSON request-body cap enforced by `MaxBodySizeMiddleware` (default 1 MB) |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` / `CELERY_TASK_TIME_LIMIT_SECONDS` | Backstop timeouts for optimization/import background jobs (default 300s/360s) |
| `NEXT_PUBLIC_API_BASE_URL` | Where the frontend expects the API - **not a secret**, it's shipped to every browser |

Production-only variables (`.env.production.example`) and the full
security/deployment picture live in
[`docs/14_Production_Deployment.md`](docs/14_Production_Deployment.md).

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
- **Docker dev hot-reload requires polling** (Phase 10 fix). On this
  project's Windows/Docker Desktop combination, neither `next dev`'s
  webpack watcher nor `uvicorn --reload`'s watchfiles watcher ever
  detected a host-side file edit through the bind mount by default -
  confirmed by editing a file and watching the container logs never show
  a recompile/reload, even though the container's view of the file
  content was already correctly up to date (a watch-mechanism problem,
  not a file-sync problem). `docker-compose.yml` now sets
  `WATCHFILES_FORCE_POLLING=true` (backend) and `WATCHPACK_POLLING=true`
  (frontend) to force polling-based watching, which reliably works
  across host OSes/file-sharing backends at the cost of a several-second
  detection delay instead of near-instant native events. If hot-reload
  ever seems to have stopped working again after a `docker compose up`,
  confirm both env vars actually reached the container
  (`docker exec routecare-backend env | grep WATCHFILES`) before
  assuming it's a code bug.
- **A dead session (expired/revoked refresh token) now redirects to
  `/login`** (Phase 10 fix) instead of leaving whatever page was open
  showing a generic "could not load" error with no way back short of a
  manual reload - see `lib/api.ts`'s `apiFetch`.
- **`app.services.routing`/`geocoding` now reuse a pooled `httpx.Client`**
  (Phase 9) instead of opening a fresh connection per call - previously
  a known limitation, now fixed; see the Production Hardening section.
- **Day-schedule optimization's patient-availability lookup is now
  batched** (Phase 10 perf fix) - `_compute_day_schedule_recommendation`
  used to query `PatientAvailability` once per appointment in a loop (a
  bounded but real N+1 on the optimizer's main hot path, up to
  `OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY` extra queries per run); it now
  fetches every involved patient's availability for the day in one
  query. Behavior is unchanged, only the query count.
- **The optimization recommendation card now shows "before" driving time
  explicitly** (Phase 10 UX fix), not just "after" and "time saved" -
  a user previously had to compute `after + saved` themselves to see
  what the schedule cost before the recommendation.
- **Weekly optimization is one therapist at a time.** There's no
  bulk/multi-therapist weekly job (Phase 7's task explicitly listed this
  as an existing limitation to leave alone, not fix) - a clinic-wide
  "optimize everyone's week" would mean either N separate requests from
  the frontend or a new orchestration layer above
  `WEEK_SCHEDULE_OPTIMIZATION`, neither built here.
- **Public Nominatim/OSRM demo servers, not a production-grade
  deployment.** Both have real usage limits (Nominatim in particular
  caps at roughly one request/second) - fine for development and this
  phase's scope, but a real production deployment should self-host both
  (docs/03_System_Architecture.md already calls for this) by pointing
  `NOMINATIM_BASE_URL`/`OSRM_BASE_URL` at private instances.
- **`patient_duplicates` (docs/04 section 15) is not implemented.** It's
  general cross-cutting duplicate tracking outside the import flow;
  import-scoped duplicate matches live on `import_rows` instead. Revisit
  if duplicate detection is ever needed outside of imports.
- **`.xls` support depends on `xlrd`, `.xlsx` on `openpyxl`** - both are
  already in `requirements.txt`. File type is picked by sniffing the
  actual bytes (never the extension), so an `.xls`-named file that's
  actually a `.xlsx` (or vice versa) is still parsed correctly.
- **Plain ASGI middleware, not `BaseHTTPMiddleware`.** `RequestContextMiddleware`/
  `SecurityHeadersMiddleware` are plain ASGI classes rather than
  Starlette's `BaseHTTPMiddleware` — the latter can run the wrapped app
  in a separate anyio task depending on Starlette version, which breaks
  the "set a contextvar deep inside the route, read it back after
  `call_next`" pattern request correlation relies on. See
  `app/core/middleware.py`'s docstring. This also means mypy's Starlette
  stubs flag them with a (harmless, `# type: ignore`d) structural typing
  mismatch in `app/main.py`.
- **Lint/format config** (`backend/pyproject.toml`, added Phase 1C).
  The whole backend tree is `black`-formatted as of Phase 4 (a handful
  of Phase 1A/1B files were left unformatted through Phase 3 to avoid
  unrelated churn; Phase 4's `black app tests alembic` run normalized
  everything).

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
- `14_Production_Deployment.md` — env vars, deployment requirements,
  security assumptions actually enforced (not just planned), migrations,
  backup/restore, health checks, operational troubleshooting (Phase 9/10)

## Core Principle

AI recommends. Humans decide. RouteCare AI never automatically changes a
schedule without explicit user approval — this rule applies to every
feature built on top of this foundation.