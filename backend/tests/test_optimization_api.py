"""Tests for the /api/v1/optimization endpoints - full request lifecycle, acceptance, staleness
protection, RBAC, and clinic isolation. Travel time is a deterministic fake (never a real network
call) so results are reproducible without any external routing/geocoding service."""

import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.appointment import Appointment, AppointmentStatus
from app.models.clinic import Clinic
from app.models.user import User
from app.services.routing import RouteResult
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

OPT_URL = "/api/v1/optimization"

NEXT_MONDAY = date(2026, 8, 24)
assert NEXT_MONDAY.weekday() == 0


class _DeterministicFakeRouting:
    """duration_seconds/distance_meters are a simple deterministic function of the raw
    coordinates, so nearby points are always cheaper than far ones and every test can compute
    the exact expected numbers by hand."""

    def route(self, *, origin_lat, origin_lng, dest_lat, dest_lng):
        seconds = (abs(origin_lat - dest_lat) + abs(origin_lng - dest_lng)) * 100_000
        return RouteResult(distance_meters=seconds * 10, duration_seconds=seconds)

    def route_matrix(self, *, points):
        size = len(points)
        matrix = []
        for i in range(size):
            row = []
            for j in range(size):
                if i == j:
                    row.append(None)
                else:
                    row.append(
                        self.route(
                            origin_lat=points[i][0],
                            origin_lng=points[i][1],
                            dest_lat=points[j][0],
                            dest_lng=points[j][1],
                        )
                    )
            matrix.append(row)
        return matrix


@pytest.fixture(autouse=True)
def _deterministic_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _DeterministicFakeRouting())


