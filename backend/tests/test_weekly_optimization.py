"""Tests for OptimizationMode.WEEK_SCHEDULE_OPTIMIZATION - orchestrates the existing day-schedule
optimizer once per day of the week rather than a separate algorithm. Covers: multiple days,
mixed successful/failed/no-feasible-solution days, and aggregation into one weekly response."""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
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


def test_weekly_optimization_produces_one_recommendation_per_day(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)

    # Monday: two appointments in a poor order (a real reorder opportunity).
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.003, longitude=-74.0)
    patient_c = make_patient(db_session, clinic, first_name="C", latitude=40.0, longitude=-74.0, zip_code="07031")
    patient_far = make_patient(
        db_session, clinic, first_name="Far", latitude=40.0031, longitude=-74.0, zip_code="07032"
    )
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
        patient=patient_far,
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

    # Tuesday: no appointments at all (should come back OPTIMAL/no-changes, not infeasible).
    # Wednesday-Sunday: also empty - weekday availability means Wed-Fri work, Sat/Sun don't.

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "WEEK_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "COMPLETED"
    request_id = resp.json()["id"]

    recs = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()
    # 7 days, exactly one recommendation each.
    assert len(recs) == 7
    by_date = {r["target_date"]: r for r in recs}
    assert len(by_date) == 7

    monday_rec = by_date[str(NEXT_MONDAY)]
    assert monday_rec["solver_status"] in ("OPTIMAL", "FEASIBLE")

    # Weekday-with-no-appointments day (Tuesday) - OPTIMAL, not INFEASIBLE.
    from datetime import timedelta

    tuesday = str(NEXT_MONDAY + timedelta(days=1))
    assert by_date[tuesday]["solver_status"] == "OPTIMAL"
    assert by_date[tuesday]["reason_codes"] == ["NO_APPOINTMENTS"]

    # Weekend day the therapist doesn't work at all - also just "no appointments," not an error.
    saturday = str(NEXT_MONDAY + timedelta(days=5))
    assert by_date[saturday]["solver_status"] == "OPTIMAL"


def test_weekly_optimization_one_bad_day_does_not_fail_the_whole_week(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)

    geocoded_patient = make_patient(db_session, clinic, first_name="Geocoded", latitude=40.001, longitude=-74.001)
    ungeocoded_patient = make_patient(db_session, clinic, first_name="Ungeocoded", zip_code="07031")  # no lat/long

    from datetime import timedelta

    tuesday = NEXT_MONDAY + timedelta(days=1)
    # Monday: fine, geocoded patient.
    make_appointment(
        db_session,
        clinic,
        patient=geocoded_patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )
    # Tuesday: an ungeocoded patient - this one day should fail, not the whole week.
    make_appointment(
        db_session,
        clinic,
        patient=ungeocoded_patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=tuesday,
        start_time=time(9, 0),
    )

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "WEEK_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "COMPLETED"  # the request itself succeeds even though one day failed

    recs = client.get(f"{OPT_URL}/requests/{resp.json()['id']}/recommendations", headers=auth_headers(admin)).json()
    by_date = {r["target_date"]: r for r in recs}

    assert by_date[str(NEXT_MONDAY)]["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert by_date[str(tuesday)]["solver_status"] == "ERROR"
    assert "geocoded" in by_date[str(tuesday)]["explanation"].lower()


def test_weekly_optimization_no_feasible_solution_day(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist, start_time=time(9, 0), end_time=time(9, 30))  # tiny window

    patient = make_patient(db_session, clinic, first_name="Tight", latitude=40.001, longitude=-74.001)
    # A 60-minute appointment jammed into a 30-minute working window - never fits.
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
        duration_minutes=60,
    )

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "WEEK_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    request_id = resp.json()["id"]

    recs = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()
    by_date = {r["target_date"]: r for r in recs}
    assert by_date[str(NEXT_MONDAY)]["solver_status"] == "INFEASIBLE"


def test_weekly_optimization_accepts_independently_per_day(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    """Each day's recommendation can be accepted/left alone independently - accepting Monday's
    proposal must not affect Tuesday's, and vice versa."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)

    from datetime import timedelta

    tuesday = NEXT_MONDAY + timedelta(days=1)

    # Monday: poor order, reorderable.
    m_a = make_patient(db_session, clinic, first_name="MA", latitude=40.003, longitude=-74.0)
    m_c = make_patient(db_session, clinic, first_name="MC", latitude=40.0, longitude=-74.0, zip_code="07031")
    m_far = make_patient(db_session, clinic, first_name="MFar", latitude=40.0031, longitude=-74.0, zip_code="07032")
    make_appointment(
        db_session,
        clinic,
        patient=m_a,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=m_far,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(10, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=m_c,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(11, 0),
    )

    # Tuesday: same poor-order pattern with different patients.
    t_a = make_patient(db_session, clinic, first_name="TA", latitude=40.003, longitude=-74.0, zip_code="07033")
    t_c = make_patient(db_session, clinic, first_name="TC", latitude=40.0, longitude=-74.0, zip_code="07034")
    t_far = make_patient(db_session, clinic, first_name="TFar", latitude=40.0031, longitude=-74.0, zip_code="07035")
    make_appointment(
        db_session,
        clinic,
        patient=t_a,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=tuesday,
        start_time=time(9, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=t_far,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=tuesday,
        start_time=time(10, 0),
    )
    make_appointment(
        db_session,
        clinic,
        patient=t_c,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=tuesday,
        start_time=time(11, 0),
    )

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "WEEK_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = resp.json()["id"]
    recs = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()
    by_date = {r["target_date"]: r for r in recs}
    monday_rec = by_date[str(NEXT_MONDAY)]
    tuesday_rec = by_date[str(tuesday)]

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{monday_rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200

    # Tuesday's recommendation is still accept-able (not blocked by Monday's acceptance).
    accept_tuesday_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{tuesday_rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_tuesday_resp.status_code == 200
