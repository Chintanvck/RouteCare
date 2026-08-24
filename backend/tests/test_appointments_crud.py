"""Tests for POST/GET/PATCH/DELETE /api/v1/appointments."""

import uuid
from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.appointment import Appointment, AppointmentStatus
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

APPOINTMENTS_URL = "/api/v1/appointments"

# A Monday, safely in the future relative to any plausible "today".
NEXT_MONDAY = date(2026, 8, 24)
assert NEXT_MONDAY.weekday() == 0


def _setup(db_session: Session, clinic):
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    return admin, therapist, patient


def test_create_appointment_succeeds(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)

    payload = {
        "patient_id": str(patient.id),
        "therapist_id": str(therapist.id),
        "scheduled_date": str(NEXT_MONDAY),
        "start_time": "10:00:00",
        "duration_minutes": 45,
    }
    response = client.post(APPOINTMENTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SCHEDULED"
    assert body["end_time"] == "10:45:00"
    assert body["patient_name"] == patient.full_name
    assert body["therapist_name"] == f"{therapist.first_name} {therapist.last_name}"


def test_create_appointment_unknown_therapist_fails_clearly(client: TestClient, db_session: Session, clinic) -> None:
    admin, _therapist, patient = _setup(db_session, clinic)

    payload = {
        "patient_id": str(patient.id),
        "therapist_id": str(uuid.uuid4()),
        "scheduled_date": str(NEXT_MONDAY),
        "start_time": "10:00:00",
        "duration_minutes": 45,
    }
    response = client.post(APPOINTMENTS_URL, json=payload, headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "THERAPIST_NOT_FOUND"


def test_create_appointment_unknown_patient_fails_clearly(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, _patient = _setup(db_session, clinic)

    payload = {
        "patient_id": str(uuid.uuid4()),
        "therapist_id": str(therapist.id),
        "scheduled_date": str(NEXT_MONDAY),
        "start_time": "10:00:00",
        "duration_minutes": 45,
    }
    response = client.post(APPOINTMENTS_URL, json=payload, headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_get_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.get(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["id"] == str(appt.id)


def test_update_appointment_time(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"start_time": "11:00:00"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["start_time"] == "11:00:00"
    assert response.json()["end_time"] == "11:45:00"


def test_update_appointment_status(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.patch(f"{APPOINTMENTS_URL}/{appt.id}", json={"status": "COMPLETED"}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_update_never_silently_moves_on_conflict(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(13, 0),
        duration_minutes=60,
    )
    movable = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{movable.id}", json={"start_time": "13:30:00"}, headers=auth_headers(admin)
    )
    assert response.status_code == 400
    db_session.refresh(movable)
    assert movable.start_time == time(10, 0)  # untouched


def test_cancel_appointment_sets_status_not_hard_delete(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.delete(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(admin))
    assert response.status_code == 204

    row = db_session.get(Appointment, appt.id)
    assert row is not None
    assert row.status == AppointmentStatus.CANCELLED


def test_cancelled_slot_can_be_rebooked(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )
    client.delete(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(admin))

    payload = {
        "patient_id": str(patient.id),
        "therapist_id": str(therapist.id),
        "scheduled_date": str(NEXT_MONDAY),
        "start_time": "10:00:00",
        "duration_minutes": 45,
    }
    response = client.post(APPOINTMENTS_URL, json=payload, headers=auth_headers(admin))
    assert response.status_code == 201


def test_date_range_query(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY + timedelta(days=10),
        start_time=time(10, 0),
    )

    response = client.get(
        f"{APPOINTMENTS_URL}?start_date={NEXT_MONDAY}&end_date={NEXT_MONDAY}", headers=auth_headers(admin)
    )
    assert response.json()["total"] == 1


def test_filter_by_status(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
        status=AppointmentStatus.CANCELLED,
    )
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(12, 0),
    )

    response = client.get(f"{APPOINTMENTS_URL}?status=SCHEDULED", headers=auth_headers(admin))
    assert response.json()["total"] == 1
