"""Tests for POST/GET/PATCH /api/v1/therapists."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.therapist import Therapist
from app.models.user import User
from tests.conftest import auth_headers, make_therapist, make_user

THERAPISTS_URL = "/api/v1/therapists"

VALID_PAYLOAD = {
    "first_name": "Terry",
    "last_name": "Therapist",
    "email": "terry@example.com",
    "password": "Str0ng!Passw0rd",
    "license_type": "PT",
    "phone": "201-555-0111",
    "max_daily_hours": 8,
}


def test_create_therapist_creates_user_and_profile(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    response = client.post(THERAPISTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Terry"
    assert body["email"] == "terry@example.com"
    assert body["is_active"] is True

    user = db_session.query(User).filter(User.email == "terry@example.com").one()
    assert user.role == UserRole.THERAPIST
    therapist = db_session.query(Therapist).filter(Therapist.user_id == user.id).one()
    assert therapist.clinic_id == clinic.id
    assert therapist.license_type == "PT"


def test_create_therapist_never_returns_password(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(THERAPISTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))
    assert VALID_PAYLOAD["password"] not in response.text
    assert "password" not in response.json()


def test_create_therapist_rejects_duplicate_email(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    client.post(THERAPISTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))

    response = client.post(THERAPISTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_create_therapist_rejects_weak_password(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(THERAPISTS_URL, json={**VALID_PAYLOAD, "password": "weak"}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_get_therapist(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    response = client.get(f"{THERAPISTS_URL}/{therapist.id}", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["id"] == str(therapist.id)


def test_get_unknown_therapist_404s(client: TestClient, db_session: Session, clinic) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.get(f"{THERAPISTS_URL}/{uuid.uuid4()}", headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "THERAPIST_NOT_FOUND"


def test_update_therapist_profile_fields(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    response = client.patch(
        f"{THERAPISTS_URL}/{therapist.id}",
        json={"license_type": "OT", "max_daily_hours": 6},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["license_type"] == "OT"
    assert body["max_daily_hours"] == 6


def test_update_therapist_name_updates_linked_user_not_a_new_one(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, email="original@example.com")
    original_user_id = therapist.user_id

    response = client.patch(
        f"{THERAPISTS_URL}/{therapist.id}", json={"first_name": "Updated"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["first_name"] == "Updated"
    assert response.json()["user_id"] == str(original_user_id)
    assert db_session.query(User).count() == 2  # admin + the one therapist user - no duplicate created


def test_deactivate_therapist_toggles_user_is_active(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    response = client.patch(f"{THERAPISTS_URL}/{therapist.id}", json={"is_active": False}, headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    db_session.refresh(therapist.user)
    assert therapist.user.is_active is False


def test_list_therapists(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_therapist(db_session, clinic, email="a@example.com", first_name="Amy")
    make_therapist(db_session, clinic, email="b@example.com", first_name="Bob")

    response = client.get(THERAPISTS_URL, headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_list_therapists_search_by_name(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_therapist(db_session, clinic, email="a@example.com", first_name="Amy", last_name="Anderson")
    make_therapist(db_session, clinic, email="b@example.com", first_name="Bob", last_name="Baker")

    response = client.get(f"{THERAPISTS_URL}?search=Amy", headers=auth_headers(admin))

    assert response.json()["total"] == 1
    assert response.json()["items"][0]["first_name"] == "Amy"


def test_list_therapists_filter_by_active(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_therapist(db_session, clinic, email="active@example.com", is_active=True)
    make_therapist(db_session, clinic, email="inactive@example.com", is_active=False)

    response = client.get(f"{THERAPISTS_URL}?is_active=false", headers=auth_headers(admin))

    assert response.json()["total"] == 1
    assert response.json()["items"][0]["email"] == "inactive@example.com"
