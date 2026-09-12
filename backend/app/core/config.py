"""
RouteCare AI - Application configuration.

Centralized settings loaded from environment variables. Every other
module should import `settings` from here rather than reading
os.environ directly, so configuration stays in one place.

The insecure-looking defaults below (JWT secret, DB password) are
intentional dev-only conveniences, not a security hole: _validate_production_config
below refuses to let the app start with ENVIRONMENT=production if any
of them are still in place, so a misconfigured production deploy fails
loudly at boot rather than silently running with a known secret.
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_SECRET = "change_this_to_a_long_random_secret"
_INSECURE_DB_PASSWORD_MARKER = "routecare_dev_password"
_MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # General
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "RouteCare AI"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://routecare:routecare_dev_password" "@localhost:5432/routecare_ai"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET_KEY: str = _INSECURE_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(default=60, gt=0)

    # CORS - comma-separated origins, e.g. "http://localhost:3000,https://app.routecare.ai"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Patient import (Phase 3)
    IMPORT_STORAGE_DIR: str = "var/imports"
    IMPORT_MAX_FILE_SIZE_BYTES: int = Field(default=10 * 1024 * 1024, gt=0)  # 10 MB

    # Celery - dev/demo convenience by default: runs tasks synchronously in-process instead of
    # dispatching to a worker via Redis. Refused in production (see _validate_production_config)
    # unless ALLOW_EAGER_TASKS_IN_PRODUCTION is also explicitly set - the one supported exception
    # is a worker-less free-tier deployment (e.g. Render's free tier has no free background-worker
    # service) that deliberately accepts synchronous optimization/import requests instead of paying
    # for a worker process. See docs/15_Free_Deployment.md section 2.
    CELERY_TASK_ALWAYS_EAGER: bool = False
    ALLOW_EAGER_TASKS_IN_PRODUCTION: bool = False
    # Backstop timeouts (Phase 9) - defense-in-depth against a hung network call or pathological
    # input occupying a worker forever; per-call HTTP timeouts (ROUTING_TIMEOUT_SECONDS etc.) are
    # the first line of defense and should trip long before these do. Soft raises
    # SoftTimeLimitExceeded inside the task (caught by the same broad except Exception every task's
    # service function already has, so the request/job ends up FAILED, never stuck); hard SIGKILLs
    # the worker process a bit later as a last resort if the soft signal is somehow swallowed.
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = Field(default=300, gt=0)
    CELERY_TASK_TIME_LIMIT_SECONDS: int = Field(default=360, gt=0)

    # Maps & travel-time (Phase 5). Public demo servers by default per
    # docs/03_System_Architecture.md section 9 (OpenStreetMap/Nominatim/OSRM) -
    # self-hostable later by pointing these at a private instance. Nominatim's
    # usage policy requires a real identifying User-Agent and caps the public
    # server at ~1 request/second; NOMINATIM_MIN_REQUEST_INTERVAL_SECONDS
    # enforces that regardless of which server is configured.
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_USER_AGENT: str = "RouteCareAI/1.0 (dev@routecare.ai)"
    NOMINATIM_MIN_REQUEST_INTERVAL_SECONDS: float = Field(default=1.1, gt=0)
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    GEOCODING_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    ROUTING_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    GEOCODE_CACHE_TTL_SECONDS: int = Field(default=60 * 60 * 24 * 30, gt=0)  # 30 days
    TRAVEL_TIME_CACHE_TTL_SECONDS: int = Field(default=60 * 60 * 24, gt=0)  # 24 hours
    MAPS_MAX_MATRIX_POINTS: int = Field(default=25, gt=1)

    # Schedule optimization (Phase 6). Weights are relative to a fixed 1.0 on
    # total drive-minutes, the task's explicit primary objective - see
    # app/services/optimization_engine.py's docstring for the full objective
    # function. Deliberately configurable rather than hardcoded, per the
    # task's explicit "do not hardcode business assumptions" instruction.
    OPTIMIZATION_GAP_WEIGHT: float = Field(default=0.1, ge=0)
    OPTIMIZATION_CHANGE_PENALTY_WEIGHT: float = Field(default=2.0, ge=0)
    OPTIMIZATION_MAX_SOLVE_SECONDS: float = Field(default=10.0, gt=0)
    OPTIMIZATION_DEFAULT_SEARCH_DAYS: int = Field(default=14, gt=0)
    OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY: int = Field(default=20, gt=1)

    # Rate limiting (Phase 9). Redis-backed fixed-window counters - see app/core/rate_limiting.py.
    # Login/register/password-reset limits are per (ip, email-or-ip) pair; the "expensive
    # operation" limits (import upload, optimization requests, geocode, travel-time matrix) are
    # per authenticated user, since those endpoints require auth already.
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = Field(default=5, gt=0)
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = Field(default=15 * 60, gt=0)
    RATE_LIMIT_PASSWORD_RESET_MAX_ATTEMPTS: int = Field(default=3, gt=0)
    RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS: int = Field(default=60 * 60, gt=0)
    RATE_LIMIT_REGISTER_MAX_ATTEMPTS: int = Field(default=5, gt=0)
    RATE_LIMIT_REGISTER_WINDOW_SECONDS: int = Field(default=60 * 60, gt=0)
    RATE_LIMIT_IMPORT_UPLOAD_MAX: int = Field(default=10, gt=0)
    RATE_LIMIT_IMPORT_UPLOAD_WINDOW_SECONDS: int = Field(default=60 * 60, gt=0)
    RATE_LIMIT_OPTIMIZATION_MAX: int = Field(default=30, gt=0)
    RATE_LIMIT_OPTIMIZATION_WINDOW_SECONDS: int = Field(default=60 * 60, gt=0)
    RATE_LIMIT_GEOCODE_MAX: int = Field(default=30, gt=0)
    RATE_LIMIT_GEOCODE_WINDOW_SECONDS: int = Field(default=60 * 60, gt=0)
    RATE_LIMIT_TRAVEL_MATRIX_MAX: int = Field(default=60, gt=0)
    RATE_LIMIT_TRAVEL_MATRIX_WINDOW_SECONDS: int = Field(default=60 * 60, gt=0)

    # Request body size cap (Phase 9), enforced by app.core.middleware.MaxBodySizeMiddleware for
    # every request except the import upload endpoint, which enforces its own larger
    # IMPORT_MAX_FILE_SIZE_BYTES limit directly against the multipart stream instead.
    MAX_REQUEST_BODY_BYTES: int = Field(default=1 * 1024 * 1024, gt=0)  # 1 MB - generous for JSON bodies

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_production_config(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        problems: list[str] = []
        if self.JWT_SECRET_KEY == _INSECURE_JWT_SECRET or len(self.JWT_SECRET_KEY) < _MIN_PRODUCTION_SECRET_LENGTH:
            problems.append(
                f"JWT_SECRET_KEY must be a unique secret of at least {_MIN_PRODUCTION_SECRET_LENGTH} "
                "characters in production."
            )
        if _INSECURE_DB_PASSWORD_MARKER in self.DATABASE_URL:
            problems.append("DATABASE_URL still contains the development default password.")
        if self.CELERY_TASK_ALWAYS_EAGER and not self.ALLOW_EAGER_TASKS_IN_PRODUCTION:
            problems.append(
                "CELERY_TASK_ALWAYS_EAGER must be false in production - background jobs would block requests. "
                "If this is a deliberate worker-less free-tier deployment, also set "
                "ALLOW_EAGER_TASKS_IN_PRODUCTION=true (see docs/15_Free_Deployment.md)."
            )
        insecure_origins = [o for o in self.cors_origins_list if "localhost" in o or "127.0.0.1" in o]
        if insecure_origins or not self.cors_origins_list:
            problems.append(
                "CORS_ORIGINS must be set to the real production frontend origin(s), not localhost/empty, in production."
            )

        if problems:
            raise ValueError("Insecure production configuration detected:\n- " + "\n- ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
