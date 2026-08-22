# RouteCare AI
# Coding Standards

Version: 1.0

Status: Draft

Written after Phase 1C (Shared Backend Infrastructure). These are
working conventions, not a style-guide-for-its-own-sake - most of them
exist because Phase 1B/1C code already follows them, and the point of
writing them down is so Phase 2+ doesn't have to re-derive the same
decisions from reading source.

---

# 1. Python Naming Conventions

- Modules/files: `snake_case.py` (`auth_service.py`, `request_context.py`).
- Classes: `PascalCase` (`RefreshToken`, `NotFoundError`, `PaginationParams`).
- Functions/variables: `snake_case` (`hash_password`, `raw_refresh_token`).
- Constants: `UPPER_SNAKE_CASE`, module-level (`DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE`).
- Private/internal helpers: prefix with `_` (`_now`, `_aware_utc`, `_log_audit`) -
  signals "implementation detail of this module, don't import it elsewhere."
- Pydantic schemas: suffix by role, not by "Schema" - `RegisterRequest`,
  `TokenResponse`, `UserPublic`. `...Public` specifically means "the
  subset of a model safe to return to a client" (never includes
  `password_hash`, `token_hash`, etc.).
- SQLAlchemy models: singular noun, matching the table's singular
  concept (`User`, not `Users`); `__tablename__` is the plural
  snake_case form (`"users"`).

---

# 2. TypeScript Naming Conventions

(No TypeScript business logic exists yet beyond the Phase 0 scaffold -
these are the conventions to follow once frontend work starts.)

- Components: `PascalCase.tsx` (`PatientCard.tsx`), one component per file.
- Hooks: `camelCase` prefixed `use` (`useAuth.ts`, `useDebounce.ts`).
- Non-component modules: `camelCase.ts` (`apiClient.ts`) or `kebab-case.ts`
  for multi-word utility files - pick one per directory and stay consistent
  within it; don't mix within the same folder.
- Types/interfaces: `PascalCase`, no `I`/`T` prefix (`User`, not `IUser`).
- Constants: `UPPER_SNAKE_CASE` for true constants, `camelCase` for
  config objects.

---

# 3. API Naming Conventions

- Resource-oriented REST paths, plural nouns: `GET /patients`,
  `POST /patients`, `GET /patients/{id}`, `PUT /patients/{id}`,
  `DELETE /patients/{id}` (soft delete - see docs/04_Database_Design.md 1.2).
- Actions that don't fit CRUD are verbs on a sub-path, not new HTTP
  methods: `POST /optimization/{id}/accept`, `POST /auth/reset-password`.
- Query params for list endpoints: `page`, `page_size`, `search`, and
  filter fields as their own params (`?zip_code=07030`), not a generic
  `?filter=` blob. See section 6.
- Every route lives under `settings.API_V1_PREFIX` (`/api/v1`), registered
  in `app/main.py` with an explicit `tags=[...]` matching the module name.
- Error codes (the `error.code` field) are `UPPER_SNAKE_CASE` and, where
  meaningful, domain-prefixed: `PATIENT_NOT_FOUND`, `EMAIL_ALREADY_EXISTS`,
  not just `NOT_FOUND`/`CONFLICT` - the generic default is a fallback for
  when there's genuinely no more specific concept.

---

# 4. Database Naming Conventions

Per docs/04_Database_Design.md, already followed by every table:

- Table names: plural snake_case (`clinics`, `users`, `refresh_tokens`).
- Columns: snake_case; `id` (UUID PK), `<other_table_singular>_id` for FKs
  (`clinic_id`, `user_id`).
- Every clinic-owned table has `clinic_id` (multi-tenant isolation - see
  section 8).
- Timestamps: `created_at`, `updated_at` on every table; `deleted_at`
  (nullable) on soft-deletable ones. New models should use
  `app.models.mixins.TimestampMixin`/`SoftDeleteMixin` rather than
  redeclaring these columns by hand.
- Indexes: `ix_<table>_<column>`; unique constraints via `unique=True`
  on the column or an explicit `UniqueConstraint` for composite keys.
- Enums stored as native Postgres enums, named `<column>_<table-ish>`
  (e.g. `user_role`), backed by a Python `str, Enum` class as the single
  source of truth (`app.core.permissions.UserRole`).

---

# 5. Error Handling Conventions

- Never raise a bare `HTTPException` from route/service code. Raise one
  of the typed exceptions in `app.core.exceptions`:
  `NotFoundError`, `UnauthorizedError`, `ForbiddenError`, `ConflictError`,
  `ValidationError`, `BusinessRuleError` (or the `AppError` base for a
  genuinely one-off status code). Each has a sensible default status +
  code; override `code=` with a domain-specific one whenever a client
  might reasonably branch on it (`PATIENT_NOT_FOUND`, not `NOT_FOUND`).
