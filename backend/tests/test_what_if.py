"""Tests for /api/v1/optimization/what-if and .../what-if/apply.

`evaluate_what_if` must never write to the database, regardless of scenario type or feasibility.
`apply_what_if` must revalidate against the live database and reject if the schedule changed since
the scenario was calculated - it never trusts a precomputed check."""

import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.appointment import Appointment, AppointmentStatus
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
NEXT_TUESDAY = date(2026, 8, 25)
assert NEXT_MONDAY.weekday() == 0


class _DeterministicFakeRouting:
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


@pytest.fixture(autouse=True)
def _deterministic_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _DeterministicFakeRouting())


def _setup(db_session: Session, clinic):
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    # A is a deliberate detour off the direct home->B line (not colinear with home/B), so
    # visiting A clearly costs more total travel than skipping it - avoids a coincidental
    # near-tie between "with A" and "without A" that a colinear layout would produce.
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.001, longitude=-74.05)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.002, longitude=-74.002, zip_code="07031")
    appt_a = make_appointment(
        db_session,
        clinic,
        patient=patient_a,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )
    appt_b = make_appointment(
        db_session,
        clinic,
        patient=patient_b,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(13, 0),
    )
    return admin, therapist, patient_a, patient_b, appt_a, appt_b


# --------------------------------------------------------------------------
# MOVE - evaluate
# --------------------------------------------------------------------------


def test_what_if_move_feasible_same_day_does_not_modify_appointment(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin, _therapist, _pa, _pb, appt_a, _appt_b = _setup(db_session, clinic)
    original_start = appt_a.start_time

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "10:00:00",
        },
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is True
    assert body["conflicts"] == []
    assert len(body["days"]) == 1
    assert body["affected_appointment_ids"] == [str(appt_a.id)]
    assert body["total_time_impact_minutes"] is not None

    db_session.refresh(appt_a)
    assert appt_a.start_time == original_start


def test_what_if_move_infeasible_reports_conflict_and_does_not_modify(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin, _therapist, _pa, _pb, appt_a, appt_b = _setup(db_session, clinic)

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "13:15:00",
        },
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is False
    assert len(body["conflicts"]) > 0
    assert body["days"] == []
    assert body["total_time_impact_minutes"] is None

    db_session.refresh(appt_a)
    db_session.refresh(appt_b)
    assert appt_a.start_time == time(9, 0)
    assert appt_b.start_time == time(13, 0)


def test_what_if_move_cross_day_reports_both_origin_and_destination(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin, _therapist, _pa, _pb, appt_a, _appt_b = _setup(db_session, clinic)

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_TUESDAY),
            "new_start_time": "09:00:00",
        },
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is True
    dates = {d["target_date"] for d in body["days"]}
    assert dates == {str(NEXT_MONDAY), str(NEXT_TUESDAY)}

    db_session.refresh(appt_a)
    assert appt_a.scheduled_date == NEXT_MONDAY


def test_what_if_move_with_duration_change(client: TestClient, db_session: Session, clinic) -> None:
    admin, _therapist, _pa, _pb, appt_a, _appt_b = _setup(db_session, clinic)

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "09:00:00",
            "new_duration_minutes": 90,
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["feasible"] is True

    db_session.refresh(appt_a)
    assert appt_a.duration_minutes == 45  # unchanged - evaluate never applies anything


