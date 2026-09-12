# RouteCare AI
# Free-Tier MVP Deployment Guide

Version: 1.0 (Phase 12)

Status: Draft

> Numbering note: `docs/12_MVP_Launch_Strategy.md` already existed, so this
> guide is `15_` (after `14_Production_Deployment.md`) rather than `12_`.
> `docs/14_Production_Deployment.md` documents a different path -
> self-hosted via `docker-compose.prod.yml` with your own Postgres/Redis
> containers. This document is the **$0/month managed-services** path:
> Cloudflare + Render Free + Supabase + Upstash. Pick one path; both
> read the same application code and the same environment variable names.

---

## 1. Scope

Get the existing app running on the public internet at $0/month:

| Layer | Service | Tier |
|---|---|---|
| Frontend | Cloudflare | Free |
| Backend | Render Web Service | Free |
| Database | Supabase PostgreSQL | Free |
| Redis | Upstash Redis | Free |
| Source | GitHub | Free |

No product features, database schema, or algorithms change in this phase.
Local Docker development (`docker-compose.yml`) is untouched and keeps
working exactly as before.

---

## 2. The one architecture compromise: no background worker

`docker-compose.yml`/`docker-compose.prod.yml` run a separate `worker`
container (`celery -A app.workers.celery_app worker`) that processes
optimization requests and Excel imports asynchronously. **Render's free
tier has no free Background Worker service** - that product tier starts
at ~$7/month.

Fix used here, via a setting that already existed in `app/core/config.py`
and was already fully wired through `app/workers/*_tasks.py`:

```
CELERY_TASK_ALWAYS_EAGER=true
ALLOW_EAGER_TASKS_IN_PRODUCTION=true
```

This makes every `.delay()` call run synchronously, in-process, the
moment it's called - optimization requests and import processing happen
inside the same HTTP request instead of being handed to a worker that
doesn't exist on the free tier.

**One real code change was required here** (not zero, as originally
assumed): `Settings._validate_production_config` already refused to boot
with `ENVIRONMENT=production` + `CELERY_TASK_ALWAYS_EAGER=true` - a
pre-existing safety net written for the normal "production always has a
real worker" assumption, which this free-tier path deliberately breaks.
`ALLOW_EAGER_TASKS_IN_PRODUCTION` is a new, narrow, explicit opt-in added
specifically for this: setting it is the only way past that one specific
check, and it relaxes nothing else - every other production check (JWT
secret strength, dev DB password marker, CORS origin) still fires
regardless. See `backend/tests/test_production_config.py` for the
regression coverage proving both halves of that.

**Tradeoffs to accept, in writing:**
- An optimization request now blocks until the solver finishes (bounded
  by `OPTIMIZATION_MAX_SOLVE_SECONDS`, default 10s) instead of returning
  `PENDING` immediately. Render's free web service has a request timeout
  well above this, so it fits - but it's a real UX difference from local
  dev's async behavior.
- Import row-validation/execution similarly runs synchronously on
  upload/confirm.
- **Do not set this in a real production deployment with a paid worker.**
  It exists specifically for this free-tier constraint;
  `docs/14_Production_Deployment.md`'s path must keep it `false`/unset
  (`Settings._validate_production_config` already refuses `true` in that
  path's normal production validation - see the note in §6 below on how
  this interacts with that check).

---

## 3. GitHub setup

1. Create an empty repository (no README/license, so `git push` doesn't
   conflict with local history): `github.com/new`.
2. From the repo root:
   ```
   git remote add origin https://github.com/<you>/routecare-ai.git
   git branch -M main
   git push -u origin main
   ```
3. Both Cloudflare and Render connect directly to this repo and
   redeploy automatically on every push to `main` (configured in §4/§5).

---

## 4. Cloudflare setup (frontend)

**This section was corrected after actually going through it.** Cloudflare
has consolidated Pages into its Workers platform - creating a new
Git-connected project today lands you in the Workers Builds flow (Build
command / Deploy command / Version command fields, no "Framework preset"
dropdown), not the older classic Pages UI this doc originally assumed.
That flow deploys via Wrangler, which needs a real config in the repo -
added as part of this phase:

- `frontend/wrangler.jsonc` - Worker name, entry point
  (`.open-next/worker.js`), and the static-assets binding.
