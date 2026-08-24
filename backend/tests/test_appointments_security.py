"""RBAC and cross-clinic isolation tests for the appointments API - including the
THERAPIST-role "own appointments only" scoping (app.services.appointment_service's
restrict_to_therapist_id mechanism)."""

from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.clinic import Clinic
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

APPOINTMENTS_URL = "/api/v1/appointments"
NEXT_MONDAY = date(2026, 8, 24)
assert NEXT_MONDAY.weekday() == 0


def _payload(therapist, patient):
    return {
        "patient_id": str(patient.id),
        "therapist_id": str(therapist.id),
        "scheduled_date": str(NEXT_MONDAY),
        "start_time": "10:00:00",
        "duration_minutes": 45,
    }


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get(APPOINTMENTS_URL).status_code == 401


def test_therapist_cannot_create_appointment(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    response = client.post(APPOINTMENTS_URL, json=_payload(therapist, patient), headers=auth_headers(therapist.user))
    assert response.status_code == 403


def test_office_scheduler_can_create_appointment(client: TestClient, db_session: Session, clinic) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    response = client.post(APPOINTMENTS_URL, json=_payload(therapist, patient), headers=auth_headers(scheduler))
    assert response.status_code == 201


def test_therapist_sees_only_own_appointments_in_list(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    patient = make_patient(db_session, clinic)

    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist_a,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist_b,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(11, 0),
    )

    response = client.get(APPOINTMENTS_URL, headers=auth_headers(therapist_a.user))
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["therapist_id"] == str(therapist_a.id)


def test_therapist_list_ignores_therapist_id_param_and_forces_own(
    client: TestClient, db_session: Session, clinic
) -> None:
    """Even if a therapist explicitly asks for another therapist_id, they only ever get their own."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist_b,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(11, 0),
    )

    response = client.get(f"{APPOINTMENTS_URL}?therapist_id={therapist_b.id}", headers=auth_headers(therapist_a.user))
    assert response.json()["total"] == 0


def test_therapist_cannot_get_another_therapists_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist_b,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(11, 0),
    )

    response = client.get(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(therapist_a.user))
    assert response.status_code == 404


def test_therapist_can_view_and_reschedule_own_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    get_response = client.get(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(therapist.user))
    assert get_response.status_code == 200

    patch_response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"start_time": "11:00:00"}, headers=auth_headers(therapist.user)
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["start_time"] == "11:00:00"


def test_therapist_cannot_reassign_appointment_to_another_patient(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic, email="p1@example.com")
    other_patient = make_patient(db_session, clinic, email="p2@example.com", first_name="Other")
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
        f"{APPOINTMENTS_URL}/{appt.id}",
        json={"patient_id": str(other_patient.id)},
        headers=auth_headers(therapist.user),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "APPOINTMENT_FIELD_NOT_ALLOWED"


def test_therapist_cannot_cancel_another_therapists_appointment(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist_b,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(11, 0),
    )

    response = client.delete(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(therapist_a.user))
    assert response.status_code == 404


def test_therapist_can_cancel_own_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.delete(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(therapist.user))
    assert response.status_code == 204


def test_system_admin_cannot_access_appointments(client: TestClient, db_session: Session, clinic) -> None:
    system_admin = make_user(db_session, None, role=UserRole.SYSTEM_ADMIN, email="sysadmin@example.com")
    response = client.get(APPOINTMENTS_URL, headers=auth_headers(system_admin))
    assert response.status_code == 403


def test_cross_clinic_get_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    other_admin = make_user(db_session, other_clinic, role=UserRole.CLINIC_ADMIN, email="other-admin@example.com")
    other_therapist = make_therapist(db_session, other_clinic, email="other-t@example.com")
    other_patient = make_patient(db_session, other_clinic)
    other_appt = make_appointment(
        db_session,
        other_clinic,
        patient=other_patient,
        therapist=other_therapist,
        created_by=other_admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.get(f"{APPOINTMENTS_URL}/{other_appt.id}", headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "APPOINTMENT_NOT_FOUND"


def test_cross_clinic_list_never_leaks_other_clinics_appointments(
    client: TestClient, db_session: Session, clinic
) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    other_admin = make_user(db_session, other_clinic, role=UserRole.CLINIC_ADMIN, email="other-admin@example.com")
    other_therapist = make_therapist(db_session, other_clinic, email="other-t@example.com")
    other_patient = make_patient(db_session, other_clinic)
    make_appointment(
        db_session,
        other_clinic,
        patient=other_patient,
        therapist=other_therapist,
        created_by=other_admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )

    response = client.get(APPOINTMENTS_URL, headers=auth_headers(admin))
    assert response.json()["total"] == 1


def test_cannot_create_appointment_across_clinics(client: TestClient, db_session: Session, clinic) -> None:
    """A clinic admin cannot book an appointment using another clinic's therapist or patient."""
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    my_patient = make_patient(db_session, clinic)
    other_therapist = make_therapist(db_session, other_clinic, email="other-t@example.com")

    response = client.post(APPOINTMENTS_URL, json=_payload(other_therapist, my_patient), headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "THERAPIST_NOT_FOUND"
