"""Tests for the accept/reject recommendation workflow - independent of which optimization mode
produced the recommendation. "Modify" isn't a separate backend endpoint (see
app/services/optimization_service.py's module docstring / README) - a user modifies a
recommendation by evaluating their own version through What-If and applying that instead, already
covered by tests/test_what_if.py; this file focuses on accept/reject state and the
NEW_PATIENT_PLACEMENT sibling-exclusivity rule."""

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


def _setup_day_schedule(db_session: Session, clinic):
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
    return admin, therapist


def _create_and_get_day_recommendation(client, admin, therapist):
    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(NEXT_MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = create_resp.json()["id"]
    rec = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()[0]
    return request_id, rec


def test_reject_marks_recommendation_rejected(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)

    resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/reject", headers=auth_headers(admin)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rejected_at"] is not None
    assert body["accepted_at"] is None


def test_reject_then_accept_still_works(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    """Rejecting isn't a permanent lock - a change of mind should still be able to accept."""
    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)

    reject_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/reject", headers=auth_headers(admin)
    )
    assert reject_resp.status_code == 200

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["recommendation"]["accepted_at"] is not None


def test_cannot_reject_an_already_accepted_recommendation(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 200

    reject_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/reject", headers=auth_headers(admin)
    )
    assert reject_resp.status_code == 409


def test_cannot_accept_twice(client: TestClient, db_session: Session, clinic, sync_optimization_tasks) -> None:
    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)

    first = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert first.status_code == 200
    second = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert second.status_code == 409


def test_reject_unknown_recommendation_404s(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    import uuid

    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, _rec = _create_and_get_day_recommendation(client, admin, therapist)

    resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{uuid.uuid4()}/reject", headers=auth_headers(admin)
    )
    assert resp.status_code == 404


def test_new_patient_placement_accepting_one_alternative_blocks_the_others(
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
    request_id = create_resp.json()["id"]
    recs = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()
    assert len(recs) >= 1
    if len(recs) < 2:
        pytest.skip("Need at least 2 candidate slots to exercise sibling exclusivity.")

    first_accept = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{recs[0]['id']}/accept", headers=auth_headers(admin)
    )
    assert first_accept.status_code == 200

    second_accept = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{recs[1]['id']}/accept", headers=auth_headers(admin)
    )
    assert second_accept.status_code == 409
    assert second_accept.json()["error"]["code"] == "RECOMMENDATION_ALREADY_ACCEPTED"


def test_accept_revalidates_constraints_not_just_replays_blindly(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    """If therapist availability is removed entirely after the recommendation was generated,
    accept must fail rather than silently create an appointment outside working hours."""
    from app.models.therapist_availability import TherapistAvailability

    admin, therapist = _setup_day_schedule(db_session, clinic)
    request_id, rec = _create_and_get_day_recommendation(client, admin, therapist)

    if not rec["recommendation_data"].get("appointments"):
        pytest.skip("This recommendation didn't move anything - nothing to revalidate against.")

    # Wipe the therapist's working hours entirely between generation and acceptance.
    db_session.query(TherapistAvailability).filter(TherapistAvailability.therapist_id == therapist.id).delete()
    db_session.commit()

    accept_resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin)
    )
    assert accept_resp.status_code == 400
    assert accept_resp.json()["error"]["code"] == "STALE_RECOMMENDATION"
    assert "changed" in accept_resp.json()["error"]["message"].lower()
