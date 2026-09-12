"""
RouteCare AI - Appointment status workflow (explicit, not inferred).

Consolidates the specific behaviors requested when this was reviewed: status
only ever changes because someone explicitly set it via PATCH /appointments/
{id} or DELETE (-> CANCELLED) - never because a scheduled_date/start_time
happened to be in the past. `test_appointments_crud.py` and
`test_appointments_security.py` already cover the general PATCH/DELETE
mechanics and the therapist-can-only-touch-own-appointment restriction; this
file is the single place that exercises the status state machine itself
(SCHEDULED -> {COMPLETED, NO_SHOW, CANCELLED}) end to end, including the
"nothing happens automatically" and "dashboard counts reflect the persisted
column" guarantees.
"""

from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.appointment import AppointmentStatus
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

APPOINTMENTS_URL = "/api/v1/appointments"
ANALYTICS_URL = "/api/v1/analytics"

# A fixed Monday, unrelated to whenever the suite actually runs.
MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0

# Deliberately far in the past relative to any plausible "today" this suite ever runs under.
PAST_MONDAY = date(2020, 1, 6)
assert PAST_MONDAY.weekday() == 0


def _setup(db_session: Session, clinic):
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    return admin, therapist, patient


# ============================================================
# Therapist can mark their own appointments COMPLETED / NO_SHOW
# ============================================================


def test_therapist_can_mark_own_appointment_completed(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"status": "COMPLETED"}, headers=auth_headers(therapist.user)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_therapist_can_mark_own_appointment_no_show(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"status": "NO_SHOW"}, headers=auth_headers(therapist.user)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NO_SHOW"


def test_office_scheduler_can_mark_appointment_status(client: TestClient, db_session: Session, clinic) -> None:
    """Clinic-level roles keep whatever status-change access they already had for the rest of the
    appointment - nothing about the status field should be more restrictive for them than before."""
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=scheduler.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"status": "NO_SHOW"}, headers=auth_headers(scheduler)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NO_SHOW"


# ============================================================
# A therapist must not be able to change another therapist's status
# ============================================================


def test_therapist_cannot_change_status_of_another_therapists_appointment(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist_b, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"status": "COMPLETED"}, headers=auth_headers(therapist_a.user)
    )
    assert response.status_code == 404

    # Nothing actually changed on the row a wrong-therapist request 404'd against.
    unchanged = db_session.get(type(appt), appt.id)
    assert unchanged.status == AppointmentStatus.SCHEDULED


def test_unauthenticated_request_cannot_change_status(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.patch(f"{APPOINTMENTS_URL}/{appt.id}", json={"status": "COMPLETED"})
    assert response.status_code == 401

    unchanged = db_session.get(type(appt), appt.id)
    assert unchanged.status == AppointmentStatus.SCHEDULED


# ============================================================
# No automatic inference from scheduled_date/start_time
# ============================================================


def test_past_scheduled_appointment_does_not_auto_become_no_show(
    client: TestClient, db_session: Session, clinic
) -> None:
    """A SCHEDULED appointment whose date has long since passed must still read back as SCHEDULED -
    nothing in the read path (or any background process) is allowed to reclassify it just because
    `scheduled_date` is now in the past. Automatic no-show detection is explicitly out of scope."""
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=PAST_MONDAY, start_time=time(9, 0),
    )
    assert appt.status == AppointmentStatus.SCHEDULED

    response = client.get(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["status"] == "SCHEDULED"

    # Re-fetch from a fresh query too, not just the cached ORM instance.
    db_session.expire_all()
    reloaded = db_session.get(type(appt), appt.id)
    assert reloaded.status == AppointmentStatus.SCHEDULED


def test_past_scheduled_appointment_counts_as_scheduled_in_dashboard(
    client: TestClient, db_session: Session, clinic
) -> None:
    """The overview endpoint's status breakdown must reflect the persisted column even for a date
    range entirely in the past - it must never bucket an old SCHEDULED row under no_show_appointments
    just because its date has elapsed."""
    admin, therapist, patient = _setup(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=PAST_MONDAY, start_time=time(9, 0), status=AppointmentStatus.SCHEDULED,
    )

    response = client.get(
        f"{ANALYTICS_URL}/overview",
        params={
            "period": "custom",
            "start_date": str(PAST_MONDAY),
            "end_date": str(PAST_MONDAY + timedelta(days=6)),
        },
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scheduled_appointments"] == 1
    assert body["no_show_appointments"] == 0
    assert body["completed_appointments"] == 0


# ============================================================
# Dashboard counts match persisted status, across all four values
# ============================================================


def test_dashboard_status_counts_match_persisted_values(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, patient = _setup(db_session, clinic)

    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0), status=AppointmentStatus.SCHEDULED,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(10, 0), status=AppointmentStatus.COMPLETED,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(11, 0), status=AppointmentStatus.CANCELLED,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(12, 0), status=AppointmentStatus.NO_SHOW,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(13, 0), status=AppointmentStatus.NO_SHOW,
    )

    response = client.get(
        f"{ANALYTICS_URL}/overview",
        params={"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY)},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scheduled_appointments"] == 1
    assert body["completed_appointments"] == 1
    assert body["cancelled_appointments"] == 1
    assert body["no_show_appointments"] == 2
    assert body["total_appointments"] == 5

    # Cross-check directly against the database, not just against the fixture's own bookkeeping.
    from app.models.appointment import Appointment

    db_counts = {
        status: db_session.query(Appointment).filter(
            Appointment.clinic_id == clinic.id, Appointment.status == status
        ).count()
        for status in AppointmentStatus
    }
    assert db_counts[AppointmentStatus.SCHEDULED] == body["scheduled_appointments"]
    assert db_counts[AppointmentStatus.COMPLETED] == body["completed_appointments"]
    assert db_counts[AppointmentStatus.CANCELLED] == body["cancelled_appointments"]
    assert db_counts[AppointmentStatus.NO_SHOW] == body["no_show_appointments"]


def test_cancel_endpoint_sets_cancelled_not_no_show_or_completed(
    client: TestClient, db_session: Session, clinic
) -> None:
    """DELETE (cancel) must always land on CANCELLED specifically - never silently reuse NO_SHOW or
    COMPLETED as a stand-in status."""
    admin, therapist, patient = _setup(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.delete(f"{APPOINTMENTS_URL}/{appt.id}", headers=auth_headers(admin))
    assert response.status_code == 204

    db_session.expire_all()
    reloaded = db_session.get(type(appt), appt.id)
    assert reloaded.status == AppointmentStatus.CANCELLED
