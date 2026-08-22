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
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.modules.auth.router import router as auth_router
from app.modules.patients.router import router as patients_router

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


# Remaining feature routers (scheduling, imports, optimization, ...) are
# included here as each module is implemented in later phases.