def _setup_day_schedule(db_session: Session, clinic):
    """Therapist home near Patient B; Patient A and Patient C are near each other but far from
    home/B - poor original chronological order (A@9, B@10, C@11) should be improved."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0000, home_longitude=-74.0000)
    make_weekday_availability(db_session, therapist)

    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.0030, longitude=-74.0000)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.0000, longitude=-74.0001, zip_code="07031")
    patient_c = make_patient(db_session, clinic, first_name="C", latitude=40.0031, longitude=-74.0000, zip_code="07032")

    make_appointment(
        db_session,
        clinic,
        patient=patient_a,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=patient_b,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=patient_c,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(11, 0),
    )

    return admin, therapist, (patient_a, patient_b, patient_c)


def test_day_schedule_optimization_full_lifecycle(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist, _patients = _setup_day_schedule(db_session, clinic)

    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert create_resp.status_code == 201
    request_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "COMPLETED"  # sync_optimization_tasks runs it inline

    status_resp = client.get(f"{OPT_URL}/requests/{request_id}", headers=auth_headers(admin))
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "COMPLETED"
    assert status_resp.json()["completed_at"] is not None

    recs_resp = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin))
    assert recs_resp.status_code == 200
    recs = recs_resp.json()
    assert len(recs) == 1
    rec = recs[0]
    assert rec["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert rec["total_drive_minutes"] > 0
    assert rec["time_saved_minutes"] > 0  # the poor A-B-C order should be improvable
    assert "appointments" in rec["recommendation_data"]

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200
    accept_body = accept_resp.json()
    assert accept_body["recommendation"]["id"] == rec["id"]
    assert accept_body["recommendation"]["accepted_at"] is not None
    assert len(accept_body["appointment_ids"]) > 0

    # The DB should reflect the moved appointments' new times.
    moved_ids = {uuid.UUID(a["appointment_id"]) for a in rec["recommendation_data"]["appointments"]}
    for appt_id in moved_ids:
        db_session.refresh(db_session.get(Appointment, appt_id))
    appointments = db_session.query(Appointment).filter(Appointment.id.in_(moved_ids)).all()
    changes = {c["appointment_id"]: c["new_start_time"] for c in rec["recommendation_data"]["appointments"]}
    for appt in appointments:
        assert appt.start_time.isoformat() == changes[str(appt.id)]

    # Accepting again is rejected - a recommendation can only be accepted once.
    second_accept = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert second_accept.status_code == 409


def test_day_schedule_optimization_no_appointments_is_completed_with_no_changes(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "COMPLETED"

    recs = client.get(f"{OPT_URL}/requests/{resp.json()['id']}/recommendations", headers=auth_headers(admin)).json()
    assert len(recs) == 1
    # "No appointments to optimize" is trivially fine, not a failure to find a schedule.
    assert recs[0]["solver_status"] == "OPTIMAL"
    assert recs[0]["reason_codes"] == ["NO_APPOINTMENTS"]


def test_day_schedule_optimization_fails_clearly_when_patient_not_geocoded(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)  # no latitude/longitude
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "FAILED"
    assert "geocoded" in resp.json()["error_message"].lower()


def test_accept_rejects_stale_recommendation_when_appointment_cancelled_first(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist, patients = _setup_day_schedule(db_session, clinic)

    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = create_resp.json()["id"]
    rec = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()[0]

    # Cancel one of the appointments the recommendation was computed against - the underlying
    # schedule has now changed since the recommendation was generated.
    changed_id = uuid.UUID(rec["recommendation_data"]["appointments"][0]["appointment_id"])
    appt = db_session.get(Appointment, changed_id)
    appt.status = AppointmentStatus.CANCELLED
    db_session.commit()

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 400
    assert accept_resp.json()["error"]["code"] == "STALE_RECOMMENDATION"

    # The cancelled appointment must not have been silently un-cancelled or moved.
    db_session.refresh(appt)
    assert appt.status == AppointmentStatus.CANCELLED


def test_new_patient_placement_full_lifecycle(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    new_patient = make_patient(
        db_session, clinic, first_name="New", latitude=40.001, longitude=-74.001, visit_duration_minutes=45
    )

    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "NEW_PATIENT_PLACEMENT",
            "therapist_id": str(therapist.id),
            "target_date": str(NEXT_MONDAY),
            "patient_id": str(new_patient.id),
        },
        headers=auth_headers(admin),
    )
    assert create_resp.status_code == 201
    request_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "COMPLETED"
    assert create_resp.json()["new_appointment_duration_minutes"] == 45

    recs = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()
    assert len(recs) >= 1
    rec = recs[0]
    assert rec["solver_status"] == "FEASIBLE"
    data = rec["recommendation_data"]
    assert data["patient_id"] == str(new_patient.id)

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200
    appointment_ids = accept_resp.json()["appointment_ids"]
    assert len(appointment_ids) == 1

    created = db_session.get(Appointment, uuid.UUID(appointment_ids[0]))
    assert created.patient_id == new_patient.id
    assert created.therapist_id == therapist.id
    assert created.status == AppointmentStatus.SCHEDULED


def test_new_patient_placement_requires_a_duration(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic, latitude=40.0, longitude=-74.0)  # no visit_duration_minutes

    resp = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "NEW_PATIENT_PLACEMENT",
            "therapist_id": str(therapist.id),
            "target_date": str(NEXT_MONDAY),
            "patient_id": str(patient.id),
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DURATION_REQUIRED"


def test_therapist_can_request_optimization_only_for_own_schedule(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    _admin, therapist_a, _ = _setup_day_schedule(db_session, clinic)
    therapist_b = make_therapist(db_session, clinic, email="other@example.com")
    make_weekday_availability(db_session, therapist_b)

    therapist_a_user = db_session.get(User, therapist_a.user_id)

    resp_own = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "DAY_SCHEDULE_OPTIMIZATION",
            "therapist_id": str(therapist_a.id),
            "target_date": str(NEXT_MONDAY),
        },
        headers=auth_headers(therapist_a_user),
    )
    assert resp_own.status_code == 201

    resp_other = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "DAY_SCHEDULE_OPTIMIZATION",
            "therapist_id": str(therapist_b.id),
            "target_date": str(NEXT_MONDAY),
        },
        headers=auth_headers(therapist_a_user),
    )
    assert resp_other.status_code == 404


def test_system_admin_cannot_access_optimization(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist, _ = _setup_day_schedule(db_session, clinic)
    system_admin = make_user(db_session, None, email="sysadmin@example.com", role=UserRole.SYSTEM_ADMIN)

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(system_admin),
    )
    assert resp.status_code == 403


def test_clinic_isolation_on_requests_and_recommendations(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist, _ = _setup_day_schedule(db_session, clinic)
    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = create_resp.json()["id"]

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    other_admin = make_user(db_session, other_clinic, email="other-admin@example.com", role=UserRole.CLINIC_ADMIN)

    get_resp = client.get(f"{OPT_URL}/requests/{request_id}", headers=auth_headers(other_admin))
    assert get_resp.status_code == 404

    recs_resp = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(other_admin))
    assert recs_resp.status_code == 404

    # Cross-clinic therapist_id in a create request also 404s, not a leak of another clinic's therapist.
    create_cross = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(other_admin),
    )
    assert create_cross.status_code == 404
