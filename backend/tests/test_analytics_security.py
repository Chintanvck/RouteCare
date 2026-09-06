"""Tests for RBAC, tenant isolation, and therapist self-scoping across every /api/v1/analytics/*
endpoint - a THERAPIST must never be able to see another therapist's numbers (even by passing
`?therapist_id=`), and a clinic admin must never be able to reach another clinic's therapist."""

import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.user import User
from tests.conftest import auth_headers, make_appointment, make_patient, make_therapist, make_user, make_weekday_availability

ANALYTICS_URL = "/api/v1/analytics"
MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0

ENDPOINTS = ["/overview", "/therapists", "/efficiency", "/optimization-impact"]


class _NoRouting:
    def route(self, **kwargs):
        return None

    def route_matrix(self, **kwargs):
        return None


@pytest.fixture(autouse=True)
def _no_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _NoRouting())


def _params() -> dict:
    return {"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY)}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_unauthenticated_request_rejected(client: TestClient, endpoint: str) -> None:
    resp = client.get(f"{ANALYTICS_URL}{endpoint}", params=_params())
    assert resp.status_code == 401


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_system_admin_is_forbidden(client: TestClient, db_session: Session, endpoint: str) -> None:
    """SYSTEM_ADMIN isn't in this module's allowed-roles list at all (this phase adds no
    platform-level analytics, per the task's explicit scope) - require_role rejects it before
    get_current_clinic_id's own "no clinic" check would even run."""
    system_admin = make_user(db_session, None, email="sysadmin@example.com", role=UserRole.SYSTEM_ADMIN)

    resp = client.get(f"{ANALYTICS_URL}{endpoint}", params=_params(), headers=auth_headers(system_admin))

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("endpoint", ["/therapists", "/efficiency", "/optimization-impact"])
def test_admin_cannot_reach_another_clinics_therapist(client: TestClient, db_session: Session, clinic, endpoint: str) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    db_session.refresh(other_clinic)

    admin = make_user(db_session, clinic, email="admin@clinic-a.com", role=UserRole.CLINIC_ADMIN)
    other_therapist = make_therapist(db_session, other_clinic, email="other-therapist@example.com")

    resp = client.get(
        f"{ANALYTICS_URL}{endpoint}",
        params={**_params(), "therapist_id": str(other_therapist.id)},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 404


def test_therapist_role_forced_to_own_id_on_therapists_endpoint(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    me = make_therapist(db_session, clinic, email="me@example.com", first_name="Me")
    other = make_therapist(db_session, clinic, email="other@example.com", first_name="Other")
    make_weekday_availability(db_session, me)
    make_weekday_availability(db_session, other)
    me_user = db_session.get(User, me.user_id)

    resp = client.get(
        f"{ANALYTICS_URL}/therapists",
        params={**_params(), "therapist_id": str(other.id)},  # attempt to view someone else's data
        headers=auth_headers(me_user),
    )

    assert resp.status_code == 200
    therapists = resp.json()["therapists"]
    assert len(therapists) == 1
    assert therapists[0]["therapist_id"] == str(me.id)


def test_therapist_role_sees_only_own_appointments_in_overview(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    me = make_therapist(db_session, clinic, email="me2@example.com", first_name="Me2")
    other = make_therapist(db_session, clinic, email="other2@example.com", first_name="Other2")
    make_weekday_availability(db_session, me)
    make_weekday_availability(db_session, other)
    patient = make_patient(db_session, clinic)
    make_appointment(
        db_session, clinic, patient=patient, therapist=me, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient, therapist=other, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(10, 0),
    )
    me_user = db_session.get(User, me.user_id)

    admin_resp = client.get(f"{ANALYTICS_URL}/overview", params=_params(), headers=auth_headers(admin))
    therapist_resp = client.get(f"{ANALYTICS_URL}/overview", params=_params(), headers=auth_headers(me_user))

    assert admin_resp.status_code == 200
    assert therapist_resp.status_code == 200
    assert admin_resp.json()["total_appointments"] == 2
    assert therapist_resp.json()["total_appointments"] == 1


def test_therapist_without_profile_gets_not_found(client: TestClient, db_session: Session, clinic) -> None:
    orphan_therapist_user = make_user(
        db_session, clinic, email="orphan@example.com", role=UserRole.THERAPIST
    )

    resp = client.get(f"{ANALYTICS_URL}/overview", params=_params(), headers=auth_headers(orphan_therapist_user))

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "THERAPIST_NOT_FOUND"


def test_unknown_therapist_id_is_404_not_a_data_leak(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    resp = client.get(
        f"{ANALYTICS_URL}/efficiency", params={**_params(), "therapist_id": str(uuid.uuid4())}, headers=auth_headers(admin)
    )

    assert resp.status_code == 404
