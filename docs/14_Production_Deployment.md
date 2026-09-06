# RouteCare AI
# Production Deployment & Operations Guide

Version: 1.0 (Phase 9)

Status: Draft

---

# 1. Scope

This document covers what's needed to run RouteCare AI in a real clinic
deployment: environment configuration, the production Docker images,
security assumptions actually enforced by the code (not just aspired to
in docs/09_Security_Privacy_Compliance.md), database migrations,
backup/restore, health checks, and common operational troubleshooting.

It does not cover infrastructure choice (which cloud, which Postgres
host) - those are deployment-specific decisions. It documents what the
application itself requires and enforces.

---

# 2. Production Environment Variables

Copy `.env.production.example` (repo root) to two files and fill in
real values - **never commit either**:

- `.env` - read by `docker-compose.prod.yml` itself for `${VAR}`
  substitution (image build args, port mappings).
- `.env.production` - passed into the `backend`/`worker` containers via
  `env_file:` (see docker-compose.prod.yml).

In practice both files can hold the same values; they're separated
because Compose variable substitution and a container's `env_file` are
two different mechanisms, not because the values differ.

| Variable | Required | Notes |
|---|---|---|
| `ENVIRONMENT` | Yes | Must be `production`. Triggers `Settings._validate_production_config` (app/core/config.py) - the app **refuses to start** if any check below fails. |
| `JWT_SECRET_KEY` | Yes | At least 32 characters, unique, never the dev default. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `DATABASE_URL` | Yes | Must not contain the dev password marker (`routecare_dev_password`). Use the `postgres` service name as host under Compose. |
| `CORS_ORIGINS` | Yes | Comma-separated real frontend origin(s). Must not be empty or contain `localhost`/`127.0.0.1` - the app refuses to start otherwise (Phase 9 hardening). |
| `REDIS_URL` | Yes | Backs Celery, response caching, and rate limiting (see §5). |
| `CELERY_TASK_ALWAYS_EAGER` | Must be unset/false | Startup validation refuses `true` in production - background jobs would block requests. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` / `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | No | Sensible defaults (30 min / 7 days / 60 min) already set in app/core/config.py. |
| `RATE_LIMIT_*` (12 settings) | No | Login/register/password-reset/import/optimization/geocode/travel-matrix limits - see app/core/config.py for defaults and app/core/rate_limiting.py for enforcement. Tune only if defaults prove wrong for your clinic's real traffic. |
| `MAX_REQUEST_BODY_BYTES` | No | Generic JSON body cap (default 1 MB) - see app/core/middleware.MaxBodySizeMiddleware. |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` / `CELERY_TASK_TIME_LIMIT_SECONDS` | No | Defaults 300s/360s - backstop against a hung optimization/import job. |
| `NEXT_PUBLIC_API_BASE_URL` | Yes (frontend) | Baked into the frontend build - **not a secret**, it's shipped to every browser. Never put a real secret in a `NEXT_PUBLIC_*` variable. |

Run the app once with your real `.env.production` before deploying -
`Settings()` raises a `ValidationError` immediately (at import time,
before any request is served) listing every problem found, so a
misconfigured production deploy fails loudly at boot rather than
silently running insecure.

---

# 3. Deployment Requirements

- Docker + Docker Compose v2, **or** the three services (Postgres 16 +
  PostGIS, Redis 7, and this app's own backend/worker/frontend images)
  run some other way - the compose file is a reference topology, not a
  requirement to use Compose specifically.
- PostgreSQL 16 with the PostGIS extension available (the `init.sql`
  under `docker/postgres/` enables it) - PostGIS itself isn't queried
  directly yet by application code, but the extension is provisioned
  for the geocoded lat/lng columns already in use.
- Outbound HTTPS access from the backend/worker containers to
  Nominatim (`NOMINATIM_BASE_URL`) and OSRM (`OSRM_BASE_URL`) - both
  default to the public demo servers; point them at a private instance
  for real production volume (the public Nominatim server enforces
  ~1 request/second, already respected by
  `app/services/geocoding.py`'s rate limiter).
- A TLS-terminating reverse proxy or load balancer in front of both the
  backend (port 8000) and frontend (port 3000) - this app does not
  terminate TLS itself and does not set `Strict-Transport-Security`
  (deliberately - see `app/core/middleware.py`'s docstring on why that
  header belongs at the TLS-terminating edge, not the app).

### Bringing the stack up

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker exec routecare-backend-prod alembic upgrade head
```

