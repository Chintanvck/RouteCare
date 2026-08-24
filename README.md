# RouteCare AI

AI-powered scheduling and route optimization platform for home healthcare
providers (therapists, PTAs, nurses, and the agencies that employ them).

> **Status: Phase 5 — Maps & Travel-Time Engine.**
> Auth/RBAC (Phase 1B), shared backend infrastructure (Phase 1C), patient
> management (Phase 2), TheraOffice Excel import (Phase 3), and therapist
> management/scheduling (Phase 4) are in place. Patients and therapists
> can now be geocoded (Nominatim), driving distance/time between any two
> locations is available (OSRM, Redis-cached), and a map view shows
> patient/therapist locations with a travel-time calculator. AI schedule
> optimization and route ordering are still not built - this phase is
> the location/travel-time *foundation* the optimization engine will
> consume, not the engine itself. See
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
│   ├── cache.py             # generic Redis-backed JSON get/set with TTL - geocoding/travel-time cache
│   └── rate_limiting.py    # no-op extension points (no backend wired up yet)
├── database/                # SQLAlchemy engine, session, declarative Base, portable GUID type, pagination.paginate()
├── models/                  # ORM models: Clinic, User, RefreshToken, PasswordResetToken, AuditLog, Patient,
│                            # ImportJob, ImportRow, ImportRowError, Therapist, TherapistAvailability,
│                            # PatientAvailability, Appointment, mixins.py (GeocodingStatus lives on patient.py)
├── modules/
│   ├── auth/                 # register/login/logout/refresh/change-password/reset/me router
│   ├── patients/              # patient list/create/get/update/delete/geocode + patient availability router
│   ├── imports/                # upload/mapping/preview/errors/confirm router
│   ├── therapists/              # therapist list/create/get/update/geocode + weekly availability router
│   ├── scheduling/               # appointment list(calendar)/create/get/update/cancel + /validate router
│   └── maps/                      # /travel-time, /travel-time-matrix (read-only, all clinic roles)
├── schemas/                 # Pydantic request/response schemas; common.py has PaginationParams/PaginatedResponse
├── services/                # business logic: auth_service.py, patient_service.py, geocoding.py,
│                            # import_service.py, column_mapping.py, duplicate_detection.py,
│                            # file_validation.py, excel_parser.py, therapist_service.py,
│                            # availability_service.py, appointment_service.py, scheduling_validation.py,
│                            # routing.py, travel_time_service.py
└── workers/                 # Celery app + tasks.py (demo) + import_tasks.py (validate/execute)
```

Frontend layout:

```
frontend/
├── app/
│   ├── login/                 # sign-in page
│   ├── patients/               # list, new, and [id] (view/edit) pages
│   ├── imports/patients/        # the 5-step import wizard page
│   ├── therapists/               # list, new, and [id] (profile/edit + weekly availability) pages
│   ├── schedule/                 # day/week calendar, appointment create/edit/cancel
│   └── map/                       # patient/therapist location map + travel-time calculator
├── components/
│   ├── ui/                     # shadcn/ui primitives (button, input, table, alert-dialog, progress, ...)
│   ├── layout/                 # AppHeader (nav + logout)
│   ├── patients/                # PatientForm, shared by the new and edit flows
│   ├── imports/                 # ImportStepper, Upload/Mapping/Preview/Results step components
│   ├── therapists/               # TherapistForm, AvailabilityEditor
│   ├── scheduling/                # AppointmentForm (live conflict check via /validate), AppointmentCard
│   └── maps/                       # LocationCard (geocode status + action), MapView (Leaflet, dynamic-
│                                   # imported client-only), TravelTimeCalculator
├── lib/
│   ├── api.ts                  # fetch wrapper (JSON + multipart), standardized ApiError, 401 -> refresh -> retry
│   ├── auth.ts                  # localStorage token storage
│   └── use-require-auth.ts      # client-side route guard
└── types/                      # TS types mirroring backend/app/schemas/{patient,import_job,therapist,appointment,maps}.py
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
tables - travel-time results are cached in Redis, not persisted). All
target PostgreSQL:

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
- **Optimization/analytics modules are still empty placeholders** — auth,
  patients, imports, therapist management/scheduling (Phase 4), and
  maps/travel-time (Phase 5) are implemented so far.
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

## Core Principle

AI recommends. Humans decide. RouteCare AI never automatically changes a
schedule without explicit user approval — this rule applies to every
feature built on top of this foundation.