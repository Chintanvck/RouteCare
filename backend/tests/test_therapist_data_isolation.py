"""
RouteCare AI - Phase 11 consolidated therapist data-isolation audit.

A THERAPIST must never be able to reach another therapist's appointments,
schedule, optimization results, performance analytics, or unassigned
patients - not even by guessing/changing an id in the URL or a query
parameter. Several of these were already covered by earlier phases'
security test files (test_appointments_security.py,
test_analytics_security.py, test_optimization_api.py); this file is the
single place that exercises the *complete* "Therapist A vs. Therapist
B's data" story end to end across every affected module in one setup,
per this phase's explicit request, plus the two gaps Phase 11 actually
found and fixed: patient scoping (Patient has no therapist assignment of
its own - see patient_service._active_patients_query) and maps/travel-
time (previously allowed resolving *any* clinic patient/therapist as a
routing endpoint, regardless of caller).

Admin/scheduler retention checks close the loop - a fix that accidentally
over-restricted clinic-level roles would be just as bad as the leak itself.
"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
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

APPOINTMENTS_URL = "/api/v1/appointments"
PATIENTS_URL = "/api/v1/patients"
THERAPISTS_URL = "/api/v1/therapists"
OPT_URL = "/api/v1/optimization"
ANALYTICS_URL = "/api/v1/analytics"
MAPS_URL = "/api/v1/maps"

MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


class _NoRouting:
    def route(self, **kwargs):
        return None

    def route_matrix(self, **kwargs):
        return None


@pytest.fixture(autouse=True)
def _no_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _NoRouting())


@pytest.fixture()
def scenario(db_session: Session, clinic):
    """Two therapists, each with their own patient and appointment, plus a third patient neither
    is assigned to - the fixture every test in this file builds on."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist_a = make_therapist(
        db_session, clinic, email="a@example.com", first_name="Alice", home_latitude=40.0, home_longitude=-74.0
    )
    therapist_b = make_therapist(
        db_session, clinic, email="b@example.com", first_name="Bob", home_latitude=40.5, home_longitude=-74.5
    )
    make_weekday_availability(db_session, therapist_a)
    make_weekday_availability(db_session, therapist_b)

    patient_a = make_patient(db_session, clinic, first_name="PatientA", latitude=40.01, longitude=-74.01, zip_code="07030")
    patient_b = make_patient(db_session, clinic, first_name="PatientB", latitude=40.51, longitude=-74.51, zip_code="07031")
    unassigned_patient = make_patient(db_session, clinic, first_name="Unassigned", zip_code="07032")

    appt_a = make_appointment(
        db_session, clinic, patient=patient_a, therapist=therapist_a, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )
    appt_b = make_appointment(
        db_session, clinic, patient=patient_b, therapist=therapist_b, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    user_a = db_session.get(User, therapist_a.user_id)
    user_b = db_session.get(User, therapist_b.user_id)

    return {
        "admin": admin,
        "therapist_a": therapist_a,
        "therapist_b": therapist_b,
        "user_a": user_a,
        "user_b": user_b,
        "patient_a": patient_a,
        "patient_b": patient_b,
        "unassigned_patient": unassigned_patient,
        "appt_a": appt_a,
        "appt_b": appt_b,
    }


# ============================================================
# Appointments / schedule
# ============================================================


def test_therapist_a_cannot_get_therapist_bs_appointment(client: TestClient, scenario) -> None:
    resp = client.get(f"{APPOINTMENTS_URL}/{scenario['appt_b'].id}", headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 404


def test_therapist_a_schedule_list_never_includes_therapist_b(client: TestClient, scenario) -> None:
    """Even an unfiltered `GET /appointments` (no therapist_id param at all) must never return
    another therapist's schedule - the server-side restriction, not query params, is the boundary."""
    resp = client.get(
        f"{APPOINTMENTS_URL}?start_date={MONDAY}&end_date={MONDAY}", headers=auth_headers(scenario["user_a"])
    )
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()["items"]}
    assert str(scenario["appt_a"].id) in ids
    assert str(scenario["appt_b"].id) not in ids


def test_therapist_a_cannot_widen_schedule_via_therapist_id_param(client: TestClient, scenario) -> None:
    """Changing ?therapist_id= in the query string to Therapist B's id must not widen A's view -
    per this phase's explicit 'must not gain access by changing... query parameters' requirement.
    The param is silently overridden (A's own schedule comes back, not B's, not empty) rather than
    rejected - same precedence appointment_service.list_appointments already documents."""
    resp = client.get(
        f"{APPOINTMENTS_URL}?therapist_id={scenario['therapist_b'].id}&start_date={MONDAY}&end_date={MONDAY}",
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()["items"]}
    assert ids == {str(scenario["appt_a"].id)}


def test_therapist_a_cannot_cancel_therapist_bs_appointment(client: TestClient, scenario) -> None:
    resp = client.delete(f"{APPOINTMENTS_URL}/{scenario['appt_b'].id}", headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 404


# ============================================================
# Therapist profiles / availability
# ============================================================


def test_therapist_a_cannot_view_therapist_bs_profile(client: TestClient, scenario) -> None:
    resp = client.get(f"{THERAPISTS_URL}/{scenario['therapist_b'].id}", headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 404


def test_therapist_a_cannot_view_therapist_bs_availability(client: TestClient, scenario) -> None:
    resp = client.get(
        f"{THERAPISTS_URL}/{scenario['therapist_b'].id}/availability", headers=auth_headers(scenario["user_a"])
    )
    assert resp.status_code == 404


def test_therapist_a_list_therapists_only_returns_self(client: TestClient, scenario) -> None:
    resp = client.get(THERAPISTS_URL, headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(scenario["therapist_a"].id)


# ============================================================
# Patients
# ============================================================


def test_therapist_a_cannot_get_therapist_bs_patient(client: TestClient, scenario) -> None:
    resp = client.get(f"{PATIENTS_URL}/{scenario['patient_b'].id}", headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 404


def test_therapist_a_cannot_get_unassigned_patient(client: TestClient, scenario) -> None:
    resp = client.get(f"{PATIENTS_URL}/{scenario['unassigned_patient'].id}", headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 404


def test_therapist_a_patient_list_excludes_bs_and_unassigned(client: TestClient, scenario) -> None:
    resp = client.get(PATIENTS_URL, headers=auth_headers(scenario["user_a"]))
    assert resp.status_code == 200
    names = {p["first_name"] for p in resp.json()["items"]}
    assert names == {"PatientA"}


# ============================================================
# Optimization
# ============================================================


def test_therapist_a_cannot_retrieve_therapist_bs_optimization_request(
    client: TestClient, scenario, sync_optimization_tasks
) -> None:
    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "DAY_SCHEDULE_OPTIMIZATION",
            "therapist_id": str(scenario["therapist_b"].id),
            "target_date": str(MONDAY),
        },
        headers=auth_headers(scenario["user_b"]),
    )
    assert create_resp.status_code == 201
    request_id = create_resp.json()["id"]

    get_resp = client.get(f"{OPT_URL}/requests/{request_id}", headers=auth_headers(scenario["user_a"]))
    assert get_resp.status_code == 404

    recs_resp = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(scenario["user_a"]))
    assert recs_resp.status_code == 404


def test_therapist_a_cannot_accept_therapist_bs_recommendation(
    client: TestClient, scenario, sync_optimization_tasks
) -> None:
    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={
            "mode": "DAY_SCHEDULE_OPTIMIZATION",
            "therapist_id": str(scenario["therapist_b"].id),
            "target_date": str(MONDAY),
        },
        headers=auth_headers(scenario["user_b"]),
    )
    request_id = create_resp.json()["id"]
    rec = client.get(
        f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(scenario["user_b"])
    ).json()[0]

    resp = client.post(
        f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(scenario["user_a"])
    )
    assert resp.status_code == 404


# ============================================================
# Analytics
# ============================================================


@pytest.mark.parametrize("endpoint", ["/therapists", "/efficiency", "/optimization-impact"])
def test_therapist_a_analytics_ignores_therapist_id_param_pointing_at_b(
    client: TestClient, scenario, endpoint: str
) -> None:
    resp = client.get(
        f"{ANALYTICS_URL}{endpoint}",
        params={"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY), "therapist_id": str(scenario["therapist_b"].id)},
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    if "therapists" in body:
        ids = {t["therapist_id"] for t in body["therapists"]}
        assert ids == {str(scenario["therapist_a"].id)}
    else:
        assert body.get("therapist_id") in (None, str(scenario["therapist_a"].id))


def test_therapist_a_overview_shows_only_own_appointment_count(client: TestClient, scenario) -> None:
    resp = client.get(
        f"{ANALYTICS_URL}/overview",
        params={"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY)},
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 200
    assert resp.json()["total_appointments"] == 1  # only appt_a, never appt_b


# ============================================================
# Maps / travel-time (the endpoint this phase found unrestricted)
# ============================================================


def test_therapist_a_cannot_resolve_therapist_bs_home_via_travel_time(client: TestClient, scenario) -> None:
    resp = client.post(
        f"{MAPS_URL}/travel-time",
        json={
            "origin": {"patient_id": str(scenario["patient_a"].id)},
            "destination": {"therapist_id": str(scenario["therapist_b"].id)},
        },
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 404


def test_therapist_a_cannot_resolve_unassigned_patient_via_travel_time(client: TestClient, scenario) -> None:
    resp = client.post(
        f"{MAPS_URL}/travel-time",
        json={
            "origin": {"therapist_id": str(scenario["therapist_a"].id)},
            "destination": {"patient_id": str(scenario["unassigned_patient"].id)},
        },
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 404


def test_therapist_a_travel_time_matrix_rejects_therapist_bs_patient(client: TestClient, scenario) -> None:
    resp = client.post(
        f"{MAPS_URL}/travel-time-matrix",
        json={
            "points": [
                {"therapist_id": str(scenario["therapist_a"].id)},
                {"patient_id": str(scenario["patient_b"].id)},
            ]
        },
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 404


def test_therapist_a_can_use_travel_time_for_own_patient(client: TestClient, scenario, monkeypatch) -> None:
    """The restriction narrows access - it must not break the legitimate case a therapist actually
    needs (their own home to their own assigned patient)."""
    from app.services import routing

    monkeypatch.setattr(
        routing,
        "get_routing_provider",
        lambda: type("P", (), {"route": lambda self, **kw: RouteResult(distance_meters=1000, duration_seconds=120)})(),
    )
    resp = client.post(
        f"{MAPS_URL}/travel-time",
        json={
            "origin": {"therapist_id": str(scenario["therapist_a"].id)},
            "destination": {"patient_id": str(scenario["patient_a"].id)},
        },
        headers=auth_headers(scenario["user_a"]),
    )
    assert resp.status_code == 200
    assert resp.json()["reachable"] is True


# ============================================================
# Admin / office scheduler retain full clinic-wide access
# ============================================================


def test_admin_sees_both_therapists_appointments(client: TestClient, scenario) -> None:
    resp = client.get(
        f"{APPOINTMENTS_URL}?start_date={MONDAY}&end_date={MONDAY}", headers=auth_headers(scenario["admin"])
    )
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()["items"]}
    assert {str(scenario["appt_a"].id), str(scenario["appt_b"].id)} <= ids


def test_admin_sees_both_therapists_in_list(client: TestClient, scenario) -> None:
    resp = client.get(THERAPISTS_URL, headers=auth_headers(scenario["admin"]))
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_admin_sees_all_patients_including_unassigned(client: TestClient, scenario) -> None:
    resp = client.get(PATIENTS_URL, headers=auth_headers(scenario["admin"]))
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


def test_office_scheduler_sees_both_therapists_schedules(client: TestClient, db_session: Session, clinic, scenario) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER, email="scheduler@example.com")
    resp = client.get(
        f"{APPOINTMENTS_URL}?start_date={MONDAY}&end_date={MONDAY}", headers=auth_headers(scheduler)
    )
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()["items"]}
    assert {str(scenario["appt_a"].id), str(scenario["appt_b"].id)} <= ids


def test_admin_can_resolve_any_therapist_via_travel_time(client: TestClient, scenario, monkeypatch) -> None:
    from app.services import routing

    monkeypatch.setattr(
        routing,
        "get_routing_provider",
        lambda: type("P", (), {"route": lambda self, **kw: RouteResult(distance_meters=1000, duration_seconds=120)})(),
    )
    resp = client.post(
        f"{MAPS_URL}/travel-time",
        json={
            "origin": {"therapist_id": str(scenario["therapist_b"].id)},
            "destination": {"patient_id": str(scenario["patient_a"].id)},
        },
        headers=auth_headers(scenario["admin"]),
    )
    assert resp.status_code == 200