def test_what_if_unknown_appointment_404s(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(uuid.uuid4()),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "09:00:00",
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# ADD - evaluate
# --------------------------------------------------------------------------


def test_what_if_add_feasible_does_not_create_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, _pa, _pb, _appt_a, _appt_b = _setup(db_session, clinic)
    new_patient = make_patient(
        db_session, clinic, first_name="New", latitude=40.003, longitude=-74.003, zip_code="07032"
    )
    count_before = db_session.query(Appointment).count()

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "ADD",
            "patient_id": str(new_patient.id),
            "therapist_id": str(therapist.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "11:00:00",
            "new_duration_minutes": 45,
        },
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is True
    assert len(body["days"]) == 1
    assert body["days"][0]["proposed_drive_minutes"] >= body["days"][0]["current_drive_minutes"]
    assert db_session.query(Appointment).count() == count_before


def test_what_if_add_infeasible_when_overlapping(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, _pa, _pb, _appt_a, _appt_b = _setup(db_session, clinic)
    new_patient = make_patient(
        db_session, clinic, first_name="New", latitude=40.003, longitude=-74.003, zip_code="07032"
    )

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "ADD",
            "patient_id": str(new_patient.id),
            "therapist_id": str(therapist.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "13:15:00",
            "new_duration_minutes": 45,
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is False
    assert len(body["conflicts"]) > 0


# --------------------------------------------------------------------------
# REMOVE - evaluate
# --------------------------------------------------------------------------


def test_what_if_remove_does_not_cancel_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin, _therapist, _pa, _pb, appt_a, _appt_b = _setup(db_session, clinic)

    resp = client.post(
        f"{OPT_URL}/what-if",
        json={"scenario_type": "REMOVE", "appointment_id": str(appt_a.id)},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is True
    assert len(body["days"]) == 1
    assert body["days"][0]["proposed_drive_minutes"] <= body["days"][0]["current_drive_minutes"]

    db_session.refresh(appt_a)
    assert appt_a.status == AppointmentStatus.SCHEDULED


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------


def test_what_if_apply_move_actually_reschedules(client: TestClient, db_session: Session, clinic) -> None:
    admin, _therapist, _pa, _pb, appt_a, _appt_b = _setup(db_session, clinic)

    resp = client.post(
        f"{OPT_URL}/what-if/apply",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "10:00:00",
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["appointment_id"] == str(appt_a.id)

    db_session.refresh(appt_a)
    assert appt_a.start_time == time(10, 0)


def test_what_if_apply_add_actually_creates_appointment(client: TestClient, db_session: Session, clinic) -> None:
    admin, therapist, _pa, _pb, _appt_a, _appt_b = _setup(db_session, clinic)
    new_patient = make_patient(
        db_session, clinic, first_name="New", latitude=40.003, longitude=-74.003, zip_code="07032"
    )
    count_before = db_session.query(Appointment).count()

    resp = client.post(
        f"{OPT_URL}/what-if/apply",
        json={
            "scenario_type": "ADD",
            "patient_id": str(new_patient.id),
            "therapist_id": str(therapist.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "11:00:00",
            "new_duration_minutes": 45,
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True

    assert db_session.query(Appointment).count() == count_before + 1
    created = db_session.get(Appointment, uuid.UUID(body["appointment_id"]))
    assert created.patient_id == new_patient.id
    assert created.status == AppointmentStatus.SCHEDULED


def test_what_if_apply_remove_actually_cancels(client: TestClient, db_session: Session, clinic) -> None:
    admin, _therapist, _pa, _pb, appt_a, _appt_b = _setup(db_session, clinic)

    resp = client.post(
        f"{OPT_URL}/what-if/apply",
        json={"scenario_type": "REMOVE", "appointment_id": str(appt_a.id)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is True

    db_session.refresh(appt_a)
    assert appt_a.status == AppointmentStatus.CANCELLED


def test_what_if_apply_rejects_stale_scenario(client: TestClient, db_session: Session, clinic) -> None:
    """Something else changes the schedule between evaluate and apply - apply must revalidate
    against the live database, not trust the earlier evaluate result."""
    admin, _therapist, _pa, _pb, appt_a, appt_b = _setup(db_session, clinic)

    evaluate_resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "11:00:00",
        },
        headers=auth_headers(admin),
    )
    assert evaluate_resp.json()["feasible"] is True

    # The schedule changes in the meantime: B moves to 11:00, blocking A's proposed slot. B's
    # *current* time (13:00) doesn't conflict with A's current time (9:00), so this PATCH succeeds.
    move_b_resp = client.patch(
        f"/api/v1/appointments/{appt_b.id}", json={"start_time": "11:00:00"}, headers=auth_headers(admin)
    )
    assert move_b_resp.status_code == 200

    apply_resp = client.post(
        f"{OPT_URL}/what-if/apply",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt_a.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "11:00:00",
        },
        headers=auth_headers(admin),
    )
    assert apply_resp.status_code == 200
    body = apply_resp.json()
    assert body["applied"] is False
    assert "changed" in body["message"].lower()

    db_session.refresh(appt_a)
    assert appt_a.start_time == time(9, 0)  # never moved
