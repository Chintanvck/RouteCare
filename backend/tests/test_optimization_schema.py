"""Schema-focused tests for Phase 7's optimization model changes:
- marginal_drive_minutes/marginal_distance_miles (NEW_PATIENT_PLACEMENT-only detail, separate
  from total_drive_minutes which now means "the day's full total" for every mode).
- accepted_at/rejected_at integrity on OptimizationRecommendation (Phase 6's
  accepted_recommendation_id was removed - see app/models/optimization.py's docstring)."""

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


def test_day_schedule_recommendation_has_no_marginal_fields(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic, first_name="A", latitude=40.001, longitude=-74.001)
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
    rec = client.get(f"{OPT_URL}/requests/{resp.json()['id']}/recommendations", headers=auth_headers(admin)).json()[0]
    assert rec["marginal_drive_minutes"] is None
    assert rec["marginal_distance_miles"] is None
    assert rec["target_date"] == str(NEXT_MONDAY)


def test_new_patient_placement_reports_marginal_and_full_day_total(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)

    # An existing appointment that day, so the "full day total" is meaningfully bigger than
    # the marginal cost of inserting the new patient alone.
    existing_patient = make_patient(db_session, clinic, first_name="Existing", latitude=40.002, longitude=-74.002)
    make_appointment(
        db_session,
        clinic,
        patient=existing_patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )

    new_patient = make_patient(
        db_session,
        clinic,
        first_name="New",
        latitude=40.001,
        longitude=-74.001,
        visit_duration_minutes=45,
        zip_code="07031",
    )

    resp = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "NEW_PATIENT_PLACEMENT",
            "therapist_id": str(therapist.id),
            "target_date": str(NEXT_MONDAY),
            "patient_id": str(new_patient.id),
        },
        headers=auth_headers(admin),
    )
    recs = client.get(f"{OPT_URL}/requests/{resp.json()['id']}/recommendations", headers=auth_headers(admin)).json()
    assert len(recs) >= 1
    rec = recs[0]

    assert rec["marginal_drive_minutes"] is not None
    assert rec["marginal_distance_miles"] is not None
    # total_drive_minutes is the full day's total (baseline + marginal), never just the marginal
    # figure alone - it should be at least as large as the marginal cost on its own.
    assert rec["total_drive_minutes"] >= rec["marginal_drive_minutes"]
    assert rec["time_saved_minutes"] is None  # not meaningful for inserting a brand-new visit
    assert rec["miles_saved"] is None


def test_recommendation_response_never_exposes_removed_request_field(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    """Regression guard for the Phase 6 -> Phase 7 schema change: accepted_recommendation_id no
    longer exists on the request; the request response must not reference it."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)

    resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    assert "accepted_recommendation_id" not in resp.json()

    status_resp = client.get(f"{OPT_URL}/requests/{resp.json()['id']}", headers=auth_headers(admin))
    assert "accepted_recommendation_id" not in status_resp.json()


def test_new_recommendation_starts_with_no_accept_or_reject_state(
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
    rec = client.get(f"{OPT_URL}/requests/{resp.json()['id']}/recommendations", headers=auth_headers(admin)).json()[0]
    assert rec["accepted_at"] is None
    assert rec["rejected_at"] is None


def test_accepting_after_rejecting_clears_rejected_state(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic, first_name="A", latitude=40.001, longitude=-74.001)
    make_appointment(
        db_session,
        clinic,
        patient=patient,
        therapist=therapist,
        created_by=admin.id,
        scheduled_date=NEXT_MONDAY,
        start_time=time(9, 0),
    )

    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = create_resp.json()["id"]
    rec = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()[0]

    client.post(f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/reject", headers=auth_headers(admin))
    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )

    assert accept_resp.status_code == 200
    updated = accept_resp.json()["recommendation"]
    assert updated["accepted_at"] is not None
    assert updated["rejected_at"] is None  # accept supersedes an earlier rejection cleanly
