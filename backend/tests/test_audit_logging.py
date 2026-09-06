"""Tests for Phase 9 audit logging (app.services.audit_service and its call sites).

Each test triggers a real action through the API, then reads the AuditLog table directly to check
what got recorded - action name, clinic_id (tenant isolation), user_id (who did it), and that
PII/secrets never end up in old_value/new_value."""

import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.audit_log import AuditLog
from app.services.routing import RouteResult
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

PATIENTS_URL = "/api/v1/patients"
THERAPISTS_URL = "/api/v1/therapists"
APPOINTMENTS_URL = "/api/v1/appointments"
IMPORTS_URL = "/api/v1/imports"
OPT_URL = "/api/v1/optimization"

VALID_PASSWORD = "Str0ng!Passw0rd"
MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


class _DeterministicFakeRouting:
    def route(self, *, origin_lat, origin_lng, dest_lat, dest_lng):
        seconds = (abs(origin_lat - dest_lat) + abs(origin_lng - dest_lng)) * 100_000
        return RouteResult(distance_meters=seconds * 10, duration_seconds=seconds)

    def route_matrix(self, *, points):
        size = len(points)
        return [
            [
                None
                if i == j
                else self.route(origin_lat=points[i][0], origin_lng=points[i][1], dest_lat=points[j][0], dest_lng=points[j][1])
                for j in range(size)
            ]
            for i in range(size)
        ]


@pytest.fixture(autouse=True)
def _deterministic_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _DeterministicFakeRouting())


def _actions(db_session: Session, clinic_id) -> list[AuditLog]:
    return db_session.query(AuditLog).filter(AuditLog.clinic_id == clinic_id).order_by(AuditLog.created_at.asc()).all()


