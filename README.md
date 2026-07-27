# RouteCare AI

AI-powered scheduling and route optimization platform for home healthcare
providers (therapists, PTAs, nurses, and the agencies that employ them).

> **Status: Phase 0 — Project Foundation.**
> This repo currently contains the runnable skeleton only: no auth, no
> patients, no scheduling, no optimization yet. See
> [`docs/10_Development_Roadmap.md`](docs/10_Development_Roadmap.md) for
> what's built in each subsequent phase.

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
├── main.py                # FastAPI app + health checks
├── core/                  # config, security (JWT/bcrypt), permissions (roles)
├── database/              # SQLAlchemy engine, session, declarative Base
├── models/                # ORM models (empty until Phase 1)
├── modules/               # one folder per feature: auth, clinics, users,
│                          # therapists, patients, imports, scheduling,
│                          # optimization, maps, analytics, audit
├── schemas/                # Pydantic request/response schemas
├── services/               # business logic
└── workers/                 # Celery tasks
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

No migrations exist yet — there are no models until Phase 1. Once models
are added under `backend/app/models/`, the usual flow is:

```bash
cd backend
alembic revision --autogenerate -m "add clinics and users tables"
alembic upgrade head
```

`backend/alembic/env.py` reads `DATABASE_URL` from the same settings object
the app uses, so migrations always target the same database as the running
API.

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
- **No models/business logic yet.** `app/models/`, `app/schemas/`, and
  all `app/modules/*` packages are intentionally empty placeholders —
  they're filled in starting with the Phase 1 prompts in
  `docs/11_Claude_Development_Prompts.md`.

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

## Core Principle

AI recommends. Humans decide. RouteCare AI never automatically changes a
schedule without explicit user approval — this rule applies to every
feature built on top of this foundation.