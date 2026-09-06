"""Tests for Phase 9 rate limiting (app.core.rate_limiting).

Backed by tests/conftest.py's `_fake_redis_cache` autouse fixture, which now supports `incr`/
`expire` in addition to `get`/`setex` - counters are real (in-memory) for the duration of one test,
never a no-op, so these tests exercise the actual fixed-window logic rather than just checking that
a code path exists."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import UserRole
from tests.conftest import VALID_PASSWORD, auth_headers, make_user

LOGIN_URL = "/api/v1/auth/login"
REGISTER_URL = "/api/v1/auth/register"
RESET_URL = "/api/v1/auth/request-password-reset"
OPT_URL = "/api/v1/optimization/requests"


def test_login_rate_limited_after_max_attempts(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="victim@example.com")

    for _ in range(settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS):
        resp = client.post(LOGIN_URL, json={"email": "victim@example.com", "password": "wrong"})
        assert resp.status_code == 401

    blocked = client.post(LOGIN_URL, json={"email": "victim@example.com", "password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


def test_login_rate_limit_is_scoped_per_email(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="a@example.com")
    make_user(db_session, clinic, email="b@example.com")

    for _ in range(settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS):
        client.post(LOGIN_URL, json={"email": "a@example.com", "password": "wrong"})
    exhausted = client.post(LOGIN_URL, json={"email": "a@example.com", "password": "wrong"})
    assert exhausted.status_code == 429

    # A different email from the same client is a different bucket - never widened by a's lockout.
    still_ok = client.post(LOGIN_URL, json={"email": "b@example.com", "password": "wrong"})
    assert still_ok.status_code == 401


def test_successful_login_still_counts_toward_the_window(client: TestClient, db_session: Session, clinic) -> None:
    """The limiter counts attempts, not failures - a correct password on attempt N doesn't reset
    the counter for whatever's left in the window (a compromised-but-correct-password brute force
    against a locked account is exactly what this defends)."""
    make_user(db_session, clinic, email="user@example.com", password=VALID_PASSWORD)

    for _ in range(settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS - 1):
        client.post(LOGIN_URL, json={"email": "user@example.com", "password": "wrong"})

    ok = client.post(LOGIN_URL, json={"email": "user@example.com", "password": VALID_PASSWORD})
    assert ok.status_code == 200

    blocked = client.post(LOGIN_URL, json={"email": "user@example.com", "password": VALID_PASSWORD})
    assert blocked.status_code == 429


def test_register_rate_limited_after_max_attempts(client: TestClient) -> None:
    for i in range(settings.RATE_LIMIT_REGISTER_MAX_ATTEMPTS):
        resp = client.post(
            REGISTER_URL,
            json={
                "clinic_name": f"Clinic {i}",
                "first_name": "A",
                "last_name": "B",
                "email": f"reg{i}@example.com",
                "password": VALID_PASSWORD,
            },
        )
        assert resp.status_code == 201

    blocked = client.post(
        REGISTER_URL,
        json={
            "clinic_name": "One More Clinic",
            "first_name": "A",
            "last_name": "B",
            "email": "one-more@example.com",
            "password": VALID_PASSWORD,
        },
    )
    assert blocked.status_code == 429


def test_password_reset_rate_limited_after_max_attempts(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="reset-target@example.com")

    for _ in range(settings.RATE_LIMIT_PASSWORD_RESET_MAX_ATTEMPTS):
        resp = client.post(RESET_URL, json={"email": "reset-target@example.com"})
        assert resp.status_code == 200

    blocked = client.post(RESET_URL, json={"email": "reset-target@example.com"})
    assert blocked.status_code == 429


def test_expensive_operation_rate_limit_applies_per_user(client: TestClient, db_session: Session, clinic) -> None:
    """Exercises the generic app.core.rate_limiting.rate_limit() factory via the optimization
    request-creation endpoint. Uses the real configured limit rather than monkeypatching it down -
    `dependencies=[Depends(rate_limit("optimization_create", limit=settings.RATE_LIMIT_OPTIMIZATION_MAX, ...))]`
    reads the setting once, at router-import time, so patching the setting after the app (and thus
    the router module) is already loaded has no effect on an already-built dependency - the same
    "value captured too early" trap this phase's own rate-limiting bugfix hit. A bogus therapist_id
    still reaches (and is counted by) the rate-limit dependency before 404ing, since FastAPI
    resolves `dependencies=[...]` before the route body runs, so this stays fast even at the real limit."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    payload = {"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(uuid.uuid4()), "target_date": "2026-08-24"}

    for _ in range(settings.RATE_LIMIT_OPTIMIZATION_MAX):
        resp = client.post(OPT_URL, json=payload, headers=auth_headers(admin))
        assert resp.status_code == 404  # therapist doesn't exist - the dependency still ran first

    blocked = client.post(OPT_URL, json=payload, headers=auth_headers(admin))
    assert blocked.status_code == 429


def test_rate_limiting_fails_open_when_redis_unavailable(
    client: TestClient, db_session: Session, clinic, monkeypatch
) -> None:
    """Matches app.core.cache's documented philosophy: Redis being down must never turn into every
    login attempt being rejected."""
    import redis

    from app.core import cache as cache_module

    def broken_client():
        raise redis.RedisError("connection refused")

    monkeypatch.setattr(cache_module, "get_redis_client", broken_client)
    make_user(db_session, clinic, email="resilient@example.com")

    for _ in range(settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS + 3):
        resp = client.post(LOGIN_URL, json={"email": "resilient@example.com", "password": "wrong"})
        assert resp.status_code == 401  # never 429 - Redis errors never block real requests
