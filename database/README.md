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

## As of Phase 3 (TheraOffice Excel Import)

- Migration `0003_create_import_tables` adds `imports` (docs/04 section
  13) and `import_errors` (section 14), plus `import_rows` - not in the
  design doc, but necessary: the wizard's mapping-review/preview steps
  need to page through every row of the uploaded file, not just the
  failing ones `import_errors` covers. See
  `backend/app/models/import_row.py` docstring.
- `imports` carries a few columns beyond the doc's minimal list, needed
  for the wizard to persist state across separate HTTP requests:
  `stored_file_path` (private, server-side only), `detected_headers`/
  `column_mapping` (JSON), `processed_records` (live progress counter).
- **Not implemented**: `patient_duplicates` (docs/04 section 15). That
  table is general cross-cutting duplicate tracking outside the import
  flow; import-scoped duplicate matches live on `import_rows` instead
  (`duplicate_patient_id`/`duplicate_of_row_number`/`duplicate_confidence`).
  Revisit if duplicate detection is ever needed outside of imports.
- The import pipeline never updates or deletes an existing `Patient` row
  - only ever creates new ones. Duplicates are detected and reported,
  never auto-merged.

## As of Phase 4 (Therapist Management & Scheduling)

- Migration `0004_create_scheduling_tables` adds `therapists`,
  `therapist_availability`, `patient_availability`, and `appointments`,
  per `docs/04_Database_Design.md`. Indexed on `clinic_id` (`therapists`,
  `appointments`), `therapist_id` (`therapist_availability`), `patient_id`
  (`patient_availability`), and composite `(therapist_id, scheduled_date)`
  / `(patient_id, scheduled_date)` on `appointments`, per the Database
  Design doc's indexing strategy (section 18).
- `therapists.user_id` is unique (1:1 with `users`) - `Therapist` has no
  own login/email/name columns; those live on the linked `User` row and
  are exposed via computed properties (`first_name`, `email`,
  `is_active`, ...) so creating/editing a therapist never risks a
  duplicate `User`. See `backend/app/models/therapist.py` docstring.
- `therapist_availability`/`patient_availability` model **recurring
  weekly** rules only (`day_of_week` 0=Monday..6=Sunday, no date-specific
  overrides) - intentionally simpler than a general recurring-calendar
  schema, per this phase's scope. A day with no rows is a day off for a
  therapist, or "available anytime" for a patient (rows only add
  constraints, they never relax the flexible default).
- `appointments.scheduled_date`/`start_time`/`end_time` are naive
  DATE/TIME columns (clinic-local wall-clock time), not `TIMESTAMPTZ` -
  every scheduling query is already scoped to one clinic, so there's no
  cross-timezone ambiguity in this system's current usage pattern. See
  `backend/app/models/appointment.py` docstring for the full reasoning.
- Cancelling an appointment is a status transition
  (`status = CANCELLED`), never a row delete - `appointments` has no
  `deleted_at`/soft-delete mixin because the status enum already covers
  that need (`SCHEDULED`/`COMPLETED`/`CANCELLED`/`NO_SHOW`).
- No clinical notes field was added to `appointments` - not in
  `docs/04_Database_Design.md`, and out of scope per this phase's task.

## What comes next (Phase 5+)

Per `docs/04_Database_Design.md` and `docs/11_Claude_Development_Prompts.md`,
the following tables are introduced in later phases:

`appointment_routes`, `optimization_requests`, `optimization_recommendations`.

Every business table will include `clinic_id` for multi-tenant isolation,
and most will include `created_at`/`updated_at` (and `deleted_at` for
soft-deletable entities), per the Database Design doc's conventions.