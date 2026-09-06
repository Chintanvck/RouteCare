"""Tests for GET /api/v1/analytics/optimization-impact - only ACCEPTED recommendations with a real
before/after comparison ever count as savings. Rejected recommendations and What-If evaluations/
applies (which never persist an OptimizationRecommendation at all) must never leak in.

accepted_at/rejected_at are stamped with the real current time (not the schedule's target_date),
so these tests filter by period="today" rather than a fixed calendar week."""

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

ANALYTICS_URL = "/api/v1/analytics"
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


def _today_params(**overrides) -> dict:
    params = {"period": "today"}
    params.update(overrides)
    return params


def _setup_day_schedule(db_session: Session, clinic):
    """A 3-appointment day laid out so DAY_SCHEDULE_OPTIMIZATION finds a genuine improvement -
    same shape as tests/test_recommendation_workflow.py's fixture."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0000, home_longitude=-74.0000)
    make_weekday_availability(db_session, therapist)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.0030, longitude=-74.0000)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.0000, longitude=-74.0001, zip_code="07031")
    patient_c = make_patient(db_session, clinic, first_name="C", latitude=40.0031, longitude=-74.0000, zip_code="07032")
    make_appointment(
        db_session, clinic, patient=patient_a, therapist=therapist, created_by=admin.id,
        scheduled_date=NEXT_MONDAY, start_time=time(9, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_b, therapist=therapist, created_by=admin.id,
        scheduled_date=NEXT_MONDAY, start_time=time(10, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_c, therapist=therapist, created_by=admin.id,
        scheduled_date=NEXT_MONDAY, start_time=time(11, 0),
    )
    return admin, therapist


def _create_and_get_day_recommendation(client: TestClient, admin, therapist):
    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = create_resp.json()["id"]
    rec = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()[0]
    return request_id, rec


def test_impact_is_empty_without_any_accepted_recommendation(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(f"{ANALYTICS_URL}/optimization-impact", params=_today_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendations_accepted"] == 0
    assert body["total_time_saved_minutes"] is None
    assert body["total_miles_saved"] is None
    assert body["percentage_improvement"] is None
    assert body["recent_examples"] == []


def test_accepted_day_schedule_recommendation_counts_as_savings(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)
    assert rec["time_saved_minutes"] is not None  # sanity: this fixture must actually find a saving

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200

    resp = client.get(f"{ANALYTICS_URL}/optimization-impact", params=_today_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendations_accepted"] == 1
    assert body["recommendations_with_savings"] == 1
    assert body["total_time_saved_minutes"] == pytest.approx(rec["time_saved_minutes"], abs=0.1)
    assert body["percentage_improvement"] is not None
    assert len(body["recent_examples"]) == 1
    example = body["recent_examples"][0]
    assert example["after_drive_minutes"] + example["time_saved_minutes"] == pytest.approx(
        example["before_drive_minutes"], abs=0.1
    )


def test_rejected_recommendation_never_counted(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)

    reject_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/reject", headers=auth_headers(admin)
    )
    assert reject_resp.status_code == 200

    resp = client.get(f"{ANALYTICS_URL}/optimization-impact", params=_today_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendations_accepted"] == 0
    assert body["total_time_saved_minutes"] is None


def test_what_if_apply_never_appears_in_optimization_impact(client: TestClient, db_session: Session, clinic) -> None:
    """apply_what_if never creates an OptimizationRequest/Recommendation at all - it just mutates
    an appointment directly - so it must be structurally impossible for it to show up here."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic, latitude=40.001, longitude=-74.0)
    appt = make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=NEXT_MONDAY, start_time=time(9, 0),
    )

    apply_resp = client.post(
        f"{OPT_URL}/what-if/apply",
        json={
            "scenario_type": "MOVE",
            "appointment_id": str(appt.id),
            "new_scheduled_date": str(NEXT_MONDAY),
            "new_start_time": "10:00:00",
        },
        headers=auth_headers(admin),
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["applied"] is True

    resp = client.get(f"{ANALYTICS_URL}/optimization-impact", params=_today_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    assert resp.json()["recommendations_accepted"] == 0


def test_new_patient_placement_accepted_counts_as_activity_not_savings(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    """NEW_PATIENT_PLACEMENT recommendations have no before/after comparison (time_saved_minutes is
    always None) - accepting one is real optimization activity, but must never inflate the savings
    numbers."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    new_patient = make_patient(
        db_session, clinic, first_name="New", latitude=40.001, longitude=-74.0, visit_duration_minutes=45
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
    request_id = create_resp.json()["id"]
    recs = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()
    assert recs, "fixture must produce at least one feasible placement"
    rec = recs[0]
    assert rec["time_saved_minutes"] is None  # sanity: marginal-only, no "before" state

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200

    resp = client.get(f"{ANALYTICS_URL}/optimization-impact", params=_today_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendations_accepted"] == 1
    assert body["recommendations_with_savings"] == 0
    assert body["total_time_saved_minutes"] is None
    assert body["recent_examples"] == []
