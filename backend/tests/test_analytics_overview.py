"""Tests for GET /api/v1/analytics/overview - date-range resolution and clinic-wide volume/
driving metrics. Data-bearing tests use period=custom with a fixed calendar week so results never
depend on when the suite happens to run; the date-range-resolution tests are the only ones that
need to reason about the real "today"."""

from datetime import date, datetime, timedelta, timezone

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

# A fixed Monday..Sunday week, unrelated to whenever the suite actually runs.
WEEK_START = date(2026, 8, 24)
WEEK_END = date(2026, 8, 30)
assert WEEK_START.weekday() == 0


class _DeterministicFakeRouting:
    """Distance-proportional-to-coordinate-delta fake, same shape as tests/test_what_if.py's -
    keeps driving-time assertions exact instead of just "greater than zero"."""

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


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _custom_params(start: date = WEEK_START, end: date = WEEK_END) -> dict:
    return {"period": "custom", "start_date": str(start), "end_date": str(end)}


# --------------------------------------------------------------------------
# Date-range resolution
# --------------------------------------------------------------------------


def test_overview_defaults_to_this_week(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    today = _today_utc()

    resp = client.get(f"{ANALYTICS_URL}/overview", headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()["date_range"]
    expected_start = today - timedelta(days=today.weekday())
    assert body["period"] == "this_week"
    assert body["start_date"] == str(expected_start)
    assert body["end_date"] == str(expected_start + timedelta(days=6))


def test_overview_today_period(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    today = _today_utc()

    resp = client.get(f"{ANALYTICS_URL}/overview", params={"period": "today"}, headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()["date_range"]
    assert body["start_date"] == body["end_date"] == str(today)


def test_overview_last_week_is_seven_days_before_this_week(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    today = _today_utc()
    this_week_start = today - timedelta(days=today.weekday())

    resp = client.get(f"{ANALYTICS_URL}/overview", params={"period": "last_week"}, headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()["date_range"]
    assert body["start_date"] == str(this_week_start - timedelta(days=7))
    assert body["end_date"] == str(this_week_start - timedelta(days=1))


def test_overview_this_month_spans_calendar_month(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    today = _today_utc()

    resp = client.get(f"{ANALYTICS_URL}/overview", params={"period": "this_month"}, headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()["date_range"]
    assert body["start_date"] == str(today.replace(day=1))
    assert date.fromisoformat(body["end_date"]).month == today.month


def test_custom_range_requires_both_dates(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(f"{ANALYTICS_URL}/overview", params={"period": "custom"}, headers=auth_headers(admin))

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CUSTOM_RANGE_REQUIRES_DATES"


def test_custom_range_start_after_end_rejected(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(
        f"{ANALYTICS_URL}/overview",
        params={"period": "custom", "start_date": str(WEEK_END), "end_date": str(WEEK_START)},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_custom_range_too_large_rejected(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(
        f"{ANALYTICS_URL}/overview",
        params={"period": "custom", "start_date": "2026-01-01", "end_date": "2026-12-31"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "DATE_RANGE_TOO_LARGE"


# --------------------------------------------------------------------------
# Volume / driving metrics
# --------------------------------------------------------------------------


def test_overview_empty_dataset_returns_zeroes_not_error(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(f"{ANALYTICS_URL}/overview", params=_custom_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_appointments"] == 0
    assert body["total_drive_minutes"] == 0
    assert body["average_utilization_pct"] is None
    assert body["estimated_time_saved_minutes"] is None
    assert body["estimated_miles_saved"] is None
    assert body["appointments_by_day"] == []
    assert body["drive_minutes_by_day"] == []


def test_overview_appointment_status_breakdown(client: TestClient, db_session: Session, clinic) -> None:
    from datetime import time as dtime

    from app.models.appointment import AppointmentStatus

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(9, 0), status=AppointmentStatus.SCHEDULED,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(10, 0), status=AppointmentStatus.COMPLETED,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(11, 0), status=AppointmentStatus.CANCELLED,
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(12, 0), status=AppointmentStatus.NO_SHOW,
    )

    resp = client.get(f"{ANALYTICS_URL}/overview", params=_custom_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_appointments"] == 4
    assert body["scheduled_appointments"] == 1
    assert body["completed_appointments"] == 1
    assert body["cancelled_appointments"] == 1
    assert body["no_show_appointments"] == 1


def test_overview_driving_metrics_from_geocoded_appointments(client: TestClient, db_session: Session, clinic) -> None:
    from datetime import time as dtime

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.001, longitude=-74.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.002, longitude=-74.0, zip_code="07031")
    make_appointment(
        db_session, clinic, patient=patient_a, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(9, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_b, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(11, 0),
    )
    # home(40,-74) -> A(40.001,-74) -> B(40.002,-74): each leg = 0.001 deg * 100_000 = 100s, rounded
    # to 1.7min by travel_time_service before this module ever sees it - sum the rounded legs, not
    # the raw arithmetic, to match the actual (cached) per-leg rounding.
    leg_minutes = round(100 / 60, 1)
    expected_minutes = round(leg_minutes * 2, 1)

    resp = client.get(f"{ANALYTICS_URL}/overview", params=_custom_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_drive_minutes"] == pytest.approx(expected_minutes, abs=0.1)
    assert body["total_distance_miles"] > 0
    assert len(body["drive_minutes_by_day"]) == 1
    assert body["drive_minutes_by_day"][0]["date"] == str(WEEK_START)


def test_overview_cancelled_appointments_excluded_from_driving(
    client: TestClient, db_session: Session, clinic
) -> None:
    from datetime import time as dtime

    from app.models.appointment import AppointmentStatus

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.001, longitude=-74.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.002, longitude=-74.0, zip_code="07031")
    make_appointment(
        db_session, clinic, patient=patient_a, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(9, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_b, therapist=therapist, created_by=admin.id,
        scheduled_date=WEEK_START, start_time=dtime(11, 0), status=AppointmentStatus.CANCELLED,
    )

    resp = client.get(f"{ANALYTICS_URL}/overview", params=_custom_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    # Only patient A remains after excluding the cancelled visit - a single geocoded visit still
    # produces one home->A leg, but never a leg to/from the cancelled B.
    body = resp.json()
    home_to_a_minutes = round(100 / 60, 1)
    assert body["total_drive_minutes"] == pytest.approx(home_to_a_minutes, abs=0.1)


def test_overview_optimization_activity_is_zero_without_any_requests(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_therapist(db_session, clinic)

    resp = client.get(f"{ANALYTICS_URL}/overview", params=_custom_params(), headers=auth_headers(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["optimization_runs"] == 0
    assert body["recommendations_accepted"] == 0
