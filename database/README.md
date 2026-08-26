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

## As of Phase 5 (Maps & Travel-Time Engine)

- Migration `0005_add_geocoding_fields` adds `geocoding_status`
  (`PENDING`/`GEOCODED`/`FAILED`/`MANUAL`), `geocoded_at`, and
  `location_verified` to both `patients` and `therapists` - see
  `backend/app/models/patient.py`'s `GeocodingStatus` docstring for the
  full lifecycle. Existing rows that already had coordinates (from
  before this migration) are backfilled as `GEOCODED` +
  `location_verified=true`, treating pre-existing coordinates as
  trustworthy rather than re-geocoding out from under them.
- **Deliberately no new table for travel-time/route results.**
  `docs/04_Database_Design.md`'s `appointment_routes` (section 10) is
  appointment-scoped and belongs with route-order optimization (a later
  phase); this phase's travel times are generic point-to-point (patient
  <-> patient, patient <-> therapist, or raw coordinates), not tied to a
  specific appointment. They're cached in Redis with a TTL instead
  (`backend/app/services/travel_time_service.py`) - avoids unnecessary
  spatial complexity for data that's cheap to recompute and doesn't need
  audit history.
- **PostGIS remains unused** (as it has since Phase 1A) - `latitude`/
  `longitude` are still plain `NUMERIC(9,6)` columns, not a `geography`/
  `geometry` type. Nothing in this phase needs spatial queries (no
  "find patients within N miles" yet); PostGIS stays enabled at the
  database level (`docker/postgres/init.sql`) for whenever that's
  actually needed.

## As of Phase 6 (Schedule Optimization Engine)

- Migration `0006_create_optimization_tables` adds `optimization_requests`
  and `optimization_recommendations`, per `docs/04_Database_Design.md`
  sections 11-12 - extended with the fields the two optimization modes
  actually need. See `backend/app/models/optimization.py`'s docstring
  for the full list and reasoning; briefly:
  - `optimization_requests.mode` (`DAY_SCHEDULE_OPTIMIZATION` /
    `NEW_PATIENT_PLACEMENT`) - not in the design doc, but a request is
    meaningless without knowing which problem it solves.
  - `target_date`/`search_days`/`new_patient_id`/
    `new_appointment_duration_minutes` hold each mode's own inputs (all
    nullable - only one mode's fields apply to any given row).
  - `accepted_recommendation_id` lives on the *request*, not a status
    enum on each recommendation - and is a plain `UUID` column, **not a
    foreign key**, specifically to avoid a circular FK between the two
    tables (each would otherwise need to reference the other).
    Application code enforces it, not the database. **Superseded in
    Phase 7** - see below.
  - `optimization_recommendations.explanation`/`solver_status` are
    additions beyond the design doc's minimal column list - a
    recommendation with no human-readable explanation or way to tell
    `OPTIMAL`/`FEASIBLE`/`INFEASIBLE` apart isn't useful to a scheduler
    deciding whether to trust it.
- Indexed on `clinic_id` and `therapist_id` (`optimization_requests`) and
  `optimization_request_id` (`optimization_recommendations`), per the
  Database Design doc's indexing strategy (section 18: "Optimization:
  therapist_id, created_at").
- **`appointment_routes` (docs/04 section 10) is still not implemented.**
  It's appointment-scoped route/travel data; this phase's recommendation
  data instead stores proposed appointment times directly in
  `recommendation_data` (JSONB) and replays them through the existing
  `appointment_service.create_appointment`/`update_appointment` on
  accept - there's no need for a separate per-appointment route table
  when the accepted outcome is just an ordinary `Appointment` row.
  Revisit if a persistent, queryable "route history" becomes a real
  requirement.
- PostGIS remains unused, same as Phase 5 - the optimization engine
  consumes `app.services.travel_time_service`'s existing Redis-cached
  travel-time matrix rather than any spatial SQL.

## As of Phase 7 (Optimization Workflow, What-If & Weekly Mode)

Migration `0007_optimization_workflow_improvements` revisits both
compromises Phase 6 explicitly flagged for review:

- **`optimization_recommendations.marginal_drive_minutes`/
  `marginal_distance_miles` added (nullable).** Phase 6's
  `NEW_PATIENT_PLACEMENT` mode had overloaded `total_drive_minutes` to
  mean "marginal added travel" instead of "the day's total," unlike
  every other mode. Rather than a bare rename, Phase 7 fixed the
  semantics properly: `total_drive_minutes`/`total_distance_miles` now
  always mean the full day's total after applying the recommendation
  (baseline + marginal, computed via the existing
  `engine.fixed_order_metrics`), for every mode consistently; the new
  `marginal_*` columns hold `NEW_PATIENT_PLACEMENT`'s insertion-specific
  detail on top of that, and stay `NULL` for every other mode.
- **`optimization_requests.accepted_recommendation_id` dropped.**
  Rather than adding a real foreign key (the option Phase 7's task asked
  to evaluate), the field was removed entirely and acceptance state
  moved onto `optimization_recommendations` itself
  (`accepted_at`/`rejected_at`, both nullable `TIMESTAMPTZ`) - this
  doesn't just resolve the circular-FK question, it eliminates the need
  for a back-reference at all, and is also what `WEEK_SCHEDULE_OPTIMIZATION`
  requires structurally: each of a week's 7 recommendations must be
  acceptable independently, which a single slot on the request could
  never represent.
- **`optimization_recommendations.target_date` added (`NOT NULL`,
  backfilled from the parent request for pre-existing rows).** Every
  recommendation now carries its own date rather than inheriting the
  request's single `target_date` - required so `WEEK_SCHEDULE_OPTIMIZATION`'s
  7 per-day rows (one per weekday) are distinguishable at all, and
  incidentally makes `NEW_PATIENT_PLACEMENT`'s multi-day candidate
  slots clearer too.
- `optimization_mode`'s enum gains `WEEK_SCHEDULE_OPTIMIZATION` -
  `ALTER TYPE ... ADD VALUE`, safe inside a transaction on this
  project's PostgreSQL 16 as long as the new value isn't used in the
  same transaction (it isn't).
- No new tables. Weekly optimization reuses `optimization_requests`/
  `optimization_recommendations` unchanged in shape (just tagged with
  the new mode + per-row `target_date`) - per the task's explicit
  "orchestrate the existing model, don't duplicate it" instruction.

Every business table will include `clinic_id` for multi-tenant isolation,
and most will include `created_at`/`updated_at` (and `deleted_at` for
soft-deletable entities), per the Database Design doc's conventions.