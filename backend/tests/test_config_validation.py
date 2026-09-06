"""Tests for production configuration validation in app.core.config."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_development_defaults_are_accepted() -> None:
    settings = Settings(ENVIRONMENT="development")
    assert settings.JWT_SECRET_KEY == "change_this_to_a_long_random_secret"


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="change_this_to_a_long_random_secret",
            DATABASE_URL="postgresql+psycopg2://user:realpassword@prod-host:5432/routecare_ai",
        )


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="too-short",
            DATABASE_URL="postgresql+psycopg2://user:realpassword@prod-host:5432/routecare_ai",
        )


def test_production_rejects_default_database_password() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 40,
            DATABASE_URL="postgresql+psycopg2://routecare:routecare_dev_password@prod-host:5432/routecare_ai",
        )


def test_production_accepts_properly_configured_secrets() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="a" * 40,
        DATABASE_URL="postgresql+psycopg2://user:realpassword@prod-host:5432/routecare_ai",
        CORS_ORIGINS="https://app.routecare.ai",
    )
    assert settings.ENVIRONMENT == "production"


def test_production_rejects_localhost_cors_origin() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 40,
            DATABASE_URL="postgresql+psycopg2://user:realpassword@prod-host:5432/routecare_ai",
            CORS_ORIGINS="http://localhost:3000",
        )


def test_production_rejects_empty_cors_origins() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 40,
            DATABASE_URL="postgresql+psycopg2://user:realpassword@prod-host:5432/routecare_ai",
            CORS_ORIGINS="",
        )


def test_expiry_settings_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(ACCESS_TOKEN_EXPIRE_MINUTES=0)