Migrations are **not** run automatically on container start - see §7.
The backend/frontend containers have Docker `HEALTHCHECK`s; wait for
`docker compose -f docker-compose.prod.yml ps` to show `healthy` before
routing real traffic.

### Running two environments on the same host

`docker-compose.prod.yml` is a fully standalone file (not an overlay
of the dev `docker-compose.yml`) with its own container names and
volume (`routecare_postgres_data`) - see that file's own header comment
for why. If a dev stack was ever brought up on the same Docker host
under the default project name, either use a distinct
`-p <project-name>` for one of them, or be aware they'll otherwise
collide on container names/volumes.

---

# 4. Security Assumptions Actually Enforced

These are the specific controls the code enforces today - not the
longer aspirational list in docs/09_Security_Privacy_Compliance.md.

- **Authentication**: bcrypt (12 rounds) password hashing; JWT access
  tokens (short-lived, `exp`/`iat`/`jti`/`type` claims, signature +
  expiry + type checked on every request); opaque, SHA-256-hashed
  refresh tokens with rotation on every use and **reuse-detection** -
  presenting an already-rotated-out refresh token revokes every active
  session for that user, on the assumption it was stolen. Login
  timing is equalized between "no such user" and "wrong password" to
  resist user enumeration.
- **Authorization**: every clinic-owned resource is scoped by
  `clinic_id` directly in the query (never "load then check"), and a
  cross-clinic ID 404s exactly like a nonexistent one - see
  `app/core/permissions.py` and every `*_service.py`'s `_not_found()`
  helper. THERAPIST-role users are additionally restricted to their
  own appointments/schedule via `restrict_to_therapist_id`, enforced
  server-side in the service layer, never just hidden in the UI.
- **Rate limiting** (`app/core/rate_limiting.py`, Redis-backed, fails
  open if Redis is unavailable): login/register/password-reset are
  limited per (IP, email); Excel import upload, optimization-request
  creation, explicit geocode, and travel-time-matrix calls are limited
  per authenticated user. Redis being briefly unavailable degrades to
  "not rate limited," never to "every request rejected" - bcrypt and
  correct-password-required remain the primary defense on login either way.
- **File upload**: content is sniffed by file signature (ZIP for
  `.xlsx`, OLE2 for `.xls`), never trusted by filename/extension/
  Content-Type alone; size is enforced by aborting a chunked read as
  soon as the limit is exceeded (never buffering an oversized upload
  into memory first); storage is a private, per-clinic,
  UUID-named path with no user-controlled path segments (no traversal
  surface); a stray temp file never survives a completed or a rejected
  upload (see tests/test_imports_file_cleanup.py).
- **Request size**: a generic `MAX_REQUEST_BODY_BYTES` (default 1 MB)
  cap applies to every JSON endpoint via `Content-Length` inspection,
  independent of the import endpoint's own larger, stream-enforced limit.
- **Audit logging** (`app/services/audit_service.py`, backed by the
  `audit_logs` table): login/logout/failed login, user creation and
  activation/deactivation, patient create/update/delete, appointment
  create/update/cancel, import confirmation, and optimization-
  recommendation acceptance are all recorded with `clinic_id` (tenant
  isolation) and the acting `user_id`. Values are deliberately minimal
  - patient field changes record which fields changed, never the PII
  values themselves; passwords/tokens/secrets are never logged anywhere
  (application logs or audit records).
