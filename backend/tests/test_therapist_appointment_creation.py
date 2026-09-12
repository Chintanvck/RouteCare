"""
RouteCare AI - Therapist self-service appointment creation.

Regression coverage for the fix that let a THERAPIST create appointments
again. Before this fix, POST /appointments and POST /appointments/validate
were gated to CLINIC_ADMIN/OFFICE_SCHEDULER only (`_WRITE_ROLES` in
app.modules.scheduling.router), so a THERAPIST got a blanket 403 regardless
of payload - the "New Appointment" feature was fully unavailable to them.

The fix extends `_WRITE_ROLES` to include THERAPIST and threads the same
`restrict_to_therapist_id` mechanism already used for get/list/update/
cancel through create and validate too - but NOT all the way down to the
patient lookup:
- `therapist_id` in the request body is silently replaced by the caller's
  own id when they're a THERAPIST (appointment_service.create_appointment) -
  matching list_appointments' existing "can't widen access by changing an
  id in the request" precedent, so forging another therapist's id has no
  effect.
- the patient only has to belong to the same clinic - NOT already be
  "assigned" (i.e. have a prior Appointment with this therapist). An
  earlier version of this fix reused patient_service's assignment-via-
  appointment restriction here too, which turned out to be circular: it
  required an existing Appointment to authorize creating the very first
  one. See test_first_appointment_establishes_therapist_patient_relationship
  below for the regression this created and how it's resolved - a THERAPIST
  can freely pick any same-clinic patient to create a first appointment
  with themselves; patient_service's stricter "already assigned" rule
  still applies everywhere a therapist *views* their patient list.

This file is the single place exercising that whole story end to end;
test_appointments_security.py and test_appointment_status.py cover the
already-existing get/list/update/cancel/status-change restrictions this
fix deliberately left untouched.
"""

from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import pytest

from app.core.permissions import UserRole
from app.models.appointment import Appointment
from app.models.clinic import Clinic
from app.services.routing import RouteResult
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

APPOINTMENTS_URL = "/api/v1/appointments"
VALIDATE_URL = f"{APPOINTMENTS_URL}/validate"
PATIENTS_URL = "/api/v1/patients"
OPT_URL = "/api/v1/optimization"


class _DeterministicFakeRouting:
    """Same shape as test_optimization_api.py's - a real (if synthetic) distance function so an
    optimization run over a newly-created appointment can actually complete instead of tripping
    "no route" fallbacks."""

    def route(self, *, origin_lat, origin_lng, dest_lat, dest_lng):
        seconds = (abs(origin_lat - dest_lat) + abs(origin_lng - dest_lng)) * 100_000
        return RouteResult(distance_meters=seconds * 10, duration_seconds=seconds)

    def route_matrix(self, *, points):
        size = len(points)
        matrix = []
        for i in range(size):
            row = []
            for j in range(size):
                row.append(
                    None
                    if i == j
                    else self.route(
                        origin_lat=points[i][0], origin_lng=points[i][1], dest_lat=points[j][0], dest_lng=points[j][1]
                    )
                )
            matrix.append(row)
        return matrix


@pytest.fixture()
def deterministic_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _DeterministicFakeRouting())

# A fixed Monday, unrelated to whenever the suite actually runs.
MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


def _payload(*, therapist_id, patient_id, start_time="14:00:00", scheduled_date=MONDAY, duration_minutes=45):
    return {
        "patient_id": str(patient_id),
        "therapist_id": str(therapist_id),
        "scheduled_date": str(scheduled_date),
        "start_time": start_time,
        "duration_minutes": duration_minutes,
    }


def _assign_patient(db_session: Session, clinic, *, therapist, patient, created_by):
    """Gives a therapist an existing relationship with a patient the way the real app does - a
    prior appointment (created by an admin/scheduler, as an initial assignment normally would be).
    Mirrors patient_service._active_patients_query's assignment-via-appointment rule."""
    return make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=created_by,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )


# ============================================================
# 1 & 2: therapist can see their own schedule / the create action is allowed
# ============================================================