- `frontend/open-next.config.ts` - minimal OpenNext config, no R2
  incremental cache (an optional feature needing its own R2 bucket - not
  set up, out of scope for this MVP).
- `@opennextjs/cloudflare` + `wrangler` added as devDependencies.
  **Pinned to `@opennextjs/cloudflare@1.15.1`** - newer versions (`1.16.0+`)
  dropped Next.js 14 support entirely (require `next@>=15.5`), and
  upgrading Next.js itself is out of scope for a deployment phase. `1.15.1`
  is the last version whose peer range includes this app's exact
  `next@14.2.35`. **Do not bump this dependency without also planning a
  Next.js major-version upgrade.**

This was verified locally end-to-end during this phase: `npm run cf:build`
(added to `frontend/package.json`, wraps `opennextjs-cloudflare build`)
ran `next build` and then OpenNext's Cloudflare bundler, producing
`.open-next/worker.js` and `.open-next/assets/` exactly as
`wrangler.jsonc` expects - not just assumed to work.

Cloudflare dashboard setup:

1. **Workers & Pages** → **Create** → connect the GitHub repo (already
   done if you're reading this after hitting a failed first build with
   `Build command: None` / `Deploy command: npx wrangler deploy`).
2. **Root directory**: `frontend` (this is a monorepo - frontend and
   backend live side by side; the default `/` is wrong).
3. **Build command**: `npm run cf:build`
4. **Deploy command**: `npx wrangler deploy` (the default is already
   correct - it was only failing because `wrangler.jsonc` didn't exist
   yet and the root directory was wrong).
5. **Version command**: leave the default (`npx wrangler versions upload`)
   - unused unless you turn on gradual rollouts, harmless either way.
6. **Variables and secrets** (build-time), Production environment:
   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://<your-render-service>.onrender.com/api/v1` |

   This is not a secret - `NEXT_PUBLIC_*` variables are baked into the JS
   bundle and shipped to every browser (see `frontend/lib/api.ts`). It
   must be set *before* triggering the build that needs it - Next.js
   inlines it at build time, not runtime.
7. Retry/trigger the build. Cloudflare gives you a `*.<project>.workers.dev`
   URL; add a custom domain later if you want one - no code change needed
   either way.

**Why an adapter at all, not a plain static export**: `app/patients/
[id]/page.tsx` and `app/therapists/[id]/page.tsx` are genuinely dynamic
routes (arbitrary UUIDs, not known at build time). A plain `next export`
requires every dynamic route to be pre-rendered via `generateStaticParams`,
which doesn't fit this data. The OpenNext adapter runs Next.js's own
server logic inside a Worker instead, so these routes work unmodified.

---

## 5. Render setup (backend)

1. Render dashboard → **New** → **Web Service** → connect the same GitHub
   repo.
2. Settings:
   - **Root directory**: `backend`
   - **Runtime**: Docker
   - **Dockerfile path**: `backend/Dockerfile.prod`
   - **Instance type**: Free
3. Render injects its own `PORT` env var; `Dockerfile.prod`'s `CMD` now
   reads `${PORT}` (previously hardcoded to 8000 - fixed as part of this
   phase, see §12).
4. **Environment variables** (Render dashboard → Environment): see the
   full table in §6.
5. Deploy. Render gives you a `https://<name>.onrender.com` URL.

**Free-tier spin-down**: Render free web services spin down after ~15
minutes with no traffic and take 30-60s to cold-start on the next
request. Document this for users/demos - the first request after idle
will be slow. There is no free way around this (Render's paid tiers keep
an instance always warm).

---

## 6. Supabase setup (PostgreSQL)