- **Error handling**: every error response shares one JSON envelope;
  unhandled exceptions are logged in full server-side but return only
  a generic message to the client (no stack trace, no DB connection
  string, no filesystem path - see `app/core/exceptions.py` and
  `app/core/health.py`, which returns only the exception *class name*
  for infra failures, never `str(exc)`).
- **CORS**: restricted to `CORS_ORIGINS`; production startup refuses a
  `localhost`/empty value.
- **What this deployment does *not* provide** (by design, out of
  scope for this phase - see docs/09_Security_Privacy_Compliance.md
  §2 "Current Product Scope"): encryption-at-rest is the responsibility
  of the chosen Postgres/disk provider, not the application; there is
  no malware scanning of uploaded files yet (`scan_for_malware` is a
  documented, always-clean stub - wire a real scanner such as ClamAV
  before accepting uploads from untrusted external users); there is no
  HIPAA/BAA compliance program - the schema deliberately stores no
  clinical/medical data.

---

# 5. Database Migrations

Alembic migrations live in `backend/alembic/versions/`. They are
**never** run automatically by the container entrypoint - this is
deliberate: a migration should be a reviewed, deliberate operational
step, not something that silently fires on every container restart
(which would also make N replicas of the backend race to apply the
same migration on startup).

```bash
# Apply all pending migrations
docker exec routecare-backend-prod alembic upgrade head

# Check current version
docker exec routecare-backend-prod alembic current

# Roll back one migration (rare - most of this schema's migrations are additive)
docker exec routecare-backend-prod alembic downgrade -1
```

Procedure for a deploy that includes a schema change:
1. Deploy the new backend/worker image (old code still runs fine
   against the old schema).
2. Run `alembic upgrade head`.
3. Only then roll the frontend/traffic over to code paths that depend
   on the new schema, if any.

This order (migrate after deploying compatible code, before enabling
new features) avoids a window where new code expects a column/table
that doesn't exist yet.

---

# 6. Backup & Recovery

A practical, low-effort PostgreSQL backup strategy is sufficient for
this phase (per the task's explicit "do not implement an expensive
external backup platform") - `pg_dump`/`pg_restore` against the
`postgres` container, on a cron schedule.

### Backup

```bash
# Daily full logical backup (custom format - supports selective/parallel restore)
docker exec routecare-postgres-prod pg_dump -U routecare -d routecare_ai -F c -f /tmp/backup.dump
docker cp routecare-postgres-prod:/tmp/backup.dump ./backups/routecare_$(date +%Y%m%d_%H%M%S).dump
```

- **Frequency**: daily, at minimum. A clinic actively scheduling
  should back up more often (e.g. every 6 hours) if the tolerance for
  lost scheduling changes is low.
- **Retention**: keep daily backups for 30 days, weekly for 90 days -
  adjust to the clinic's own data-retention policy. Store backups
  somewhere other than the same host/disk as the database itself
  (object storage, a second host) - a backup that dies with the same
  disk as the database it's backing up isn't a backup.
- **What's covered**: the Postgres database only (all application
  data - clinics, users, patients, appointments, optimization history,
  audit logs). Uploaded import files (`IMPORT_STORAGE_DIR`, mounted at
  `backend/var/imports` in dev) are a separate on-disk store - include
  that path in your host/volume backup strategy too if the original
  uploaded Excel files need to survive a disk loss, per
  docs/09_Security_Privacy_Compliance.md's "retain the original as an
  audit copy" requirement.

### Restore

```bash
# Into an existing (empty) database
docker cp ./backups/routecare_20260901_020000.dump routecare-postgres-prod:/tmp/restore.dump
docker exec routecare-postgres-prod pg_restore -U routecare -d routecare_ai --clean --if-exists /tmp/restore.dump
```

