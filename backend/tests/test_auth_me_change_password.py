"""Tests for GET /auth/me and POST /auth/change-password."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import VALID_PASSWORD, make_user

LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
CHANGE_PASSWORD_URL = "/api/v1/auth/change-password"
REFRESH_URL = "/api/v1/auth/refresh"


def _login_headers(
    client: TestClient, db_session: Session, clinic, email: str = "jane@example.com"
) -> tuple[dict, dict]:
    make_user(db_session, clinic, email=email)
    tokens = client.post(LOGIN_URL, json={"email": email, "password": VALID_PASSWORD}).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}, tokens


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get(ME_URL)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get(ME_URL, headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401


def test_me_returns_current_user(client: TestClient, db_session: Session, clinic) -> None:
    headers, _ = _login_headers(client, db_session, clinic)

    response = client.get(ME_URL, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "jane@example.com"
    assert body["role"] == "CLINIC_ADMIN"
    assert "password" not in body
    assert "password_hash" not in body


def test_change_password_succeeds_and_revokes_sessions(client: TestClient, db_session: Session, clinic) -> None:
    headers, tokens = _login_headers(client, db_session, clinic)

    response = client.post(
        CHANGE_PASSWORD_URL,
        headers=headers,
        json={"current_password": VALID_PASSWORD, "new_password": "N3wStr0ng!Pass"},
    )
    assert response.status_code == 200

    # Old refresh token must be dead after a password change.
    refresh_response = client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 401

    # New password logs in; old one no longer works.
    old_login = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": VALID_PASSWORD})
    assert old_login.status_code == 401

    new_login = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": "N3wStr0ng!Pass"})
    assert new_login.status_code == 200


def test_change_password_rejects_wrong_current_password(client: TestClient, db_session: Session, clinic) -> None:
    headers, _ = _login_headers(client, db_session, clinic)

    response = client.post(
        CHANGE_PASSWORD_URL,
        headers=headers,
        json={"current_password": "WrongCurrent1!", "new_password": "N3wStr0ng!Pass"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_change_password_rejects_weak_new_password(client: TestClient, db_session: Session, clinic) -> None:
    headers, _ = _login_headers(client, db_session, clinic)

    response = client.post(
        CHANGE_PASSWORD_URL,
        headers=headers,
        json={"current_password": VALID_PASSWORD, "new_password": "weak"},
    )

    assert response.status_code == 422