1. `supabase.com` → New project. Note the database password you set (you
   need it for the connection string - Supabase doesn't show it again).
   Use a plain alphanumeric password - a literal `%` in it breaks
   Alembic's `configparser`-based config loading regardless of URL-
   encoding (found and worked around during this phase's actual
   deployment; not worth the surprise later).
2. Use the **Session pooler** connection string, not the direct
   connection. Project → **Connect** (or Settings → Database) →
   **Session pooler** tab → copy the URI. **This was verified the hard
   way during this phase**: Supabase's direct connection
   (`db.<ref>.supabase.co:5432`) is IPv6-only, and it failed with
   `Network is unreachable` from this project's own Docker environment -
   getting IPv4 to the direct connection requires Supabase's paid IPv4
   add-on. The session pooler is IPv4-reachable and free, and (unlike
   the *transaction* pooler on port 6543) behaves like a normal
   per-client connection, so it doesn't hit SQLAlchemy/psycopg2's
   prepared-statement caveats with PgBouncer transaction-mode pooling.
   It looks like:
   ```
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
3. Convert the scheme for SQLAlchemy + psycopg2 (the app uses
   `psycopg2-binary`, not `asyncpg`) - same host/port/credentials,
   just `postgresql+psycopg2://` instead of `postgresql://`:
   ```
   postgresql+psycopg2://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
4. (Optional, matches the local Docker topology's `docker/postgres/
   init.sql` - not currently queried by any migration or app code, so
   this is a parity step, not a hard requirement) In Supabase's SQL
   Editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   ```
5. Run migrations - see §9.

**No second schema design**: this runs the exact same
`backend/alembic/versions/*` migration chain used locally. Supabase ends
up with the identical table/enum/index/constraint set as your dev
database, just hosted differently.

---

## 7. Upstash setup (Redis)

1. `upstash.com` → **Create Database** → Redis, Regional (Free tier: 10k
   commands/day, 256MB - fine for rate limiting + geocode/travel-time
   caching at MVP traffic).
2. Database → **Details** tab → copy the **Redis URL** (the `rediss://`
   TLS one, not the REST API URL - the app uses the `redis` Python
   client directly against the standard Redis protocol, see
   `app/core/health.py`'s `redis.from_url(settings.REDIS_URL)`).
3. Set as `REDIS_URL` in Render's environment variables (§6/§8's table).

**What breaks without Redis, what doesn't**: rate limiting
(`app/core/rate_limiting.py`) and geocode/travel-time response caching
depend on it and degrade to "no limiting"/"no caching" if it's
unreachable, not a hard crash - this was already true before this phase
(Phase 9 hardening). With `CELERY_TASK_ALWAYS_EAGER=true` (§2), Redis is
no longer needed as a Celery broker at all for the free-tier path - it's
only used for rate limiting and caching now. Still required; just not
for the reason it originally was.

---

## 8. Required environment variables (Render)

Set these directly in Render's dashboard - **never** commit them to Git.
`backend/.env.example` and root `.env.example`/`.env.production.example`
remain placeholder-only, for local dev and the self-hosted path
respectively.

| Variable | Value for this deployment | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | Triggers `Settings._validate_production_config`. |
| `DATABASE_URL` | `postgresql+psycopg2://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres` | Session pooler, not direct connection - from Supabase §6. |
| `REDIS_URL` | `rediss://default:<password>@<host>:<port>` | From Upstash §7. |
| `JWT_SECRET_KEY` | Output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` | Must be ≥32 chars and not the dev default - enforced at boot. |
| `CORS_ORIGINS` | `https://<your-worker>.<subdomain>.workers.dev` | Comma-separate if you add a custom domain later, e.g. `https://app.example.com,https://<worker>.<subdomain>.workers.dev`. Must not contain `localhost`/be empty - enforced at boot. |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | See §2. Free-tier-specific; do not set in the self-hosted-with-worker path. |
| `ALLOW_EAGER_TASKS_IN_PRODUCTION` | `true` | Required alongside the above or the app refuses to boot (§2). Do not set in the self-hosted-with-worker path either. |
| `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | Defaults from `app/core/config.py` are fine | Only set if you want non-default values. |
| `RATE_LIMIT_*` (12 settings), `MAX_REQUEST_BODY_BYTES`, `OSRM_BASE_URL`, `NOMINATIM_*` | Defaults are fine | See `app/core/config.py` for the full list. |

And on Cloudflare (§4):

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://<your-render-service>.onrender.com/api/v1` |

---

## 9. Running migrations against Supabase

From `backend/`, with `DATABASE_URL` pointed at Supabase (export it
locally for one command, or run this from a machine/CI step that has
it set - **do not** run this as part of every Render deploy, see §11):

```bash
cd backend
DATABASE_URL="postgresql+psycopg2://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres" \
  alembic upgrade head
```

`backend/alembic/env.py` reads `DATABASE_URL` from `Settings`, the same
object the app itself uses - there is no separate migration-only config
to keep in sync.

This was actually run against this project's real Supabase instance
during this phase (`alembic upgrade head` through revision `0007`,
confirmed via `alembic current` → `0007 (head)`), not just described:
16 application tables, all 9 app-defined enums (`appointment_status`,
`user_role`, `geocoding_status`, etc. - a fresh Supabase project also
provisions ~12 of its own `auth`/`storage`-schema enums; harmless, not
ours, don't be alarmed if `\dT+` shows more than 9), 40 indexes, and 271
constraints, then a real write → read-back → delete round trip through
the actual `Clinic` SQLAlchemy model to confirm the app - not just
`psql` - can use this database.

**Verify** (via Supabase's SQL Editor or `psql`):
```sql
\dt                                    -- all expected tables exist
\dT+                                   -- enums (appointment_status, geocoding_status, etc.)
select conname from pg_constraint;     -- constraints
select indexname from pg_indexes;      -- indexes
```
Or simply run the backend test suite against a scratch Supabase branch/
project first if you want a fuller functional check before pointing
production at it.

**Never run against production**: `alembic downgrade`, `DROP DATABASE`,
`DROP SCHEMA`, or any destructive reset. If a migration needs reverting,
write a new forward migration - the same rule as any other environment,
just with real consequences now.

---

## 10. CORS configuration

Already implemented correctly before this phase (`app/main.py` uses
`allow_origins=settings.cors_origins_list`, never `["*"]`, and
`Settings._validate_production_config` refuses to boot with an empty or
localhost-containing `CORS_ORIGINS` when `ENVIRONMENT=production`). The
only deployment-specific step is setting `CORS_ORIGINS` to the real
Cloudflare origin (§8's table) - no code change was needed here.

Keep `http://localhost:3000` in `CORS_ORIGINS` **only** for local dev
(`backend/.env.example`'s default) - never in the Render production
value.

---

## 11. How to redeploy

Both Cloudflare and Render are connected directly to the GitHub
repo (§4/§5) - a normal `git push origin main` redeploys both
automatically. Neither runs Alembic migrations automatically; that stays
a deliberate, manual, one-off command (§9) specifically so a deploy can
never accidentally run a destructive or unreviewed migration against
production. Run `alembic upgrade head` yourself, once, after a push that
includes new migrations - before or after the redeploy completes, order
doesn't matter unless the migration is a breaking schema change the new
code depends on, in which case: migrate first.

---

## 12. Checking application health

```bash
curl https://<your-render-service>.onrender.com/health
curl https://<your-render-service>.onrender.com/api/v1/health
curl https://<your-render-service>.onrender.com/health/ready   # checks DB + Redis connectivity
```
All three already existed before this phase (`app/main.py`). `/health/
ready` returns 503 with which of `database`/`redis` failed if either is
unreachable - check this first if something's wrong post-deploy.

Frontend: open the Cloudflare URL directly; a working load with no
console errors and a working login is the practical health check (no
separate frontend health endpoint exists or is needed for a static/edge
site).

---

## 13. Free-tier limitations (document, don't silently work around)

- **No background worker** - optimization/imports run synchronously
  (§2). Under real concurrent load this will feel slow; fine for MVP/demo
  traffic.
- **Render cold starts** - ~30-60s first-request delay after 15 min
  idle (§5).
- **Import files are not persisted** - `IMPORT_STORAGE_DIR` (`var/
  imports/`, see `app/services/import_service.py`) writes to the
  container's local disk, which Render free instances don't persist
  across restarts/redeploys. With `CELERY_TASK_ALWAYS_EAGER=true`, a file
  is written and immediately re-read within the same request in the
  common case, so this mostly only bites if the container restarts
  mid-import (a Render redeploy or an OOM kill landing exactly then).
  Fixing this properly means object storage (e.g. Cloudflare R2's free
  tier, or S3) - explicitly out of scope for this phase per the task's
  "do not introduce a new paid service" / "do not redesign" constraints.
  **Documented limitation, not fixed**: don't rely on an import surviving
  a Render restart mid-upload; re-upload if one ever does.
- **OSRM public demo server** (`OSRM_BASE_URL=https://
  router.project-osrm.org`, unchanged) - shared, rate-limited, no uptime
  SLA. Same limitation Phase 9 already documented in
  `docs/14_Production_Deployment.md` §3; not redesigned here. For real
  usage volume, point `OSRM_BASE_URL` at a self-hosted OSRM instance
  later - no code change needed, it's already just a config value.
- **Upstash free tier**: 10k commands/day, 256MB. Rate-limiting and
  geocode/travel-time caching both hit Redis per relevant request: watch
  for this ceiling if the demo gets real traffic.
- **Supabase free tier**: project pauses after 7 days with zero traffic
  (auto-resumes on the next request, with a delay) and has a 500MB
  database cap - both non-issues at MVP scale.
- **Single Render instance, no autoscaling** - by design, at $0/month.

---

## 14. Moving to paid infrastructure later

Every step below is a config change, not a code or schema change:

| Limitation | Paid fix |
|---|---|
| No background worker | Render Background Worker (~$7/mo) + set `CELERY_TASK_ALWAYS_EAGER=false`/unset, re-enable the `worker` process from `docker-compose.prod.yml`'s command. |
| Render cold starts | Render's paid web service tier (always-on). |
| Import files not persisted | Point `IMPORT_STORAGE_DIR`-writing code at S3/R2 instead of local disk (a real code change, not just config - out of scope here). |
| OSRM public server limits | Self-host OSRM (`OSRM_BASE_URL` → your instance). |
| Upstash 10k/day ceiling | Upstash paid tier, or self-hosted Redis. |
| Supabase free caps | Supabase paid tier (no pause, higher storage/compute). |

---

## 15. Security checklist (verify before calling this done)

- [ ] No `.env`/secrets committed to Git (`git ls-files | grep -i env`
      should only show `.example` files).
- [ ] `JWT_SECRET_KEY` on Render is unique, ≥32 chars, not the dev default.
- [ ] `DATABASE_URL`/`REDIS_URL` values only live in Render's/Cloudflare's
      dashboards, never in a commit, PR, or log line.
- [ ] `CORS_ORIGINS` is the real Cloudflare origin only - not `*`,
      not localhost.
- [ ] `ENVIRONMENT=production` is set (this alone activates the startup
      validation above).
- [ ] Login/RBAC/tenant-isolation still enforced - see §16's manual test
      list; nothing in this phase touches `app/core/permissions.py` or
      any service's authorization logic.
- [ ] Debug/reload disabled - `Dockerfile.prod` never passes `--reload`;
      confirmed unchanged in §12's Dockerfile fix.

This deployment is **not** HIPAA compliant. Nothing in this phase changes
that; see `docs/09_Security_Privacy_Compliance.md` for what would still
be required (BAAs with every vendor here, encryption-at-rest guarantees,
audit log retention policy, etc.) before handling real patient data.

---

## 16. Manual production workflow test

Run this against the real deployed URLs after §4-§9 are all live:

1. Open the Cloudflare URL.
2. Log in as a seeded therapist.
3. Confirm the header shows the logged-in user's name/role (UserMenu).
4. Open the dashboard - confirm the therapist view (not the clinic-wide
   admin view) renders.
5. Confirm "Today's schedule" loads.
6. Open "New Appointment", search for a patient by name (tests the
   `for_scheduling` search endpoint end-to-end against Supabase).
7. Create the appointment (confirms the auto-assigned-therapist create
   flow works against production DB + Redis-backed rate limiting).
8. Confirm the new appointment appears in the schedule/dashboard.
9. Run "Optimize my day" - with `CELERY_TASK_ALWAYS_EAGER=true` this
   should complete inline within the request (no polling needed) and
   show a recommendation.
10. Click "Navigate" on an appointment card - confirms `buildNavigationUrl`
    opens Google Maps with the right destination.
11. Mark the appointment Completed or No-Show.
12. Log out, then log back in - confirms JWT/refresh-token issuance
    survives a real cross-origin (Cloudflare ↔ Render) round trip, not
    just same-origin local dev.
13. Separately, log in as a CLINIC_ADMIN and confirm clinic-wide access;
    log in as a second therapist and confirm they cannot see the first
    therapist's schedule/patients (cross-tenant/cross-therapist isolation
    - unchanged by this phase, worth re-confirming against the real
    production database once).

Do not consider deployment "done" until this list has actually been run
against the live URLs, not just asserted from reading the code.