`--clean --if-exists` drops existing objects before recreating them,
so this is safe to run against a database that already has (stale or
partial) schema in it - it doesn't require a pre-wiped database.

After restoring, run `alembic current` to confirm the restored
database's migration version matches what the running application
code expects; if the backup predates a later migration, run
`alembic upgrade head` before serving traffic.

### Recovery testing

Restore a recent backup into a scratch database on a schedule (e.g.
monthly) and confirm `alembic current` + a basic smoke test (login,
list patients) succeed - an untested backup is not a verified backup.

---

# 7. Health Checks

| Endpoint | Checks | Use |
|---|---|---|
| `GET /health/live` | Nothing - always returns 200 if the process is up | Liveness probe (container orchestrator restart decision) |
| `GET /health/ready` | Real Postgres + Redis connectivity | Readiness probe (whether to route traffic here) |
| `GET /health` / `GET /api/v1/health` | Basic "the app is running" | Manual smoke check |

Both `backend` and `frontend` services in `docker-compose.prod.yml`
have a Docker-level `HEALTHCHECK` wired to `/health/live` and `/`
respectively; `docker compose ps` and `docker inspect --format
'{{.State.Health.Status}}' routecare-backend-prod` both surface it. A
container stuck "unhealthy" past its `start_period` is a real signal
something is wrong (bad `DATABASE_URL`, Postgres unreachable, etc.) -
check `docker compose logs backend` next.

---

# 8. Operational Troubleshooting

**Backend container won't start, logs show a `ValidationError` from
`Settings`**: a production config problem (see §2/§4) - the error
message lists every specific check that failed. Fix `.env.production`
and re-create the container; nothing partial is running.

**`/health/ready` reports `{"database": {"ok": false}}`**: check
`DATABASE_URL` is correct and Postgres is reachable from the backend
container's network (`docker exec routecare-backend-prod python -c
"from app.database.session import engine; engine.connect()"` for a
direct check). The error field is always just the exception class name
(e.g. `OperationalError`) - it deliberately never includes the
connection string, so check the configured `DATABASE_URL` directly
rather than trying to read credentials out of an error message.

**A specific user is getting 429 "Too many requests"**: expected once
they exceed a configured rate limit (see §4) - either it's genuine
abuse, or a legitimate limit is too tight for real usage and one of the
`RATE_LIMIT_*` settings needs raising. Rate-limit state lives in Redis
under the `routecare:ratelimit:*` key prefix and expires on its own
after the configured window - `redis-cli --scan --pattern
'routecare:ratelimit:*'` lists active windows if you need to confirm
what's currently limited.

**Background jobs (import validation/execution, optimization) seem
stuck**: check `docker compose logs worker`. Every background task
function catches its own exceptions and marks the job/request `FAILED`
rather than leaving it `PROCESSING` forever (see
`app/services/import_service.py`/`app/services/optimization_service.py`);
a job still shown `PROCESSING` for longer than
`CELERY_TASK_TIME_LIMIT_SECONDS` (default 360s) means the worker
process itself was killed (OOM, crash) - check `docker compose ps
worker` for restarts and `docker compose logs worker` for the reason.

**Geocoding/routing looks broken (patients stuck `PENDING`/`FAILED`,
optimization can't compute)**: check outbound HTTPS access to
`NOMINATIM_BASE_URL`/`OSRM_BASE_URL` from the worker/backend
containers - both providers fail closed (return "no result" /
"unreachable"), not with an exception, so nothing crashes, but nothing
useful gets computed either. `docker exec routecare-backend-prod
python -c "import httpx; print(httpx.get('https://nominatim.openstreetmap.org').status_code)"`
is a quick manual check.

**Need to see what changed to a specific patient/appointment**: query
the `audit_logs` table filtered by `entity_id` (and `clinic_id` for
tenant isolation) - see §4. There is no admin UI for this yet (out of
scope for this phase); it's a direct SQL/DB-client query today.
