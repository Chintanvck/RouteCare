"""
RouteCare AI - FastAPI application entrypoint.

Phase 1C scope: shared backend infrastructure (error handling, request
correlation, structured logging, health/readiness, security headers) is
wired in on top of Phase 1B's auth. Remaining feature routers (patients,
scheduling, optimization, etc.) are registered here starting in later
phases as each module is implemented.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import health
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.middleware import MaxBodySizeMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.imports.router import router as imports_router
from app.modules.maps.router import router as maps_router
from app.modules.optimization.router import router as optimization_router
from app.modules.patients.router import router as patients_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.therapists.router import router as therapists_router

configure_logging()

tags_metadata = [
    {
        "name": "health",
        "description": "Liveness/readiness probes for orchestration and monitoring. "
        "Liveness never touches the database; readiness does.",
    },
    {
        "name": "auth",
        "description": "Registration, login, logout, token refresh, password management, and the "
        "current-user endpoint. Protected endpoints require `Authorization: Bearer <access_token>`.",
    },
    {
        "name": "patients",
        "description": "Clinic patient records (scheduling-related information only - not a clinical "
        "record system). Scoped to the authenticated user's clinic; read access for all clinic roles, "
        "create/update/delete restricted to clinic admins and office schedulers.",
    },
    {
        "name": "imports",
        "description": "Bulk patient import from TheraOffice (or similar) Excel exports: upload, column "
        "mapping, validation/duplicate preview, and confirmed import. Restricted to clinic admins and "
        "office schedulers. Large files are validated and imported in the background - poll "
        "`GET /imports/{id}` for progress.",
    },
    {
        "name": "therapists",
        "description": "Therapist profiles (a User with role=THERAPIST, plus a profile row) and their "
        "recurring weekly availability. Read access for all clinic roles; create/update restricted to "
        "clinic admins and office schedulers.",
    },
    {
        "name": "scheduling",
        "description": "Appointments and calendar views. Clinic admins/schedulers manage any appointment; "
        "therapists see and lightly manage only their own. `GET /appointments?start_date=&end_date=` "
        "serves both day and week calendar views. `POST /appointments/validate` is a dry run of the same "
        "validation create/update use, for pre-submit feedback and drag-and-drop-style moves.",
    },
    {
        "name": "maps",
        "description": "Driving distance/time between two locations (patients, therapists, or raw "
        "coordinates) and small travel-time matrices, backed by OSRM with Redis caching. Read-only for "
        "every clinic role. Geocoding a specific patient/therapist stays on their own routers "
        "(`POST /patients/{id}/geocode`, `POST /therapists/{id}/geocode`).",
    },
    {
        "name": "optimization",
        "description": "AI-recommended schedule changes (OR-Tools CP-SAT day re-ordering, and new-"
        "patient slot placement) and a stateless What-If evaluator. The optimizer only ever "
        "recommends - nothing is applied to the calendar until `POST .../accept`, which re-validates "
        "every hard constraint before touching an appointment. Available to every clinic role; "
        "therapists are restricted to their own schedule.",
    },
    {
        "name": "analytics",
        "description": "Operational analytics/efficiency dashboard: appointment volume, driving time/"
        "distance, therapist utilization, schedule efficiency, and the impact of *accepted* "
        "optimization recommendations only. Every metric is server-computed and clinic-scoped; "
        "therapists see only their own data.",
    },
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.2.0",
    description=(
        "AI-powered scheduling and route optimization for home healthcare providers. "
        "All error responses share one envelope: "
        '`{"success": false, "error": {"code", "message", "details"}, "request_id"}`. '
        "Every response also carries an `X-Request-ID` header for correlating with server logs."
    ),
    openapi_tags=tags_metadata,
)

# Registered outermost-first: CORS is added first so it sits innermost
# among these three, closest to routing; SecurityHeaders and
# RequestContext wrap it so their headers/logging apply to every
# response, including ones CORSMiddleware itself short-circuits.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Import upload is exempted - it enforces its own larger, streaming-checked
# IMPORT_MAX_FILE_SIZE_BYTES limit directly (see app.modules.imports.router._read_bounded).
app.add_middleware(
    MaxBodySizeMiddleware,  # type: ignore[arg-type]
    max_bytes=settings.MAX_REQUEST_BODY_BYTES,
    exempt_path_prefixes=(f"{settings.API_V1_PREFIX}/imports",),
)
# mypy's Starlette stubs expect middleware constructors to match a
# specific ParamSpec-based protocol that plain ASGI classes (as opposed
# to BaseHTTPMiddleware subclasses) don't structurally satisfy, even
# though they work correctly at runtime - see app.core.middleware's
# docstring for why plain ASGI classes are used here on purpose.
app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]
app.add_middleware(RequestContextMiddleware)  # type: ignore[arg-type]

register_exception_handlers(app)

app.include_router(auth_router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])
app.include_router(patients_router, prefix=f"{settings.API_V1_PREFIX}/patients", tags=["patients"])
app.include_router(imports_router, prefix=f"{settings.API_V1_PREFIX}/imports", tags=["imports"])
app.include_router(therapists_router, prefix=f"{settings.API_V1_PREFIX}/therapists", tags=["therapists"])
app.include_router(scheduling_router, prefix=f"{settings.API_V1_PREFIX}/appointments", tags=["scheduling"])
app.include_router(maps_router, prefix=f"{settings.API_V1_PREFIX}/maps", tags=["maps"])
app.include_router(optimization_router, prefix=f"{settings.API_V1_PREFIX}/optimization", tags=["optimization"])
app.include_router(analytics_router, prefix=f"{settings.API_V1_PREFIX}/analytics", tags=["analytics"])


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Basic liveness check for the API process itself."""
    return {"status": "ok", "service": settings.PROJECT_NAME, "environment": settings.ENVIRONMENT}


@app.get(f"{settings.API_V1_PREFIX}/health", tags=["health"])
def health_check_v1() -> dict[str, str]:
    """Versioned health check, matching the /api/v1 prefix used by all future routers."""
    return {"status": "ok"}


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Is the process running? No dependency checks - must stay fast and always succeed if the app is up."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness() -> JSONResponse:
    """Can this instance actually serve traffic? Checks PostgreSQL and Redis connectivity."""
    db_ok, db_error = health.check_database()
    redis_ok, redis_error = health.check_redis()
    ready = db_ok and redis_ok

    checks: dict[str, dict[str, object]] = {"database": {"ok": db_ok}, "redis": {"ok": redis_ok}}
    if db_error:
        checks["database"]["error"] = db_error
    if redis_error:
        checks["redis"]["error"] = redis_error

    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "unavailable", "checks": checks},
    )
