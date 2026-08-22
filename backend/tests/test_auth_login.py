"""Tests for POST /auth/login."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import VALID_PASSWORD, make_user

LOGIN_URL = "/api/v1/auth/login"


def test_login_succeeds_with_correct_credentials(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com")

    response = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": VALID_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "jane@example.com"
    assert "password" not in body["user"]


def test_login_fails_with_wrong_password(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com")

    response = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": "WrongPassw0rd!"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_fails_for_unknown_email(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "WrongPassw0rd!"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_and_wrong_password_return_identical_errors(
    client: TestClient, db_session: Session, clinic
) -> None:
    """User-enumeration guard: both failure modes must be indistinguishable to the caller."""
    make_user(db_session, clinic, email="jane@example.com")

    wrong_password_response = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": "Wrong!Passw0rd"})
    unknown_email_response = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "Wrong!Passw0rd"})

    assert wrong_password_response.status_code == unknown_email_response.status_code == 401
    # request_id is expected to differ per request; the enumeration-safety
    # property is that the error itself is indistinguishable.
    assert wrong_password_response.json()["error"] == unknown_email_response.json()["error"]


def test_login_fails_for_inactive_user(client: TestClient, db_session: Session, clinic) -> None:
    make_user(db_session, clinic, email="jane@example.com", is_active=False)

    response = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": VALID_PASSWORD})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_updates_last_login(client: TestClient, db_session: Session, clinic) -> None:
    user = make_user(db_session, clinic, email="jane@example.com")
    assert user.last_login is None

    client.post(LOGIN_URL, json={"email": "jane@example.com", "password": VALID_PASSWORD})

    db_session.refresh(user)
    assert user.last_login is not None
