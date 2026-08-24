"""Tests for therapist and patient availability endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.conftest import auth_headers, make_patient, make_therapist, make_user

VALID_THERAPIST_RULES = {
    "rules": [
        {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "is_available": True},
        {"day_of_week": 0, "start_time": "12:00:00", "end_time": "13:00:00", "is_available": False},
        {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "is_available": True},
    ]
}


def test_set_and_get_therapist_availability(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    set_response = client.put(
        f"/api/v1/therapists/{therapist.id}/availability", json=VALID_THERAPIST_RULES, headers=auth_headers(admin)
    )
    assert set_response.status_code == 200
    assert len(set_response.json()) == 3

    get_response = client.get(f"/api/v1/therapists/{therapist.id}/availability", headers=auth_headers(admin))
    assert get_response.status_code == 200
    assert len(get_response.json()) == 3
    assert get_response.json()[0]["day_of_week"] == 0


def test_set_therapist_availability_replaces_previous_set(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    client.put(
        f"/api/v1/therapists/{therapist.id}/availability", json=VALID_THERAPIST_RULES, headers=auth_headers(admin)
    )
    second = {"rules": [{"day_of_week": 2, "start_time": "10:00:00", "end_time": "14:00:00", "is_available": True}]}
    response = client.put(f"/api/v1/therapists/{therapist.id}/availability", json=second, headers=auth_headers(admin))

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["day_of_week"] == 2


def test_therapist_availability_rejects_end_before_start(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    bad_rules = {"rules": [{"day_of_week": 0, "start_time": "17:00:00", "end_time": "09:00:00", "is_available": True}]}
    response = client.put(
        f"/api/v1/therapists/{therapist.id}/availability", json=bad_rules, headers=auth_headers(admin)
    )
    assert response.status_code == 422


def test_therapist_availability_rejects_invalid_day_of_week(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)

    bad_rules = {"rules": [{"day_of_week": 7, "start_time": "09:00:00", "end_time": "17:00:00", "is_available": True}]}
    response = client.put(
        f"/api/v1/therapists/{therapist.id}/availability", json=bad_rules, headers=auth_headers(admin)
    )
    assert response.status_code == 422


def test_therapist_cannot_set_own_availability(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_therapist(db_session, clinic)
    response = client.put(
        f"/api/v1/therapists/{therapist.id}/availability",
        json=VALID_THERAPIST_RULES,
        headers=auth_headers(therapist.user),
    )
    assert response.status_code == 403


def test_therapist_can_view_availability(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    client.put(
        f"/api/v1/therapists/{therapist.id}/availability", json=VALID_THERAPIST_RULES, headers=auth_headers(admin)
    )

    response = client.get(f"/api/v1/therapists/{therapist.id}/availability", headers=auth_headers(therapist.user))
    assert response.status_code == 200
    assert len(response.json()) == 3


# --- patient availability ---

VALID_PATIENT_RULES = {
    "rules": [
        {"day_of_week": 0, "start_time": "08:00:00", "end_time": "12:00:00", "preference_type": "PREFERRED"},
        {"day_of_week": 0, "start_time": "12:00:00", "end_time": "13:00:00", "preference_type": "NOT_AVAILABLE"},
    ]
}


def test_set_and_get_patient_availability(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic)

    set_response = client.put(
        f"/api/v1/patients/{patient.id}/availability", json=VALID_PATIENT_RULES, headers=auth_headers(admin)
    )
    assert set_response.status_code == 200
    assert len(set_response.json()) == 2

    get_response = client.get(f"/api/v1/patients/{patient.id}/availability", headers=auth_headers(admin))
    assert len(get_response.json()) == 2


def test_patient_availability_defaults_to_empty(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic)

    response = client.get(f"/api/v1/patients/{patient.id}/availability", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json() == []


def test_therapist_cannot_set_patient_availability(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic)

    response = client.put(
        f"/api/v1/patients/{patient.id}/availability", json=VALID_PATIENT_RULES, headers=auth_headers(therapist.user)
    )
    assert response.status_code == 403


def test_availability_endpoints_404_for_unknown_therapist_or_patient(
    client: TestClient, db_session: Session, clinic
) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.get(f"/api/v1/therapists/{uuid.uuid4()}/availability", headers=auth_headers(admin))
    assert response.status_code == 404

    response = client.get(f"/api/v1/patients/{uuid.uuid4()}/availability", headers=auth_headers(admin))
    assert response.status_code == 404
