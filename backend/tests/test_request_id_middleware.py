"""Tests for RequestContextMiddleware and SecurityHeadersMiddleware."""

import re

from fastapi.testclient import TestClient

UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


def test_response_has_generated_request_id_header(client: TestClient) -> None:
    response = client.get("/health/live")
    assert "x-request-id" in response.headers
    assert UUID_HEX_RE.match(response.headers["x-request-id"])


def test_client_supplied_safe_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "my-trace-id-123"})
    assert response.headers["x-request-id"] == "my-trace-id-123"


def test_client_supplied_unsafe_request_id_is_replaced(client: TestClient) -> None:
    unsafe = "not safe! contains spaces and <script>"
    response = client.get("/health/live", headers={"X-Request-ID": unsafe})
    assert response.headers["x-request-id"] != unsafe
    assert UUID_HEX_RE.match(response.headers["x-request-id"])


def test_client_supplied_overlong_request_id_is_replaced(client: TestClient) -> None:
    overlong = "a" * 200
    response = client.get("/health/live", headers={"X-Request-ID": overlong})
    assert response.headers["x-request-id"] != overlong


def test_request_id_present_on_error_responses_too(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "x-request-id" in response.headers
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
