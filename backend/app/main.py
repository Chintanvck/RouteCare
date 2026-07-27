"""
RouteCare AI - FastAPI application entrypoint.

Phase 0 scope: application boots, exposes health checks, and CORS is
configured. Feature routers (auth, patients, scheduling, optimization,
etc.) are registered here starting in later phases as each module is
implemented.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="AI-powered scheduling and route optimization for home healthcare providers.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Basic liveness check for the API process itself."""
    return {"status": "ok", "service": settings.PROJECT_NAME, "environment": settings.ENVIRONMENT}


@app.get(f"{settings.API_V1_PREFIX}/health", tags=["health"])
def health_check_v1() -> dict[str, str]:
    """Versioned health check, matching the /api/v1 prefix used by all future routers."""
    return {"status": "ok"}


# Feature routers are included here as modules are implemented, e.g.:
# from app.modules.auth.router import router as auth_router
# app.include_router(auth_router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])