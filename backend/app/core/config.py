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

        if problems:
            raise ValueError("Insecure production configuration detected:\n- " + "\n- ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