- Every error response is `{"success": false, "error": {"code",
  "message", "details"}, "request_id"}` - this is produced automatically
  by the handlers in `app.core.exceptions`, never assembled by hand in a
  route.
- **Success responses are not wrapped** in a matching `{"success": true,
  "data": ...}` envelope - return the resource/Pydantic model directly.
  This was a deliberate Phase 1C decision: a universal wrapper fights
  FastAPI's `response_model` typing and makes the OpenAPI schema show
  `data: object` instead of the real shape. List endpoints get their
  structure from `PaginatedResponse` instead (see section 6), which
  serves the same "consistent shape" goal without the generic wrapper.
  `request_id` is always available via the `X-Request-ID` response
  header regardless of whether the body is wrapped.
- Never let a raw exception (DB error, unexpected `AttributeError`, ...)
  reach the client. `app.core.exceptions`' catch-all `Exception` handler
  is a last resort - if you find yourself relying on it, add a specific
  typed exception instead so the error code is meaningful to the caller.
  Health checks follow the same rule: `app.core.health` returns
  `type(exc).__name__`, never `str(exc)`, since driver exception
  messages often embed the connection string.

---

# 6. Filtering, Sorting, and Pagination Conventions

**Pagination** is standardized: use `app.schemas.common.PaginationParams`
as a dependency and `app.database.pagination.paginate()` to slice a
query, and return `PaginatedResponse[YourItemSchema]`:

```python
@router.get("/patients", response_model=PaginatedResponse[PatientPublic])
def list_patients(
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
):
    query = db.query(Patient).filter(Patient.clinic_id == clinic_id, Patient.deleted_at.is_(None))
    items, total = paginate(query, pagination)
    return PaginatedResponse.create(items, page=pagination.page, page_size=pagination.page_size, total=total)
```

**Filtering and sorting are deliberately NOT a generic abstraction.**
Add typed, explicit query parameters per endpoint instead of a generic
`filters: dict` or a query-string DSL - a reader should be able to see
every supported filter by looking at the function signature:

```python
@router.get("/patients", response_model=PaginatedResponse[PatientPublic])
def list_patients(
    search: str | None = Query(None, description="Matches against patient name"),
    zip_code: str | None = Query(None),
    sort_by: Literal["name", "created_at"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
):
    query = db.query(Patient).filter(Patient.clinic_id == clinic_id, Patient.deleted_at.is_(None))
    if search:
        query = query.filter(Patient.name.ilike(f"%{search}%"))
    if zip_code:
        query = query.filter(Patient.zip_code == zip_code)
    column = getattr(Patient, sort_by)
    query = query.order_by(column.desc() if sort_order == "desc" else column.asc())
    items, total = paginate(query, pagination)
    return PaginatedResponse.create(items, page=pagination.page, page_size=pagination.page_size, total=total)
```

Apply this same shape to `GET /appointments`, `GET /therapists`, etc.
`sort_by` as a `Literal` of the actually-sortable columns (not an
arbitrary string) prevents both SQL injection via column name and a
500 from `getattr` on a nonexistent attribute.

---

# 7. Database Query Pattern Conventions

- **Tenant isolation is explicit, always.** Every query against a
  clinic-owned table filters on `clinic_id` by hand:
  `.filter(Patient.clinic_id == clinic_id)`. RouteCare does **not** use
  SQLAlchemy's automatic global-filter mechanisms (e.g.
  `with_loader_criteria`) - implicit, app-wide query rewriting is easy
  to get subtly wrong and hard to audit; an explicit filter on every
  query is easy to grep for and easy to unit test in isolation (see
  `tests/test_rbac_tenant_isolation.py`).
- **`clinic_id` never comes from the request body/query string** for a
  write - it comes from `get_current_clinic_id()`. A future `POST
  /patients` must set `patient.clinic_id = current_clinic_id` from the
  dependency, never trust a `clinic_id` field the client sent (that
  would let one clinic write into another's data by just changing a
  JSON field).
- **Soft delete**: default list/get queries filter
  `.filter(Model.deleted_at.is_(None))`; `DELETE /resource/{id}` sets
  `deleted_at = now()` rather than issuing a SQL `DELETE`.
- **Avoid N+1s**: when a list endpoint's response includes a
  relationship (e.g. patients with their assigned therapist name), load
  it eagerly with `.options(joinedload(Patient.therapist))` (one-to-one/
  many-to-one) or `.options(selectinload(...))` (one-to-many/collections)
  rather than accessing `.therapist` per row and letting SQLAlchemy
  lazy-load once per item.
