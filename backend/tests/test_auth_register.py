"""Tests for POST /auth/register."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.clinic import Clinic
from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"

VALID_PAYLOAD = {
    "clinic_name": "ABC Therapy",
    "first_name": "John",
    "last_name": "Smith",
    "email": "john@example.com",
    "password": "Str0ng!Passw0rd",
}


def test_register_creates_clinic_and_admin_user(client: TestClient, db_session: Session) -> None:
    response = client.post(REGISTER_URL, json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["message"]
    assert "user_id" in body

    user = db_session.query(User).filter(User.email == "john@example.com").one()
    assert user.role.value == "CLINIC_ADMIN"
    assert user.password_hash != VALID_PAYLOAD["password"]

    clinic = db_session.get(Clinic, user.clinic_id)
    assert clinic is not None
    assert clinic.name == "ABC Therapy"


def test_register_never_returns_password(client: TestClient) -> None:
    response = client.post(REGISTER_URL, json=VALID_PAYLOAD)
    assert VALID_PAYLOAD["password"] not in response.text
    assert "password_hash" not in response.json()


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    client.post(REGISTER_URL, json=VALID_PAYLOAD)
    response = client.post(REGISTER_URL, json=VALID_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_rejects_weak_password(client: TestClient) -> None:
    payload = {**VALID_PAYLOAD, "password": "weak"}
    response = client.post(REGISTER_URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_rejects_invalid_email(client: TestClient) -> None:
    payload = {**VALID_PAYLOAD, "email": "not-an-email"}
    response = client.post(REGISTER_URL, json=payload)

    assert response.status_code == 422


def test_register_normalizes_email_case(client: TestClient, db_session: Session) -> None:
    payload = {**VALID_PAYLOAD, "email": "John@EXAMPLE.com"}
    response = client.post(REGISTER_URL, json=payload)

    assert response.status_code == 201
    user = db_session.query(User).filter(User.email == "john@example.com").one_or_none()
    assert user is not None
