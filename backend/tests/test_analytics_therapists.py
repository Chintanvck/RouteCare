"""Tests for GET /api/v1/analytics/therapists - per-therapist breakdown, working hours, and
utilization math."""

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
WEEK_START = date(2026, 8, 24)  # Monday
WEEK_END = date(2026, 8, 30)  # Sunday
assert WEEK_START.weekday() == 0


class _NoRouting:
    def route(self, **kwargs):
        return None

    def route_matrix(self, **kwargs):
        return None


@pytest.fixture(autouse=True)
def _no_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _NoRouting())


def _params(**overrides) -> dict:
    params = {"period": "custom", "start_date": str(WEEK_START), "end_date": str(WEEK_END)}
    params.update(overrides)
    return params


def test_includes_all_active_therapists_even_with_zero_appointments(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    busy = make_therapist(db_session, clinic, email="busy@example.com", first_name="Busy")
    idle = make_therapist(db_session, clinic, email="idle@example.com", first_name="Idle")
    make_weekday_availability(db_session, busy)
    make_weekday_availability(db_session, idle)
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=busy, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=time(9, 0),
    )

    resp = client.get(f"{ANALYTICS_URL}/therapists", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    rows = resp.json()["therapists"]
    assert len(rows) == 2
    by_id = {r["therapist_id"]: r for r in rows}
    assert by_id[str(busy.id)]["appointments"] == 1
    assert by_id[str(idle.id)]["appointments"] == 0
    assert by_id[str(idle.id)]["utilization_pct"] == 0.0


def test_inactive_therapist_excluded(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_therapist(db_session, clinic, email="inactive@example.com", is_active=False)

    resp = client.get(f"{ANALYTICS_URL}/therapists", params=_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    assert resp.json()["therapists"] == []


def test_therapist_id_filter_returns_single_entry(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    t1 = make_therapist(db_session, clinic, email="t1@example.com")
    make_therapist(db_session, clinic, email="t2@example.com")
    make_weekday_availability(db_session, t1)

    resp = client.get(f"{ANALYTICS_URL}/therapists", params=_params(therapist_id=str(t1.id)), headers=auth_headers(admin))

    assert resp.status_code == 200
    therapists = resp.json()["therapists"]
    assert len(therapists) == 1
    assert therapists[0]["therapist_id"] == str(t1.id)


def test_unknown_therapist_id_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    import uuid

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(
        f"{ANALYTICS_URL}/therapists", params=_params(therapist_id=str(uuid.uuid4())), headers=auth_headers(admin)
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "THERAPIST_NOT_FOUND"


def test_working_hours_and_utilization_math(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    # 8 working hours/day, Monday-Friday only -> 40 working hours across the full Mon-Sun week.
    make_weekday_availability(db_session, therapist, start_time=time(9, 0), end_time=time(17, 0))
    patient = make_patient(db_session, clinic)
    # 4 appointments x 60 minutes = 4 scheduled hours -> utilization = 4/40 * 100 = 10%.
    for i, start in enumerate([time(9, 0), time(10, 0), time(11, 0), time(12, 0)]):
        make_appointment(
            db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
            scheduled_date=WEEK_START, start_time=start, duration_minutes=60,
        )

    resp = client.get(f"{ANALYTICS_URL}/therapists", params=_params(therapist_id=str(therapist.id)), headers=auth_headers(admin))

    assert resp.status_code == 200
    row = resp.json()["therapists"][0]
    assert row["appointments"] == 4
    assert row["working_hours"] == pytest.approx(40.0)
    assert row["scheduled_hours"] == pytest.approx(4.0)
    assert row["utilization_pct"] == pytest.approx(10.0)


def test_utilization_is_none_without_configured_working_hours(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=time(9, 0),
    )

    resp = client.get(f"{ANALYTICS_URL}/therapists", params=_params(therapist_id=str(therapist.id)), headers=auth_headers(admin))

    assert resp.status_code == 200
    row = resp.json()["therapists"][0]
    assert row["working_hours"] == 0
    assert row["utilization_pct"] is None