- **Bulk operations** (e.g. marking many appointments as imported): use
  `Session.bulk_update_mappings`/a single `UPDATE ... WHERE` (like
  `_revoke_all_refresh_tokens` in `auth_service.py`), not a Python loop
  calling `.commit()` per row.
- No generic repository layer. Query logic lives in the domain service
  (`app/services/<module>_service.py`), reading like normal SQLAlchemy -
  a repository abstraction over an already-thin ORM layer just adds a
  layer of indirection with no real benefit at this codebase's size.

---

# 8. Authentication & Tenant-Isolation Rules

- Every protected route depends on `get_current_user` (directly or via
  `require_role(...)`). Never re-implement JWT decoding in a route.
- Endpoints scoped to "the caller's clinic" depend on
  `get_current_clinic_id` - it 403s automatically for a `SYSTEM_ADMIN`
  with no clinic context, so routes don't need their own null-check.
- Endpoints that load a specific resource by ID call
  `require_clinic_access(current_user, resource.clinic_id)` immediately
  after the load, before doing anything else with it:

  ```python
  patient = db.get(Patient, patient_id)
  if patient is None:
      raise NotFoundError("Patient was not found.", code="PATIENT_NOT_FOUND")
  require_clinic_access(current_user, patient.clinic_id)
  ```

  `SYSTEM_ADMIN` deliberately bypasses this check (platform
  support/administration access) - every other role must match exactly.
- Role checks use `require_role(*roles)`, never an inline
  `if current_user.role != "X"` scattered in route bodies.
- **Authorization is server-side only.** The frontend hiding a button is
  a UX nicety, not a security control - assume every request can be
  replayed with different IDs/roles by hand, and enforce accordingly.

---

# 9. Logging Conventions

- Three loggers: `routecare.auth` (security events), `routecare.access`
  (one line per HTTP request, emitted by `RequestContextMiddleware`),
  `routecare.app` (everything else). Get a module-specific child logger
  with `logging.getLogger("routecare.<module>")` for new domains rather
  than reusing `routecare.app` for everything.
- All logs are structured JSON (`app.core.logging_config.JSONLogFormatter`).
  Pass structured fields via `extra={...}`, never string-interpolate
  them into the message: `logger.info("patient_created", extra={"patient_id": str(patient.id)})`,
  not `logger.info(f"Created patient {patient.id}")`.