def test_therapist_can_see_own_schedule(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.get(
        f"{APPOINTMENTS_URL}?start_date={MONDAY}&end_date={MONDAY}", headers=auth_headers(therapist.user)
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_therapist_role_is_no_longer_blocked_from_posting_appointments(
    client: TestClient, db_session: Session, clinic
) -> None:
    """The regression: THERAPIST must not receive a blanket 403 from the role check itself before
    any business logic runs - this is what "New Appointment" being unavailable actually looked
    like server-side. A well-formed request for the therapist's own, already-assigned patient must
    reach real validation and succeed (see test_therapist_can_create_appointment_for_own_patient
    for the full assertion); this test exists specifically to pin the role gate itself."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    _assign_patient(db_session, clinic, therapist=therapist, patient=patient, created_by=admin.id)

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id),
        headers=auth_headers(therapist.user),
    )
    assert response.status_code != 403


# ============================================================
# 3: therapist can create an appointment for their own (already-assigned) patient
# ============================================================


def test_therapist_can_create_appointment_for_own_patient(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    _assign_patient(db_session, clinic, therapist=therapist, patient=patient, created_by=admin.id)

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id),
        headers=auth_headers(therapist.user),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["therapist_id"] == str(therapist.id)
    assert body["patient_id"] == str(patient.id)
    assert body["status"] == "SCHEDULED"


def test_therapist_appointment_creation_validates_conflicts(
    client: TestClient, db_session: Session, clinic
) -> None:
    """The existing scheduling logic (overlap/working-hours checks) still runs for a
    therapist-created appointment - this isn't a shortcut path that skips validation."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    _assign_patient(db_session, clinic, therapist=therapist, patient=patient, created_by=admin.id)

    # Overlaps the existing 09:00-09:45 assignment appointment above.
    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id, start_time="09:15:00"),
        headers=auth_headers(therapist.user),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "APPOINTMENT_VALIDATION_FAILED"


def test_therapist_validate_endpoint_works_for_own_patient(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    _assign_patient(db_session, clinic, therapist=therapist, patient=patient, created_by=admin.id)

    response = client.post(
        VALIDATE_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id),
        headers=auth_headers(therapist.user),
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


# ============================================================
# 4: therapist cannot create an appointment assigned to another therapist
# ============================================================


def test_therapist_cannot_assign_new_appointment_to_another_therapist(
    client: TestClient, db_session: Session, clinic
) -> None:
    """Sending another therapist's id in the request must not create the appointment under that
    therapist - it's silently replaced with the caller's own id, so the row that actually gets
    created (if anything does) is never assigned to therapist B."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    make_weekday_availability(db_session, therapist_a)
    make_weekday_availability(db_session, therapist_b)
    patient = make_patient(db_session, clinic)
    _assign_patient(db_session, clinic, therapist=therapist_a, patient=patient, created_by=admin.id)

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist_b.id, patient_id=patient.id, start_time="15:00:00"),
        headers=auth_headers(therapist_a.user),
    )
    assert response.status_code == 201
    assert response.json()["therapist_id"] == str(therapist_a.id)

    # Therapist B's calendar must be completely untouched by A's forged request.
    b_appointments = db_session.query(Appointment).filter(Appointment.therapist_id == therapist_b.id).count()
    assert b_appointments == 0


def test_therapist_can_create_appointment_for_a_patient_primarily_seen_by_another_therapist(
    client: TestClient, db_session: Session, clinic
) -> None:
    """Patient authorization for scheduling is "same clinic," not "exclusively mine" - a patient
    already seeing therapist B (e.g. a different discipline, or covering) can still have a new
    appointment created with therapist A, as long as it's genuinely under A's own id. This is the
    explicit intended rule: only the therapist_id is locked to the caller, never the patient."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    make_weekday_availability(db_session, therapist_a)
    make_weekday_availability(db_session, therapist_b)
    patient_b = make_patient(db_session, clinic, first_name="PatientB")
    _assign_patient(db_session, clinic, therapist=therapist_b, patient=patient_b, created_by=admin.id)

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist_a.id, patient_id=patient_b.id, start_time="15:00:00"),
        headers=auth_headers(therapist_a.user),
    )
    assert response.status_code == 201
    assert response.json()["therapist_id"] == str(therapist_a.id)
    assert response.json()["patient_id"] == str(patient_b.id)


