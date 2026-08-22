# Database

RouteCare AI uses **PostgreSQL 16 with PostGIS**, managed through
**SQLAlchemy** models and **Alembic** migrations.

## As of Phase 1B (Authentication & RBAC)

- `docker/postgres/init.sql` enables the `postgis` and `uuid-ossp`
  extensions automatically when the `postgres` container first starts.
- Migration `0001_create_auth_tables` (`backend/alembic/versions/`)
  creates `clinics`, `users`, `refresh_tokens`, `password_reset_tokens`,
  and `audit_logs`. `refresh_tokens` and `password_reset_tokens` aren't
  in `docs/04_Database_Design.md` - they were added because Phase 1B's
  JWT requirements need server-side, revocable, rotatable refresh
  tokens, which the original design doc predates.
- Two deliberate deviations from `docs/04_Database_Design.md`, both
  required for authentication to work correctly (see
  `backend/app/models/user.py` docstring): `users.email` is globally
  unique rather than "unique per clinic" (login takes no clinic
  selector), and `users.clinic_id` is nullable (`SYSTEM_ADMIN` is
  platform-level and not scoped to a clinic).

## As of Phase 2 (Patient Management)

- Migration `0002_create_patients_table` adds `patients`, per
  `docs/04_Database_Design.md` section 7 - scheduling-related
  information only, not a clinical record system. Uses
  `app.models.mixins.TimestampMixin`/`SoftDeleteMixin` (added in Phase
  1C, first used here) for `created_at`/`updated_at`/`deleted_at` rather
  than redeclaring those columns by hand.
- Unlike `users.clinic_id` (nullable), `patients.clinic_id` is required
  - every patient belongs to exactly one clinic, no platform-level
    equivalent to `SYSTEM_ADMIN` exists for patient records.
- Indexed on `clinic_id` and `zip_code` per the Database Design doc's
  indexing strategy (section 18).

## What comes next (Phase 3+)

Per `docs/04_Database_Design.md` and `docs/11_Claude_Development_Prompts.md`,
the following tables are introduced in later phases:

`therapists`, `therapist_availability`, `patient_availability`,
`appointments`, `appointment_routes`, `optimization_requests`,
`optimization_recommendations`, `imports`, `import_errors`,
`patient_duplicates`.

Every business table will include `clinic_id` for multi-tenant isolation,
and most will include `created_at`/`updated_at` (and `deleted_at` for
soft-deletable entities), per the Database Design doc's conventions.