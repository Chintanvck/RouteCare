"""Tests for the centralized exception classes and standardized error envelope."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
    register_exception_handlers,
)


def _probe_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    def not_found():
        raise NotFoundError("Patient was not found.", code="PATIENT_NOT_FOUND")

    @app.get("/unauthorized")
    def unauthorized():
        raise UnauthorizedError("Not authenticated.")

    @app.get("/forbidden")
    def forbidden():
        raise ForbiddenError("Nope.")

    @app.get("/conflict")
    def conflict():
        raise ConflictError("Already exists.", code="EMAIL_ALREADY_EXISTS")

    @app.get("/validation")
    def validation():
        raise ValidationError("Bad field.", details={"field": "email"})

    @app.get("/business-rule")
    def business_rule():
        raise BusinessRuleError("Token expired.")

    @app.get("/boom")
    def boom():
        raise RuntimeError("raw database connection string leaked: postgres://user:pass@host/db")

    return app


client = TestClient(_probe_app(), raise_server_exceptions=False)


def test_not_found_error_shape() -> None:
    response = client.get("/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"] == {"code": "PATIENT_NOT_FOUND", "message": "Patient was not found.", "details": {}}
    assert "request_id" in body


def test_unauthorized_error_default_code() -> None:
    response = client.get("/unauthorized")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_forbidden_error_default_code() -> None:
    response = client.get("/forbidden")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_conflict_error_custom_code() -> None:
    response = client.get("/conflict")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_validation_error_includes_details() -> None:
    response = client.get("/validation")
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"field": "email"}


def test_business_rule_error_defaults_to_400() -> None:
    response = client.get("/business-rule")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"


def test_unhandled_exception_never_leaks_internals() -> None:
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "postgres://" not in response.text
    assert "user:pass" not in response.text
    assert "password" not in response.text.lower()


def test_app_error_base_class_allows_custom_status_code() -> None:
    err = AppError("custom", status_code=418, code="TEAPOT")
    assert err.status_code == 418
    assert err.code == "TEAPOT"


def test_not_found_endpoint_still_gets_request_id_header() -> None:
    # register_exception_handlers alone (no RequestContextMiddleware in this
    # probe app) means request_id is None - that's fine, this only checks
    # the field is present in the body per the documented envelope shape.
    response = client.get("/not-found")
    assert "request_id" in response.json()
