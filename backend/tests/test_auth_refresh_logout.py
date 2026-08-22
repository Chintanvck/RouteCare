"""Tests for POST /auth/refresh and POST /auth/logout."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.refresh_token import RefreshToken
from tests.conftest import VALID_PASSWORD, make_user

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


def _login(client: TestClient, db_session: Session, clinic) -> dict:
    make_user(db_session, clinic, email="jane@example.com")
    response = client.post(LOGIN_URL, json={"email": "jane@example.com", "password": VALID_PASSWORD})
    return response.json()


def test_refresh_issues_new_token_pair(client: TestClient, db_session: Session, clinic) -> None:
    tokens = _login(client, db_session, clinic)

    response = client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


def test_refresh_rotates_out_old_token(client: TestClient, db_session: Session, clinic) -> None:
    tokens = _login(client, db_session, clinic)

    client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

    row = db_session.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(tokens["refresh_token"])).one()
    assert row.revoked_at is not None


def test_refresh_reuse_of_rotated_token_revokes_all_sessions(client: TestClient, db_session: Session, clinic) -> None:
    tokens = _login(client, db_session, clinic)

    # First refresh rotates the token out.
    second = client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}).json()

    # Reusing the now-revoked original token is a replay attempt.
    reuse_response = client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
    assert reuse_response.status_code == 401
    assert reuse_response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    # The second (legitimately rotated) token must also now be dead.
    followup_response = client.post(REFRESH_URL, json={"refresh_token": second["refresh_token"]})
    assert followup_response.status_code == 401


def test_refresh_rejects_unknown_token(client: TestClient) -> None:
    response = client.post(REFRESH_URL, json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


def test_refresh_rejects_expired_token(client: TestClient, db_session: Session, clinic) -> None:
    tokens = _login(client, db_session, clinic)
    row = db_session.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(tokens["refresh_token"])).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    response = client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


def test_logout_revokes_refresh_token(client: TestClient, db_session: Session, clinic) -> None:
    tokens = _login(client, db_session, clinic)

    response = client.post(LOGOUT_URL, json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200

    refresh_response = client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 401


def test_logout_with_unknown_token_still_succeeds(client: TestClient) -> None:
    response = client.post(LOGOUT_URL, json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 200
