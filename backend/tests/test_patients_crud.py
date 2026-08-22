"""Tests for POST/GET/PATCH/DELETE /api/v1/patients."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.patient import Patient
from tests.conftest import auth_headers, make_patient, make_user

PATIENTS_URL = "/api/v1/patients"

VALID_PAYLOAD = {
    "first_name": "Mary",
    "last_name": "Smith",
    "address_line_1": "123 Main St",
    "city": "Hoboken",
    "state": "NJ",
    "zip_code": "07030",
}


def test_create_patient_succeeds(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    response = client.post(PATIENTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Mary"
    assert body["clinic_id"] == str(clinic.id)
    assert body["is_active"] is True
    assert body["source_system"] == "manual"

    patient = db_session.query(Patient).filter(Patient.id == body["id"]).one()
    assert patient.clinic_id == clinic.id


def test_create_patient_with_optional_fields(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    payload = {
        **VALID_PAYLOAD,
        "phone": "201-555-0100",
        "email": "mary@example.com",
        "visit_duration_minutes": 45,
        "priority_level": 2,
        "scheduling_notes": "Prefers mornings",
    }

    response = client.post(PATIENTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["phone"] == "201-555-0100"
    assert body["visit_duration_minutes"] == 45


def test_create_patient_rejects_missing_required_fields(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    payload = {"first_name": "Mary"}

    response = client.post(PATIENTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_patient_rejects_invalid_zip(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(PATIENTS_URL, json={**VALID_PAYLOAD, "zip_code": "abc"}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_create_patient_rejects_invalid_email(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(PATIENTS_URL, json={**VALID_PAYLOAD, "email": "not-an-email"}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_create_patient_rejects_invalid_phone(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(PATIENTS_URL, json={**VALID_PAYLOAD, "phone": "abc"}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_create_patient_rejects_invalid_state(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(PATIENTS_URL, json={**VALID_PAYLOAD, "state": "New Jersey"}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_get_patient_returns_patient(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic)

    response = client.get(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["id"] == str(patient.id)


def test_get_patient_404_for_unknown_id(client: TestClient, db_session: Session, clinic) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.get(f"{PATIENTS_URL}/{uuid.uuid4()}", headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_update_patient_partial_fields(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, first_name="Mary")

    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}", json={"first_name": "Marianne"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Marianne"
    assert body["last_name"] == "Smith"  # untouched


def test_update_patient_rejects_invalid_zip(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic)

    response = client.patch(f"{PATIENTS_URL}/{patient.id}", json={"zip_code": "bad"}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_update_unknown_patient_404s(client: TestClient, db_session: Session, clinic) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.patch(f"{PATIENTS_URL}/{uuid.uuid4()}", json={"first_name": "X"}, headers=auth_headers(admin))
    assert response.status_code == 404


def test_delete_patient_soft_deletes(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic)

    response = client.delete(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(admin))
    assert response.status_code == 204

    db_session.refresh(patient)
    assert patient.deleted_at is not None

    get_response = client.get(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(admin))
    assert get_response.status_code == 404


def test_delete_unknown_patient_404s(client: TestClient, db_session: Session, clinic) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.delete(f"{PATIENTS_URL}/{uuid.uuid4()}", headers=auth_headers(admin))
    assert response.status_code == 404


def test_deleted_patient_cannot_be_deleted_again(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic)

    client.delete(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(admin))
    second_delete = client.delete(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(admin))

    assert second_delete.status_code == 404
