"""Tests for appointment business-rule validation, via both POST /appointments and the
POST /appointments/validate dry run - both must agree, since they share one implementation."""

from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_therapist_availability,
    make_user,
    make_weekday_availability,
)

APPOINTMENTS_URL = "/api/v1/appointments"
VALIDATE_URL = "/api/v1/appointments/validate"

NEXT_MONDAY = date(2026, 8, 24)
assert NEXT_MONDAY.weekday() == 0


def _setup(db_session: Session, clinic):
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic)
    return admin, therapist, patient


def _payload(therapist, patient, start_time="10:00:00", duration=45, scheduled_date=NEXT_MONDAY):
    return {
        "patient_id": str(patient.id),
        "therapist_id": str(therapist.id),
        "scheduled_date": str(scheduled_date),
        "start_time": start_time,
        "duration_minutes": duration,
    }


def test_reject_appointment_on_therapists_day_off(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    # No availability rows configured at all - every day is a day off.

    response = client.post(APPOINTMENTS_URL, json=_payload(therapist, patient), headers=auth_headers(admin))
    assert response.status_code == 400
    assert "does not work on this day" in response.json()["error"]["message"]


def test_reject_appointment_outside_working_hours(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(12, 0))

    response = client.post(
        APPOINTMENTS_URL, json=_payload(therapist, patient, start_time="14:00:00"), headers=auth_headers(admin)
    )
    assert response.status_code == 400
    assert "outside the therapist's working hours" in response.json()["error"]["message"]


def test_reject_appointment_overlapping_break(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
    make_therapist_availability(
        db_session, therapist, day_of_week=0, start_time=time(12, 0), end_time=time(13, 0), is_available=False
    )

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist, patient, start_time="12:30:00", duration=30),
        headers=auth_headers(admin),
    )
    assert response.status_code == 400
    assert "break" in response.json()["error"]["message"]


def test_reject_overlapping_appointment_with_exact_task_message_format(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)
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

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist, patient, start_time="13:30:00", duration=30),
        headers=auth_headers(admin),
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Therapist already has an appointment from 1:00 PM to 2:00 PM."


def test_reject_appointment_for_inactive_therapist(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, is_active=False)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    response = client.post(APPOINTMENTS_URL, json=_payload(therapist, patient), headers=auth_headers(admin))
    assert response.status_code == 400
    assert "not currently active" in response.json()["error"]["message"]


def test_reject_appointment_outside_patient_availability(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    client.put(
        f"/api/v1/patients/{patient.id}/availability",
        json={
            "rules": [
                {
                    "day_of_week": 0,
                    "start_time": "08:00:00",
                    "end_time": "09:00:00",
                    "preference_type": "AVAILABLE",
                }
            ]
        },
        headers=auth_headers(admin),
    )

    response = client.post(
        APPOINTMENTS_URL, json=_payload(therapist, patient, start_time="10:00:00"), headers=auth_headers(admin)
    )
    assert response.status_code == 400
    assert "outside the patient's available hours" in response.json()["error"]["message"]


def test_patient_with_no_availability_configured_is_flexible(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)

    response = client.post(APPOINTMENTS_URL, json=_payload(therapist, patient), headers=auth_headers(admin))
    assert response.status_code == 201


def test_valid_appointment_passes(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)

    response = client.post(APPOINTMENTS_URL, json=_payload(therapist, patient), headers=auth_headers(admin))
    assert response.status_code == 201


# --- dry-run /validate endpoint agrees with the real create path ---


def test_validate_endpoint_reports_conflict_without_persisting(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)
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

    response = client.post(
        VALIDATE_URL, json=_payload(therapist, patient, start_time="13:30:00", duration=30), headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert len(body["errors"]) == 1

    # Nothing was actually created.
    list_response = client.get(APPOINTMENTS_URL, headers=auth_headers(admin))
    assert list_response.json()["total"] == 1  # only the one seeded directly, not a second from validate


def test_validate_endpoint_reports_valid_for_a_clean_slot(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)

    response = client.post(VALIDATE_URL, json=_payload(therapist, patient), headers=auth_headers(admin))
    assert response.json() == {"valid": True, "errors": []}


def test_validate_excludes_own_appointment_when_checking_a_move(
    client: TestClient, db_session: Session, clinic
) -> None:
    """Validating 'move appointment X to a new time' must not flag X's own current slot as a conflict."""
    admin, therapist, patient = _setup(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    payload = {**_payload(therapist, patient, start_time="10:00:00"), "exclude_appointment_id": str(appt.id)}
    response = client.post(VALIDATE_URL, json=payload, headers=auth_headers(admin))
    assert response.json()["valid"] is True
