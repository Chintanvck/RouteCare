"""RBAC and cross-clinic isolation tests for the therapists API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.clinic import Clinic
from tests.conftest import auth_headers, make_therapist, make_user

THERAPISTS_URL = "/api/v1/therapists"

VALID_PAYLOAD = {
    "first_name": "Terry",
    "last_name": "Therapist",
    "email": "terry@example.com",
    "password": "Str0ng!Passw0rd",
}


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get(THERAPISTS_URL).status_code == 401


def test_therapist_can_list_and_view_therapists(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_therapist(db_session, clinic, email="viewer@example.com")
    response = client.get(THERAPISTS_URL, headers=auth_headers(therapist.user))
    assert response.status_code == 200


def test_therapist_cannot_create_therapist(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_therapist(db_session, clinic, email="viewer@example.com")
    response = client.post(THERAPISTS_URL, json=VALID_PAYLOAD, headers=auth_headers(therapist.user))
    assert response.status_code == 403


def test_therapist_cannot_update_therapist(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_therapist(db_session, clinic, email="viewer@example.com")
    other = make_therapist(db_session, clinic, email="other@example.com")
    response = client.patch(
        f"{THERAPISTS_URL}/{other.id}", json={"license_type": "PT"}, headers=auth_headers(therapist.user)
    )
    assert response.status_code == 403


def test_office_scheduler_can_create_and_edit_therapists(client: TestClient, db_session: Session, clinic) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER)
    create_response = client.post(THERAPISTS_URL, json=VALID_PAYLOAD, headers=auth_headers(scheduler))
    assert create_response.status_code == 201

    therapist_id = create_response.json()["id"]
    update_response = client.patch(
        f"{THERAPISTS_URL}/{therapist_id}", json={"license_type": "OT"}, headers=auth_headers(scheduler)
    )
    assert update_response.status_code == 200


def test_system_admin_cannot_access_therapists(client: TestClient, db_session: Session, clinic) -> None:
    system_admin = make_user(db_session, None, role=UserRole.SYSTEM_ADMIN, email="sysadmin@example.com")
    response = client.get(THERAPISTS_URL, headers=auth_headers(system_admin))
    assert response.status_code == 403


def test_cross_clinic_get_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    other_therapist = make_therapist(db_session, other_clinic, email="other@example.com")

    response = client.get(f"{THERAPISTS_URL}/{other_therapist.id}", headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "THERAPIST_NOT_FOUND"


def test_cross_clinic_update_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    other_therapist = make_therapist(db_session, other_clinic, email="other@example.com")

    response = client.patch(
        f"{THERAPISTS_URL}/{other_therapist.id}", json={"license_type": "PT"}, headers=auth_headers(admin)
    )
    assert response.status_code == 404


def test_cross_clinic_list_never_leaks_other_clinics_therapists(
    client: TestClient, db_session: Session, clinic
) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_therapist(db_session, clinic, email="mine@example.com")
    make_therapist(db_session, other_clinic, email="theirs@example.com")

    response = client.get(THERAPISTS_URL, headers=auth_headers(admin))
    assert response.json()["total"] == 1