def test_patient_create_update_delete_are_audited(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    create_resp = client.post(
        PATIENTS_URL,
        json={
            "first_name": "Mary",
            "last_name": "Smith",
            "address_line_1": "123 Main St",
            "city": "Hoboken",
            "state": "NJ",
            "zip_code": "07030",
        },
        headers=auth_headers(admin),
    )
    patient_id = create_resp.json()["id"]

    client.patch(f"{PATIENTS_URL}/{patient_id}", json={"phone": "555-1234"}, headers=auth_headers(admin))
    client.delete(f"{PATIENTS_URL}/{patient_id}", headers=auth_headers(admin))

    logs = [a for a in _actions(db_session, clinic.id) if a.entity_id == uuid.UUID(patient_id)]
    actions = [log.action for log in logs]
    assert actions == ["PATIENT_CREATED", "PATIENT_UPDATED", "PATIENT_DELETED"]
    for log in logs:
        assert log.clinic_id == clinic.id
        assert log.user_id == admin.id
        assert log.entity_type == "PATIENT"

    update_log = logs[1]
    # Field names only, never the PII value itself.
    assert update_log.new_value == {"changed_fields": ["phone"]}
    assert "555-1234" not in str(update_log.new_value)


def test_therapist_create_and_deactivate_are_audited(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    create_resp = client.post(
        THERAPISTS_URL,
        json={"first_name": "Terry", "last_name": "Therapist", "email": "terry@example.com", "password": VALID_PASSWORD},
        headers=auth_headers(admin),
    )
    therapist = create_resp.json()

    client.patch(f"{THERAPISTS_URL}/{therapist['id']}", json={"is_active": False}, headers=auth_headers(admin))

    logs = [a for a in _actions(db_session, clinic.id) if a.entity_type == "USER" and str(a.entity_id) == therapist["user_id"]]
    actions = [log.action for log in logs]
    assert "USER_CREATED" in actions
    assert "USER_DEACTIVATED" in actions
    assert all(log.user_id == admin.id for log in logs)


def test_therapist_update_without_activation_change_does_not_log_activation_event(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    create_resp = client.post(
        THERAPISTS_URL,
        json={"first_name": "Terry", "last_name": "Therapist", "email": "terry2@example.com", "password": VALID_PASSWORD},
        headers=auth_headers(admin),
    )
    therapist = create_resp.json()

    client.patch(f"{THERAPISTS_URL}/{therapist['id']}", json={"phone": "555-9999"}, headers=auth_headers(admin))

    logs = [a for a in _actions(db_session, clinic.id) if str(a.entity_id) == therapist["user_id"]]
    assert [log.action for log in logs] == ["USER_CREATED"]


def test_appointment_create_update_cancel_are_audited(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic)

    create_resp = client.post(
        APPOINTMENTS_URL,
        json={
            "patient_id": str(patient.id),
            "therapist_id": str(therapist.id),
            "scheduled_date": str(MONDAY),
            "start_time": "09:00:00",
            "duration_minutes": 60,
        },
        headers=auth_headers(admin),
    )
    appt_id = create_resp.json()["id"]

    client.patch(f"{APPOINTMENTS_URL}/{appt_id}", json={"start_time": "10:00:00"}, headers=auth_headers(admin))
    client.delete(f"{APPOINTMENTS_URL}/{appt_id}", headers=auth_headers(admin))

    logs = [a for a in _actions(db_session, clinic.id) if a.entity_id == uuid.UUID(appt_id)]
    assert [log.action for log in logs] == ["APPOINTMENT_CREATED", "APPOINTMENT_UPDATED", "APPOINTMENT_CANCELLED"]
    assert all(log.user_id == admin.id for log in logs)

    update_log = logs[1]
    assert update_log.old_value["scheduled_at"].endswith("09:00:00")
    assert update_log.new_value["scheduled_at"].endswith("10:00:00")


def test_import_confirm_is_audited(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    from tests.conftest import build_theraoffice_xlsx

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    content = build_theraoffice_xlsx([["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]])

    upload_resp = client.post(
        f"{IMPORTS_URL}/patients",
        files={"file": ("patients.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers(admin),
    )
    import_id = upload_resp.json()["id"]

    client.post(
        f"{IMPORTS_URL}/{import_id}/mapping",
        json={
            "mapping": {
                "full_name": "Patient Full Name",
                "address_line_1": "Address",
                "city": "City",
                "state": "State",
                "zip_code": "ZIP",
            }
        },
        headers=auth_headers(admin),
    )
    client.post(f"{IMPORTS_URL}/{import_id}/confirm", json={"include_duplicates": False}, headers=auth_headers(admin))

    logs = [a for a in _actions(db_session, clinic.id) if a.entity_id == uuid.UUID(import_id)]
    assert any(log.action == "IMPORT_CONFIRMED" for log in logs)
    confirm_log = next(log for log in logs if log.action == "IMPORT_CONFIRMED")
    assert confirm_log.user_id == admin.id
    assert confirm_log.entity_type == "IMPORT_JOB"


def test_optimization_acceptance_is_audited(
    client: TestClient, db_session: Session, clinic, sync_optimization_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.003, longitude=-74.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.0, longitude=-74.0001, zip_code="07031")
    patient_c = make_patient(db_session, clinic, first_name="C", latitude=40.0031, longitude=-74.0, zip_code="07032")
    make_appointment(
        db_session, clinic, patient=patient_a, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_b, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(10, 0),
    )
    make_appointment(
        db_session, clinic, patient=patient_c, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(11, 0),
    )

    create_resp = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": str(therapist.id), "target_date": str(MONDAY)},
        headers=auth_headers(admin),
    )
    request_id = create_resp.json()["id"]
    rec = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=auth_headers(admin)).json()[0]

    client.post(f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=auth_headers(admin))

    logs = [a for a in _actions(db_session, clinic.id) if a.entity_id == uuid.UUID(rec["id"])]
    assert len(logs) == 1
    assert logs[0].action == "OPTIMIZATION_RECOMMENDATION_ACCEPTED"
    assert logs[0].user_id == admin.id
    assert logs[0].entity_type == "OPTIMIZATION_RECOMMENDATION"


def test_audit_logs_are_tenant_isolated(client: TestClient, db_session: Session, clinic) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin_a = make_user(db_session, clinic, email="a@example.com", role=UserRole.CLINIC_ADMIN)
    admin_b = make_user(db_session, other_clinic, email="b@example.com", role=UserRole.CLINIC_ADMIN)

    client.post(
        PATIENTS_URL,
        json={
            "first_name": "A",
            "last_name": "Patient",
            "address_line_1": "1 St",
            "city": "X",
            "state": "NY",
            "zip_code": "10001",
        },
        headers=auth_headers(admin_a),
    )
    client.post(
        PATIENTS_URL,
        json={
            "first_name": "B",
            "last_name": "Patient",
            "address_line_1": "2 St",
            "city": "Y",
            "state": "NY",
            "zip_code": "10002",
        },
        headers=auth_headers(admin_b),
    )

    clinic_a_logs = _actions(db_session, clinic.id)
    clinic_b_logs = _actions(db_session, other_clinic.id)

    assert any(log.action == "PATIENT_CREATED" for log in clinic_a_logs)
    assert any(log.action == "PATIENT_CREATED" for log in clinic_b_logs)
    assert all(log.user_id == admin_a.id for log in clinic_a_logs)
    assert all(log.user_id == admin_b.id for log in clinic_b_logs)
