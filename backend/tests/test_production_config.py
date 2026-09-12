"""
RouteCare AI - `Settings._validate_production_config` regression coverage.

This validator has real consequences (the app refuses to start at all if it
raises) but had no direct test coverage before Phase 12 added
`ALLOW_EAGER_TASKS_IN_PRODUCTION` - a targeted exception to the "never
CELERY_TASK_ALWAYS_EAGER in production" rule for worker-less free-tier
deployments (Render's free tier has no free background-worker service; see
docs/15_Free_Deployment.md). These tests exist specifically to prove that
exception is narrow: it only silences the one problem it's meant to, every
other production safety check still fires, and the check is a no-op outside
ENVIRONMENT=production entirely.

Settings is constructed directly with explicit kwargs (bypassing any real
.env file / process environment) so these tests are hermetic regardless of
what's actually set in the shell running them.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_VALID_SECRET = "a" * 40
_VALID_DB_URL = "postgresql+psycopg2://postgres:reallysecurepassword@db.supabase.co:5432/postgres"


def _base_kwargs(**overrides) -> dict:
    defaults = dict(
        ENVIRONMENT="production",
        JWT_SECRET_KEY=_VALID_SECRET,
        DATABASE_URL=_VALID_DB_URL,
        CORS_ORIGINS="https://app.example.com",
        CELERY_TASK_ALWAYS_EAGER=False,
    )
    defaults.update(overrides)
    return defaults


def test_valid_production_config_does_not_raise() -> None:
    Settings(**_base_kwargs())


def test_development_environment_skips_all_checks() -> None:
    """None of these values would pass in production - development must never validate them."""
    Settings(
        ENVIRONMENT="development",
        JWT_SECRET_KEY="change_this_to_a_long_random_secret",
        DATABASE_URL="postgresql+psycopg2://routecare:routecare_dev_password@localhost:5432/routecare_ai",
        CORS_ORIGINS="",
        CELERY_TASK_ALWAYS_EAGER=True,
    )


def test_insecure_jwt_secret_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(**_base_kwargs(JWT_SECRET_KEY="change_this_to_a_long_random_secret"))


def test_short_jwt_secret_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(**_base_kwargs(JWT_SECRET_KEY="too-short"))


def test_dev_database_password_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            **_base_kwargs(
                DATABASE_URL="postgresql+psycopg2://routecare:routecare_dev_password@db.supabase.co:5432/postgres"
            )
        )


def test_empty_cors_origins_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**_base_kwargs(CORS_ORIGINS=""))


def test_localhost_cors_origin_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**_base_kwargs(CORS_ORIGINS="http://localhost:3000"))


# ============================================================
# CELERY_TASK_ALWAYS_EAGER / ALLOW_EAGER_TASKS_IN_PRODUCTION (Phase 12)
# ============================================================


def test_eager_tasks_rejected_in_production_by_default() -> None:
    """The normal-production assumption (a real worker exists) still holds by default."""
    with pytest.raises(ValidationError, match="CELERY_TASK_ALWAYS_EAGER"):
        Settings(**_base_kwargs(CELERY_TASK_ALWAYS_EAGER=True))


def test_eager_tasks_allowed_in_production_with_explicit_opt_in() -> None:
    """The Phase 12 free-tier exception: both flags together must succeed."""
    Settings(**_base_kwargs(CELERY_TASK_ALWAYS_EAGER=True, ALLOW_EAGER_TASKS_IN_PRODUCTION=True))


def test_opt_in_alone_without_eager_flag_is_a_no_op() -> None:
    """Setting the opt-in without actually enabling eager mode changes nothing - it doesn't
    relax any other check or become some kind of general production bypass."""
    Settings(**_base_kwargs(CELERY_TASK_ALWAYS_EAGER=False, ALLOW_EAGER_TASKS_IN_PRODUCTION=True))


def test_opt_in_does_not_relax_other_production_checks() -> None:
    """ALLOW_EAGER_TASKS_IN_PRODUCTION must not become a general "skip validation" switch - an
    insecure JWT secret must still be rejected even when it's set."""
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            **_base_kwargs(
                JWT_SECRET_KEY="too-short",
                CELERY_TASK_ALWAYS_EAGER=True,
                ALLOW_EAGER_TASKS_IN_PRODUCTION=True,
            )
        )