- `request_id`/`user_id`/`clinic_id` are attached automatically by
  `RequestContextFilter` - don't pass them manually unless logging
  outside a request context (e.g. a Celery task, where you'd pass them
  explicitly since there's no ambient HTTP request).
- **Never log**: passwords, JWT access tokens, refresh tokens, password
  reset tokens, full request bodies, or patient PII/PHI. Log identifiers
  (`user_id`, `patient_id`) and outcomes, not payloads.

---

# 10. Testing Conventions

- Tests run against SQLite in-memory (`tests/conftest.py`), not a real
  Postgres - this keeps the suite fast and dependency-free. Models use
  `app.database.types.GUID` and `JSON().with_variant(JSONB(), "postgresql")`
  specifically so this works; new models should follow the same pattern
  rather than using `postgresql.UUID`/`postgresql.JSONB` directly.
- One test file per endpoint group (`test_auth_login.py`,
  `test_auth_refresh_logout.py`, ...), not one giant file per module.
- For infrastructure that has no real endpoint to exercise it through
  yet (RBAC dependencies before any business router exists), build a
  small throwaway `FastAPI()` probe app in the test file itself (see
  `test_rbac_tenant_isolation.py`, `test_error_handling.py`) rather than
  adding scaffolding routes to the real app just for tests.
- Test both the happy path and the specific failure modes that matter
  security-wise: wrong password vs. unknown email returning identical
  errors, expired/revoked tokens, cross-tenant access, page_size caps.
- Readiness/external-infra tests monkeypatch the check functions
  (`app.core.health.check_database`/`check_redis`) rather than requiring
  a real Postgres/Redis to be reachable from the test environment.

---

# 11. Import Organization

Standard library, then third-party, then local (`app.*`), each group
alphabetized, one blank line between groups - this is what every file
in the codebase already does and what `ruff`/`isort` enforce by default:

```python
import uuid
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
```

Avoid `import *`. Prefer `from app.core import health` (module import)
over `from app.core.health import check_database` when a test or caller
needs to monkeypatch the function later - patching a name that was
imported with `from x import y` only rebinds the local copy, not the
one other code sees (see `app/main.py`'s use of `health.check_database()`).

---

# 12. Service/Module Structure

Established by `app/modules/auth/` + `app/services/auth_service.py` -
follow the same split for every future module:

- `app/modules/<name>/router.py` - HTTP layer only: parses the request
  (via Pydantic), calls a service function, shapes the response. No
  business logic, no direct SQLAlchemy queries.
- `app/services/<name>_service.py` - business logic, database queries,
  logging, audit entries. Plain functions taking a `Session` and
  explicit arguments (not a `Request`) - keeps it testable without
  spinning up FastAPI.
- `app/models/<name>.py` - one SQLAlchemy model per file (small
  exception: tightly-coupled auth token tables could share a file, but
  we didn't even do that - `refresh_token.py`/`password_reset_token.py`
  are separate).
- `app/schemas/<name>.py` - Pydantic request/response schemas for that
  module. `app/schemas/common.py` is for cross-module shared shapes only
  (pagination) - don't put module-specific schemas there.
- Shared, cross-cutting code (auth dependencies, exceptions, logging,
  middleware, health, pagination, model mixins) lives in `app/core/`,
  `app/database/`, or top-level `app/schemas/common.py` /
  `app/models/mixins.py` - never duplicated per module.

---

# 13. When to Create a Reusable Component

Create shared infrastructure when a pattern is used (or clearly about
to be used) by **more than one module** and the abstraction doesn't
hide anything a reader needs to see to understand a specific call site.
Everything built in Phase 1C fits this: every future list endpoint
needs pagination; every future protected/tenant-scoped endpoint needs
the same three auth dependencies; every future table needs
timestamps/soft-delete; every response needs the same error shape.

# 14. When NOT to Create an Abstraction

- A generic filter/query-builder DSL - explicit per-endpoint query
  params are more readable and type-safe than a `filters: dict[str, Any]`
  that hides what's actually queryable (see section 6).
- A generic repository class wrapping SQLAlchemy - the ORM is already
  the abstraction; a repository on top of it just relocates the query
  without simplifying it (see section 7).
- A base "CRUD service" class that every module inherits - domain logic
  (validation rules, side effects like revoking tokens on password
  change) doesn't fit a generic template and ends up overridden into
  meaninglessness.
- Wrapping every success response in `{"success": true, "data": ...}` -
  see section 5.
- Any third-party dependency for something ~10 lines of stdlib/existing-
  library code already solves (e.g. no rate-limiting library was added
  in Phase 1C - see `app/core/rate_limiting.py`'s documented no-op
  extension points instead).

---

# 15. Git Commit Conventions

- Imperative mood, present tense: "Add refresh token rotation", not
  "Added" or "Adds".
- Prefix with the phase or module when it disambiguates a small repo
  history (`Phase 1C: add request ID middleware`) - not required for
  every commit once the codebase is bigger and commits are naturally
  scoped to one module.
- Body explains **why**, not what (the diff already shows what) -
  e.g. "bcrypt>=4.1 broke passlib's version probe" is a useful commit
  body; "changed hash_password to use bcrypt directly" is not (the diff
  says that already).
- Don't bundle unrelated changes (a dependency bump and a new feature)
  into one commit.

---

# 16. Security Rules for Developers

- Never commit `.env` files or real secrets - `.gitignore` already
  excludes `.env`; `.env.example` files hold placeholder values only.
- Never hardcode a secret as a Python default that could plausibly ship
  to production unnoticed - `app.core.config.Settings` fails startup if
  `ENVIRONMENT=production` and `JWT_SECRET_KEY`/`DATABASE_URL` still
  hold their insecure dev defaults. Any new secret-like setting should
  get the same treatment.
- Never accept `clinic_id`, `user_id`, or `role` from client-supplied
  request data for authorization purposes - these always come from the
  verified JWT via `get_current_user`/`get_current_clinic_id`.
- Never log or return a password, JWT, refresh token, or reset token in
  any response body or log line, including error messages.
- Hash passwords with `app.core.security.hash_password` (bcrypt); hash
  opaque tokens (refresh, password reset) with `hash_token` (SHA-256) -
  they're different because bcrypt is for low-entropy human-chosen
  secrets, and its 72-byte input limit would silently mis-hash a longer
  opaque token.
- Any new raw SQL (rare - the ORM covers almost everything) must use
  bound parameters (`text("...").bindparams(...)` or
  `session.execute(text("..."), {...})`), never an f-string/`.format()`
  building the query.
- When adding a new list endpoint, always cap `page_size` via
  `PaginationParams` - never accept an unbounded `limit` from the client.
