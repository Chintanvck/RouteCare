"""Tests for GET /health/live and GET /health/ready.

check_database/check_redis are monkeypatched rather than hit for real:
this sandbox has no live Postgres/Redis, and readiness intentionally
bypasses the test DB override to check the real configured
infrastructure (see app.core.health docstring) - so these tests would
otherwise depend on infrastructure that may or may not exist wherever
the suite runs.
"""

from fastapi.testclient import TestClient

import app.core.health as health


def test_liveness_always_succeeds(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_succeeds_when_all_dependencies_healthy(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: (True, None))
    monkeypatch.setattr(health, "check_redis", lambda: (True, None))

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True


def test_readiness_fails_when_postgres_unavailable(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: (False, "OperationalError"))
    monkeypatch.setattr(health, "check_redis", lambda: (True, None))

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"]["ok"] is False
    assert body["checks"]["database"]["error"] == "OperationalError"


def test_readiness_fails_when_redis_unavailable(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: (True, None))
    monkeypatch.setattr(health, "check_redis", lambda: (False, "ConnectionError"))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"]["ok"] is False


def test_readiness_never_leaks_raw_exception_text(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        health, "check_database", lambda: (False, "OperationalError")
    )  # class name only, never str(exc)
    monkeypatch.setattr(health, "check_redis", lambda: (True, None))

    response = client.get("/health/ready")

    assert "postgresql://" not in response.text
    assert "password" not in response.text.lower()