def test_therapist_validate_endpoint_evaluates_against_own_calendar_not_forged_one(
    client: TestClient, db_session: Session, clinic
) -> None:
    """The dry-run endpoint must not become a side-channel for probing another therapist's
    schedule - it applies the same therapist_id override as the real create. Proven here by giving
    therapist A (not B) a conflicting appointment at the proposed time: if the override didn't
    happen and B's (free) calendar were used instead, this would incorrectly report `valid: true`."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(db_session, clinic, email="a@example.com")
    therapist_b = make_therapist(db_session, clinic, email="b@example.com")
    make_weekday_availability(db_session, therapist_a)
    make_weekday_availability(db_session, therapist_b)
    patient = make_patient(db_session, clinic)
    _assign_patient(db_session, clinic, therapist=therapist_a, patient=patient, created_by=admin.id)  # 09:00-09:45

    response = client.post(
        VALIDATE_URL,
        json=_payload(therapist_id=therapist_b.id, patient_id=patient.id, start_time="09:15:00"),
        headers=auth_headers(therapist_a.user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("already has an appointment" in e.lower() for e in body["errors"])


# ============================================================
# 10: admin/scheduler retain clinic-wide scheduling
# ============================================================


def test_admin_can_still_create_appointment_for_any_therapist(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    response = client.post(
        APPOINTMENTS_URL, json=_payload(therapist_id=therapist.id, patient_id=patient.id), headers=auth_headers(admin)
    )
    assert response.status_code == 201
    assert response.json()["therapist_id"] == str(therapist.id)


def test_office_scheduler_can_still_create_appointment_for_any_therapist(
    client: TestClient, db_session: Session, clinic
) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id),
        headers=auth_headers(scheduler),
    )
    assert response.status_code == 201
    assert response.json()["therapist_id"] == str(therapist.id)


# ============================================================
# 11: cross-clinic isolation still holds for the newly-opened therapist path
# ============================================================


def test_therapist_cannot_create_appointment_using_another_clinics_patient(
    client: TestClient, db_session: Session, clinic
) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    other_patient = make_patient(db_session, other_clinic, email="other-p@example.com")

    response = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=other_patient.id),
        headers=auth_headers(therapist.user),
    )
    assert response.status_code == 404


# ============================================================
# 5 & 6: modify - own vs. another therapist's appointment
# ============================================================


def test_therapist_cannot_modify_another_therapists_appointment(
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
        f"{APPOINTMENTS_URL}/{appt.id}", json={"start_time": "10:00:00"}, headers=auth_headers(therapist_a.user)
    )
    assert response.status_code == 404

    db_session.expire_all()
    unchanged = db_session.get(Appointment, appt.id)
    assert unchanged.start_time == time(9, 0)


def test_therapist_can_modify_own_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.patch(
        f"{APPOINTMENTS_URL}/{appt.id}", json={"start_time": "10:00:00"}, headers=auth_headers(therapist.user)
    )
    assert response.status_code == 200
    assert response.json()["start_time"] == "10:00:00"


# ============================================================
# First appointment establishes the therapist-patient relationship
# ============================================================


def test_first_appointment_establishes_therapist_patient_relationship(
    client: TestClient, db_session: Session, clinic
) -> None:
    """Before the fix, patient_service's assignment-via-appointment restriction was also applied
    to appointment creation, so a therapist could never create the very first appointment for a
    patient - there was no Appointment yet to authorize it. This proves the fix: the patient starts
    out NOT visible to the therapist (patient_service.list_patients' normal, unchanged behavior),
    creating a first appointment succeeds, and the patient becomes visible immediately afterward
    through that same appointment - no separate assignment step, no schema change."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    # Before: not yet visible via the normal (assignment-restricted) patient list or detail fetch.
    before_list = client.get(PATIENTS_URL, headers=auth_headers(therapist.user))
    assert before_list.json()["total"] == 0
    before_get = client.get(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(therapist.user))
    assert before_get.status_code == 404

    create_resp = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id),
        headers=auth_headers(therapist.user),
    )
    assert create_resp.status_code == 201

    # After: visible everywhere a therapist's own patients normally show up.
    after_list = client.get(PATIENTS_URL, headers=auth_headers(therapist.user))
    assert after_list.json()["total"] == 1
    assert after_list.json()["items"][0]["id"] == str(patient.id)

    after_get = client.get(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(therapist.user))
    assert after_get.status_code == 200


def test_for_scheduling_param_widens_patient_list_only_when_requested(
    client: TestClient, db_session: Session, clinic
) -> None:
    """The `for_scheduling=true` opt-in (used by the New Appointment picker) lets a therapist see
    every active clinic patient, but only when explicitly asked for - the plain list call keeps
    today's "already assigned" restriction, so nothing else on the therapist's side gets wider by
    accident."""
    therapist = make_therapist(db_session, clinic)
    make_patient(db_session, clinic, first_name="Unrelated")

    default_resp = client.get(PATIENTS_URL, headers=auth_headers(therapist.user))
    assert default_resp.json()["total"] == 0

    scheduling_resp = client.get(f"{PATIENTS_URL}?for_scheduling=true", headers=auth_headers(therapist.user))
    assert scheduling_resp.json()["total"] == 1


def test_therapist_can_optimize_newly_assigned_patient(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks, deterministic_routing
) -> None:
    """Optimization filters appointments purely by clinic_id/therapist_id/scheduled_date/status
    (see optimization_service._compute_day_schedule_recommendation) - it never consults
    patient_service's assignment restriction at all. So a patient scheduled for the very first time
    via this fix participates in that therapist's optimization exactly like any other appointment,
    with no extra wiring needed."""
    therapist = make_therapist(db_session, clinic, home_latitude=40.0000, home_longitude=-74.0000)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic, latitude=40.0050, longitude=-74.0010)

    create_resp = client.post(
        APPOINTMENTS_URL,
        json=_payload(therapist_id=therapist.id, patient_id=patient.id, start_time="09:00:00"),
        headers=auth_headers(therapist.user),
    )
    assert create_resp.status_code == 201

    opt_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(MONDAY)},
        headers=auth_headers(therapist.user),
    )
    assert opt_resp.status_code == 201
    assert opt_resp.json()["status"] == "COMPLETED"

    recs = client.get(
        f"{OPT_URL}/requests/{opt_resp.json()['id']}/recommendations", headers=auth_headers(therapist.user)
    ).json()
    assert len(recs) == 1
    # An empty `{}` (not `{"appointments": [...]}`) is exactly what a NO_APPOINTMENTS/infeasible
    # result looks like (see optimization_service._infeasible_recommendation) - its presence here
    # proves the newly-created appointment was actually found, geocoded, and fed through the
    # solver, not skipped because the patient wasn't "assigned" yet.
    assert "appointments" in recs[0]["recommendation_data"]
    assert recs[0]["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert "NO_APPOINTMENTS" not in recs[0]["reason_codes"]
