"""Tests for GET /api/v1/analytics/efficiency - gap/travel-time math and the "don't count breaks
as inefficient gaps" rule."""

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
    make_therapist_availability,
    make_user,
)

ANALYTICS_URL = "/api/v1/analytics"
MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


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


def _params(**overrides) -> dict:
    params = {"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY)}
    params.update(overrides)
    return params


def test_insufficient_data_flag_below_threshold(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    resp = client.get(f"{ANALYTICS_URL}/efficiency", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_size"] == 1
    assert body["has_sufficient_data"] is False


def test_gap_excludes_declared_break_window(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
    # A declared lunch break exactly spanning the gap between the two appointments below.
    make_therapist_availability(
        db_session, therapist, day_of_week=0, start_time=time(11, 0), end_time=time(12, 0), is_available=False
    )
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(10, 0), duration_minutes=60,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(12, 0), duration_minutes=60,
    )

    resp = client.get(f"{ANALYTICS_URL}/efficiency", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    # Raw gap is 60 minutes (11:00-12:00), entirely covered by the declared break -> 0 effective gap.
    assert resp.json()["average_gap_minutes"] == 0.0


def test_gap_without_a_break_counts_in_full(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(10, 0), duration_minutes=60,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(12, 0), duration_minutes=60,
    )

    resp = client.get(f"{ANALYTICS_URL}/efficiency", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    assert resp.json()["average_gap_minutes"] == pytest.approx(60.0)


def test_partial_break_overlap_only_subtracts_the_overlapping_portion(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
    # Break only covers the first half of the 60-minute gap.
    make_therapist_availability(
        db_session, therapist, day_of_week=0, start_time=time(11, 0), end_time=time(11, 30), is_available=False
    )
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(10, 0), duration_minutes=60,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(12, 0), duration_minutes=60,
    )

    resp = client.get(f"{ANALYTICS_URL}/efficiency", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    assert resp.json()["average_gap_minutes"] == pytest.approx(30.0)


def test_average_travel_between_appointments_excludes_home_legs(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_therapist_availability(db_session, therapist, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
    # home->A and A->B legs are both 0.001deg (100s); B->home would be 0.002deg but is never
    # traveled within the working day, so only ONE inter-appointment leg (A->B) should count.
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.001, longitude=-74.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.002, longitude=-74.0, zip_code="07031")
    make_appointment(
        db_session, clinic, patient=patient_a, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_b, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(11, 0),
    )

    resp = client.get(f"{ANALYTICS_URL}/efficiency", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    expected_leg_minutes = round(100 / 60, 1)
    assert body["average_travel_minutes_between_appointments"] == pytest.approx(expected_leg_minutes, abs=0.05)
    # Total driving DOES include both home-adjacent legs - a different number from the average above.
    assert body["total_drive_minutes"] > body["average_travel_minutes_between_appointments"]


def test_efficiency_unknown_therapist_id_404(client: TestClient, db_session: Session, clinic) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(
        f"{ANALYTICS_URL}/efficiency", params=_params(therapist_id=str(uuid.uuid4())), headers=auth_headers(admin)
    )

    assert resp.status_code == 404
