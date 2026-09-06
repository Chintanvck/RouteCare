"""Tests for app.core.middleware.MaxBodySizeMiddleware - a generic Content-Length cap on every
JSON endpoint, independent of the import upload endpoint's own larger, streaming-enforced limit."""

from fastapi.testclient import TestClient

from app.core.config import settings


def test_oversized_json_body_is_rejected_before_reaching_the_route(client: TestClient) -> None:
    oversized_body = b'{"padding": "' + b"a" * (settings.MAX_REQUEST_BODY_BYTES + 1) + b'"}'

    response = client.post(
        "/api/v1/auth/login",
        content=oversized_body,
        headers={"Content-Length": str(len(oversized_body)), "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_body_within_the_limit_is_not_rejected_by_size(client: TestClient) -> None:
    # Still 401 (wrong credentials) - the point is it's not 413, i.e. it passed the size gate.
    response = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert response.status_code == 401


def test_import_upload_is_exempt_from_the_generic_body_size_cap(client: TestClient) -> None:
    """The import endpoint enforces its own larger IMPORT_MAX_FILE_SIZE_BYTES limit directly (see
    app.modules.imports.router._read_bounded) - a file bigger than the generic 1MB JSON cap but
    still under the import limit must not be rejected by this middleware."""
    import io

    oversized_for_generic_cap = settings.MAX_REQUEST_BODY_BYTES + 1024
    assert oversized_for_generic_cap < settings.IMPORT_MAX_FILE_SIZE_BYTES

    response = client.post(
        "/api/v1/auth/login",  # sanity: confirm the same size WOULD be rejected on a non-exempt path
        content=b"x" * oversized_for_generic_cap,
        headers={"Content-Length": str(oversized_for_generic_cap), "Content-Type": "application/json"},
    )
    assert response.status_code == 413

    # The import endpoint requires auth, so this will 401 (no valid token) rather than upload
    # successfully - the point here is only that it's not 413, i.e. the exemption is in effect.
    upload_response = client.post(
        "/api/v1/imports/patients",
        files={"file": ("big.xlsx", io.BytesIO(b"x" * oversized_for_generic_cap), "application/octet-stream")},
    )
    assert upload_response.status_code != 413
