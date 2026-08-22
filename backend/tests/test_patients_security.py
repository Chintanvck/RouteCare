"""Tests for authentication, RBAC, and cross-tenant isolation on patient endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.clinic import Clinic
from tests.conftest import VALID_PASSWORD, auth_headers, make_patient, make_user

PATIENTS_URL = "/api/v1/patients"

VALID_PAYLOAD = {
    "first_name": "Mary",
    "last_name": "Smith",
    "address_line_1": "123 Main St",
    "city": "Hoboken",
    "state": "NJ",
    "zip_code": "07030",
}


def test_list_requires_authentication(client: TestClient) -> None:
    response = client.get(PATIENTS_URL)
    assert response.status_code == 401


def test_create_requires_authentication(client: TestClient) -> None:
    response = client.post(PATIENTS_URL, json=VALID_PAYLOAD)
    assert response.status_code == 401


def test_therapist_can_list_patients(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    make_patient(db_session, clinic)

    response = client.get(PATIENTS_URL, headers=auth_headers(therapist))
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_therapist_can_get_single_patient(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    patient = make_patient(db_session, clinic)

    response = client.get(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(therapist))
    assert response.status_code == 200


def test_therapist_cannot_create_patient(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    response = client.post(PATIENTS_URL, json=VALID_PAYLOAD, headers=auth_headers(therapist))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_therapist_cannot_update_patient(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    patient = make_patient(db_session, clinic)

    response = client.patch(f"{PATIENTS_URL}/{patient.id}", json={"first_name": "X"}, headers=auth_headers(therapist))
    assert response.status_code == 403


def test_therapist_cannot_delete_patient(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    patient = make_patient(db_session, clinic)

    response = client.delete(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(therapist))
    assert response.status_code == 403


def test_office_scheduler_can_create_and_manage_patients(client: TestClient, db_session: Session, clinic) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER)

    create_response = client.post(PATIENTS_URL, json=VALID_PAYLOAD, headers=auth_headers(scheduler))
    assert create_response.status_code == 201

    patient_id = create_response.json()["id"]
    update_response = client.patch(
        f"{PATIENTS_URL}/{patient_id}", json={"first_name": "Updated"}, headers=auth_headers(scheduler)
    )
    assert update_response.status_code == 200

    delete_response = client.delete(f"{PATIENTS_URL}/{patient_id}", headers=auth_headers(scheduler))
    assert delete_response.status_code == 204


def test_system_admin_cannot_access_clinic_patients(client: TestClient, db_session: Session, clinic) -> None:
    system_admin = make_user(db_session, None, role=UserRole.SYSTEM_ADMIN, email="sysadmin@example.com")
    make_patient(db_session, clinic)

    response = client.get(PATIENTS_URL, headers=auth_headers(system_admin))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_cross_clinic_get_returns_404_not_403(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    clinic_a_admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="a-admin@example.com")
    patient_in_other_clinic = make_patient(db_session, other_clinic, first_name="Secret")

    response = client.get(f"{PATIENTS_URL}/{patient_in_other_clinic.id}", headers=auth_headers(clinic_a_admin))

    # Enumeration-safe: a patient that exists in a different clinic looks
    # identical to one that doesn't exist at all.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_cross_clinic_update_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    clinic_a_admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="a-admin@example.com")
    patient_in_other_clinic = make_patient(db_session, other_clinic)

    response = client.patch(
        f"{PATIENTS_URL}/{patient_in_other_clinic.id}",
        json={"first_name": "Hacked"},
        headers=auth_headers(clinic_a_admin),
    )
    assert response.status_code == 404


def test_cross_clinic_delete_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    clinic_a_admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="a-admin@example.com")
    patient_in_other_clinic = make_patient(db_session, other_clinic)

    response = client.delete(f"{PATIENTS_URL}/{patient_in_other_clinic.id}", headers=auth_headers(clinic_a_admin))
    assert response.status_code == 404


def test_cross_clinic_list_never_leaks_other_clinics_patients(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    clinic_a_admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="a-admin@example.com")
    make_patient(db_session, clinic, first_name="Mine")
    make_patient(db_session, other_clinic, first_name="TheirsNotMine")

    response = client.get(PATIENTS_URL, headers=auth_headers(clinic_a_admin))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["first_name"] == "Mine"


def test_inactive_user_cannot_access_patients(client: TestClient, db_session: Session, clinic) -> None:
    user = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, is_active=False)
    response = client.get(PATIENTS_URL, headers=auth_headers(user))
    assert response.status_code == 401


def test_end_to_end_login_then_list_patients(client: TestClient, db_session: Session, clinic) -> None:
    """Sanity check using a real login round-trip rather than the auth_headers() shortcut."""
    make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="real@example.com")
    make_patient(db_session, clinic)

    login_response = client.post("/api/v1/auth/login", json={"email": "real@example.com", "password": VALID_PASSWORD})
    token = login_response.json()["access_token"]

    response = client.get(PATIENTS_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
