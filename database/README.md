# Database

RouteCare AI uses **PostgreSQL 16 with PostGIS**, managed through
**SQLAlchemy** models and **Alembic** migrations.

## In Phase 0

- No models exist yet.
- `docker/postgres/init.sql` enables the `postgis` and `uuid-ossp`
  extensions automatically when the `postgres` container first starts.
- Alembic is configured (`backend/alembic/`) but has zero revisions —
  there's nothing to migrate against yet.

## What comes next (Phase 1 — Database Implementation)

Per `docs/04_Database_Design.md` and `docs/11_Claude_Development_Prompts.md`,
the following tables are introduced in later phases:

`clinics`, `users`, `therapists`, `therapist_availability`, `patients`,
`patient_availability`, `appointments`, `appointment_routes`,
`optimization_requests`, `optimization_recommendations`, `imports`,
`import_errors`, `patient_duplicates`, `audit_logs`.

Every business table will include `clinic_id` for multi-tenant isolation,
and most will include `created_at`/`updated_at` (and `deleted_at` for
soft-deletable entities), per the Database Design doc's conventions.