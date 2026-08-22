"""Tests for POST /auth/request-password-reset and POST /auth/reset-password."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.password_reset_token import PasswordResetToken
from tests.conftest import VALID_PASSWORD, make_user

REQUEST_RESET_URL = "/api/v1/auth/request-password-reset"
RESET_URL = "/api/v1/auth/reset-password"
LOGIN_URL = "/api/v1/auth/login"


def test_request_reset_for_existing_email_returns_dev_token(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com")

    response = client.post(REQUEST_RESET_URL, json={"email": "jane@example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"]
    # ENVIRONMENT defaults to "development" in tests, so the dev convenience field is populated.
    assert body["reset_token"]


def test_request_reset_for_unknown_email_returns_same_response_shape(client: TestClient) -> None:
    response = client.post(REQUEST_RESET_URL, json={"email": "nobody@example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"]
    assert body["reset_token"] is None


def test_reset_password_with_valid_token_succeeds(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com")
    reset_token = client.post(REQUEST_RESET_URL, json={"email": "jane@example.com"}).json()["reset_token"]

    response = client.post(RESET_URL, json={"token": reset_token, "new_password": "N3wStr0ng!Pass"})
    assert response.status_code == 200

    old_login = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": VALID_PASSWORD})
    assert old_login.status_code == 401

    new_login = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": "N3wStr0ng!Pass"})
    assert new_login.status_code == 200


def test_reset_password_token_is_single_use(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com")
    reset_token = client.post(REQUEST_RESET_URL, json={"email": "jane@example.com"}).json()["reset_token"]

    first = client.post(RESET_URL, json={"token": reset_token, "new_password": "N3wStr0ng!Pass"})
    assert first.status_code == 200

    second = client.post(RESET_URL, json={"token": reset_token, "new_password": "An0therStr0ng!"})
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "INVALID_RESET_TOKEN"


def test_reset_password_rejects_unknown_token(client: TestClient) -> None:
    response = client.post(RESET_URL, json={"token": "not-a-real-token", "new_password": "N3wStr0ng!Pass"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"


def test_reset_password_rejects_expired_token(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com")
    reset_token = client.post(REQUEST_RESET_URL, json={"email": "jane@example.com"}).json()["reset_token"]

    row = db_session.query(PasswordResetToken).filter(PasswordResetToken.token_hash == hash_token(reset_token)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    response = client.post(RESET_URL, json={"token": reset_token, "new_password": "N3wStr0ng!Pass"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"
