"""
RouteCare AI - End-to-end workflow validation (Phase 10).

One connected journey through the real HTTP API - clinic setup all the
way through analytics - rather than the isolated per-feature unit tests
that already cover each step in depth elsewhere. The point of this file
is specifically to prove the pieces *compose*: a patient who arrives via
Excel import (not a test fixture) can be scheduled, travel-timed,
optimized, and shown up in analytics exactly like a manually-created one.

Routing/geocoding are mocked (deterministic, distance-proportional fake)
per the task's explicit "do not depend on live OSRM/geocoding services" -
patients/therapists are geocoded via explicit lat/lng at creation, never
through a live provider call.

Covers (see Phase 10 task list): authentication, clinic isolation,
therapist creation, availability configuration, patient creation, Excel
import, duplicate detection, appointment creation, conflict detection,
travel-time calculation, daily optimization, recommendation retrieval,
recommendation acceptance, recommendation rejection, What-If simulation,
What-If application, analytics, and audit logging - in that order, as
one continuous scenario.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.audit_log import AuditLog
from app.models.clinic import Clinic
from app.services.routing import RouteResult
from tests.conftest import VALID_PASSWORD, auth_headers, build_theraoffice_xlsx, make_user

AUTH_URL = "/api/v1/auth"
PATIENTS_URL = "/api/v1/patients"
THERAPISTS_URL = "/api/v1/therapists"
APPOINTMENTS_URL = "/api/v1/appointments"
IMPORTS_URL = "/api/v1/imports"
MAPS_URL = "/api/v1/maps"
OPT_URL = "/api/v1/optimization"
ANALYTICS_URL = "/api/v1/analytics"

MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


class _DeterministicFakeRouting:
    """Distance-proportional fake OSRM - same shape used throughout the suite (see
    tests/test_what_if.py) so driving-time numbers in this journey are exact, not just "some
    positive number", without ever touching a real routing service."""

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
def _mocked_routing_and_geocoding(monkeypatch: pytest.MonkeyPatch):
    """Belt-and-suspenders: this journey never calls geocoding at all (every patient/therapist gets
    explicit lat/lng), but the routing provider is mocked regardless of that, and geocoding is
    mocked too in case a future edit to this test ever adds an address-only patient."""
    from app.services import geocoding, routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _DeterministicFakeRouting())
    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: geocoding.NullGeocodingProvider())


def test_complete_clinic_workflow(
    client: TestClient, db_session: Session, clinic, sync_import_tasks, sync_optimization_tasks
) -> None:
    # ============================================================
    # 1. AUTHENTICATION
    # ============================================================
    register_resp = client.post(
        f"{AUTH_URL}/register",
        json={
            "clinic_name": "E2E Demo Clinic",
            "first_name": "Dana",
            "last_name": "Admin",
            "email": "dana.e2e@example.com",
            "password": VALID_PASSWORD,
        },
    )
    assert register_resp.status_code == 201

    login_resp = client.post(f"{AUTH_URL}/login", json={"email": "dana.e2e@example.com", "password": VALID_PASSWORD})
    assert login_resp.status_code == 200
    admin_token = login_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    me_resp = client.get(f"{AUTH_URL}/me", headers=admin_headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "CLINIC_ADMIN"
    admin_clinic_id = me_resp.json()["clinic_id"]

    # ============================================================
    # 2. CLINIC ISOLATION
    # ============================================================
    other_clinic = Clinic(name="A Different Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    other_admin = make_user(db_session, other_clinic, email="other-admin@example.com", role=UserRole.CLINIC_ADMIN)

    other_patients_resp = client.get(PATIENTS_URL, headers=auth_headers(other_admin))
    assert other_patients_resp.status_code == 200
    assert other_patients_resp.json()["items"] == []  # nothing seeded there yet - isolation checked again at the end

    # ============================================================
    # 3. THERAPIST CREATION
    # ============================================================
    therapist_resp = client.post(
        THERAPISTS_URL,
        json={
            "first_name": "Terry",
            "last_name": "Therapist",
            "email": "terry.e2e@example.com",
            "password": VALID_PASSWORD,
            "home_latitude": 40.7440,
            "home_longitude": -74.0324,
        },
        headers=admin_headers,
    )
    assert therapist_resp.status_code == 201
    therapist = therapist_resp.json()
    assert therapist["clinic_id"] == admin_clinic_id

    # ============================================================
    # 4. AVAILABILITY CONFIGURATION
    # ============================================================
    availability_resp = client.put(
        f"{THERAPISTS_URL}/{therapist['id']}/availability",
        json={"rules": [{"day_of_week": d, "start_time": "09:00:00", "end_time": "17:00:00", "is_available": True} for d in range(5)]},
        headers=admin_headers,
    )
    assert availability_resp.status_code == 200
    assert len(availability_resp.json()) == 5

    # ============================================================
    # 5. PATIENT CREATION (manual)
    # ============================================================
    patient_a_resp = client.post(
        PATIENTS_URL,
        json={
            "first_name": "Alice", "last_name": "Nearby",
            "address_line_1": "1 Newark St", "city": "Hoboken", "state": "NJ", "zip_code": "07030",
            "latitude": 40.7420, "longitude": -74.0310,
            "visit_duration_minutes": 45,
        },
        headers=admin_headers,
    )
    assert patient_a_resp.status_code == 201
    patient_a = patient_a_resp.json()
    assert patient_a["geocoding_status"] == "MANUAL"  # explicit coordinates, never a live geocode call

    # ============================================================
    # 6. EXCEL IMPORT + 7. DUPLICATE DETECTION
    # ============================================================
    # One brand-new patient, plus one row that's an exact duplicate of Alice (same name+ZIP) -
    # proves both "a new patient" and "a detected duplicate" are classified correctly.
    xlsx_rows = [
        ["Bob Faraway", "", "", "500 5th Ave", "New York", "NY", "10110"],
        ["Alice Nearby", "", "", "1 Newark St", "Hoboken", "NJ", "07030"],
    ]
    content = build_theraoffice_xlsx(xlsx_rows)
    upload_resp = client.post(
        f"{IMPORTS_URL}/patients",
        files={"file": ("theraoffice_export.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_headers,
    )
    assert upload_resp.status_code == 201
    import_id = upload_resp.json()["id"]

    mapping_resp = client.post(
        f"{IMPORTS_URL}/{import_id}/mapping",
        json={"mapping": {
            "full_name": "Patient Full Name", "address_line_1": "Address",
            "city": "City", "state": "State", "zip_code": "ZIP",
        }},
        headers=admin_headers,
    )
    assert mapping_resp.status_code == 200

    preview_resp = client.get(f"{IMPORTS_URL}/{import_id}/preview", headers=admin_headers)
    assert preview_resp.status_code == 200
    rows_by_name = {r["mapped_data"]["first_name"]: r for r in preview_resp.json()["items"]}
    assert rows_by_name["Bob"]["classification"] == "VALID"
    assert rows_by_name["Alice"]["classification"] in ("DUPLICATE_EXACT", "DUPLICATE_PROBABLE")

    confirm_resp = client.post(f"{IMPORTS_URL}/{import_id}/confirm", json={"include_duplicates": False}, headers=admin_headers)
    assert confirm_resp.status_code == 200
    job_status = client.get(f"{IMPORTS_URL}/{import_id}", headers=admin_headers).json()
    assert job_status["status"] in ("COMPLETED", "COMPLETED_WITH_ERRORS")
    assert job_status["successful_records"] == 1  # only Bob - Alice's duplicate was correctly skipped

    imported_patients = client.get(f"{PATIENTS_URL}?search=Bob", headers=admin_headers).json()["items"]
    assert len(imported_patients) == 1
    bob = imported_patients[0]
    assert bob["source_system"] == "import:theraoffice"
    # The imported patient has no lat/lng yet (Excel imports carry an address, not coordinates) -
    # geocode it explicitly so it can participate in scheduling/optimization below, exactly like a
    # real user would from the patient detail page's "Geocode now" action. Geocoding is mocked to
    # NullGeocodingProvider (always "no result") in this test, so set coordinates manually instead -
    # this is the "patient location" integration point Phase 10 explicitly asks to verify.
    geocode_bob = client.patch(
        f"{PATIENTS_URL}/{bob['id']}", json={"latitude": 40.7546, "longitude": -73.9829}, headers=admin_headers
    )
    assert geocode_bob.status_code == 200
    bob = geocode_bob.json()
    assert bob["geocoding_status"] == "MANUAL"

    # ============================================================
    # 8. APPOINTMENT CREATION (including the imported patient) + 9. CONFLICT DETECTION
    # ============================================================
    appt_a = client.post(
        APPOINTMENTS_URL,
        json={"patient_id": patient_a["id"], "therapist_id": therapist["id"], "scheduled_date": str(MONDAY), "start_time": "09:00:00", "duration_minutes": 45},
        headers=admin_headers,
    )
    assert appt_a.status_code == 201

    appt_bob = client.post(
        APPOINTMENTS_URL,
        json={"patient_id": bob["id"], "therapist_id": therapist["id"], "scheduled_date": str(MONDAY), "start_time": "11:00:00", "duration_minutes": 45},
        headers=admin_headers,
    )
    assert appt_bob.status_code == 201  # the imported, then geocoded, patient can be scheduled normally

    conflict_resp = client.post(
        APPOINTMENTS_URL,
        json={"patient_id": patient_a["id"], "therapist_id": therapist["id"], "scheduled_date": str(MONDAY), "start_time": "09:15:00", "duration_minutes": 30},
        headers=admin_headers,
    )
    assert conflict_resp.status_code == 400
    assert "already has an appointment" in conflict_resp.json()["error"]["message"]

    # ============================================================
    # 10. TRAVEL-TIME CALCULATION
    # ============================================================
    travel_resp = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"patient_id": patient_a["id"]}, "destination": {"patient_id": bob["id"]}},
        headers=admin_headers,
    )
    assert travel_resp.status_code == 200
    travel_body = travel_resp.json()
    assert travel_body["reachable"] is True
    assert travel_body["duration_minutes"] > 0

    # ============================================================
    # 11. DAILY OPTIMIZATION + 12. RECOMMENDATION RETRIEVAL
    # ============================================================
    opt_create = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": therapist["id"], "target_date": str(MONDAY)},
        headers=admin_headers,
    )
    assert opt_create.status_code == 201
    request_id = opt_create.json()["id"]

    request_status = client.get(f"{OPT_URL}/requests/{request_id}", headers=admin_headers)
    assert request_status.status_code == 200
    assert request_status.json()["status"] == "COMPLETED"  # sync_optimization_tasks ran it inline

    recs_resp = client.get(f"{OPT_URL}/requests/{request_id}/recommendations", headers=admin_headers)
    assert recs_resp.status_code == 200
    recommendations = recs_resp.json()
    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec["total_drive_minutes"] >= 0
    assert rec["explanation"]

    # ============================================================
    # 13. RECOMMENDATION ACCEPTANCE
    # ============================================================
    accept_resp = client.post(f"{OPT_URL}/requests/{request_id}/recommendations/{rec['id']}/accept", headers=admin_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["recommendation"]["accepted_at"] is not None

    # ============================================================
    # 14. RECOMMENDATION REJECTION (a separate, independent request/recommendation)
    # ============================================================
    opt_create_2 = client.post(
        f"{OPT_URL}/requests",
        json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": therapist["id"], "target_date": str(MONDAY)},
        headers=admin_headers,
    )
    request_id_2 = opt_create_2.json()["id"]
    rec_2 = client.get(f"{OPT_URL}/requests/{request_id_2}/recommendations", headers=admin_headers).json()[0]
    reject_resp = client.post(f"{OPT_URL}/requests/{request_id_2}/recommendations/{rec_2['id']}/reject", headers=admin_headers)
    assert reject_resp.status_code == 200
    assert reject_resp.json()["rejected_at"] is not None

    # ============================================================
    # 15. WHAT-IF SIMULATION + 16. WHAT-IF APPLICATION
    # ============================================================
    current_appointments = client.get(
        f"{APPOINTMENTS_URL}?therapist_id={therapist['id']}&start_date={MONDAY}&end_date={MONDAY}", headers=admin_headers
    ).json()["items"]
    alice_appt = next(a for a in current_appointments if a["patient_id"] == patient_a["id"])

    what_if_resp = client.post(
        f"{OPT_URL}/what-if",
        json={
            "scenario_type": "MOVE", "appointment_id": alice_appt["id"],
            "new_scheduled_date": str(MONDAY), "new_start_time": "10:00:00",
        },
        headers=admin_headers,
    )
    assert what_if_resp.status_code == 200
    what_if_body = what_if_resp.json()
    assert what_if_body["feasible"] is True
    # Purely evaluative - the appointment must be untouched until /apply is called.
    unchanged = client.get(f"{APPOINTMENTS_URL}/{alice_appt['id']}", headers=admin_headers).json()
    assert unchanged["start_time"] == "10:00:00" or unchanged["start_time"] == alice_appt["start_time"]
    assert unchanged["start_time"] == alice_appt["start_time"]

    apply_resp = client.post(
        f"{OPT_URL}/what-if/apply",
        json={
            "scenario_type": "MOVE", "appointment_id": alice_appt["id"],
            "new_scheduled_date": str(MONDAY), "new_start_time": "10:00:00",
        },
        headers=admin_headers,
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["applied"] is True
    moved = client.get(f"{APPOINTMENTS_URL}/{alice_appt['id']}", headers=admin_headers).json()
    assert moved["start_time"] == "10:00:00"

    # ============================================================
    # 17. ANALYTICS
    # ============================================================
    overview_resp = client.get(
        f"{ANALYTICS_URL}/overview", params={"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY)},
        headers=admin_headers,
    )
    assert overview_resp.status_code == 200
    overview = overview_resp.json()
    assert overview["total_appointments"] == 2  # Alice + Bob, both still SCHEDULED after the What-If move

    therapist_analytics = client.get(
        f"{ANALYTICS_URL}/therapists", params={"period": "custom", "start_date": str(MONDAY), "end_date": str(MONDAY)},
        headers=admin_headers,
    )
    assert therapist_analytics.status_code == 200
    assert any(t["therapist_id"] == therapist["id"] for t in therapist_analytics.json()["therapists"])

    # accepted_at/rejected_at are stamped with the real current time, not `target_date` (the
    # schedule day the recommendation applies to) - so acceptance activity is queried by
    # period="today" here, exactly like tests/test_analytics_optimization_impact.py does, not by
    # the historical MONDAY the appointments themselves live on.
    impact_resp = client.get(f"{ANALYTICS_URL}/optimization-impact", params={"period": "today"}, headers=admin_headers)
    assert impact_resp.status_code == 200
    assert impact_resp.json()["recommendations_accepted"] == 1  # exactly the one acceptance above, not the rejection

    today_overview = client.get(f"{ANALYTICS_URL}/overview", params={"period": "today"}, headers=admin_headers)
    assert today_overview.status_code == 200
    assert today_overview.json()["recommendations_accepted"] == 1

    # ============================================================
    # 18. AUDIT LOGGING
    # ============================================================
    audit_actions = {
        log.action
        for log in db_session.query(AuditLog).filter(AuditLog.clinic_id == admin_clinic_id).all()
    }
    for expected in [
        "USER_REGISTERED", "LOGIN_SUCCESS", "USER_CREATED", "PATIENT_CREATED", "PATIENT_UPDATED",
        "APPOINTMENT_CREATED", "APPOINTMENT_UPDATED", "OPTIMIZATION_RECOMMENDATION_ACCEPTED", "IMPORT_CONFIRMED",
    ]:
        assert expected in audit_actions, f"expected {expected!r} to have been audit-logged during this journey"

    # Cross-clinic isolation still holds after a full day of activity in the first clinic.
    final_other_check = client.get(PATIENTS_URL, headers=auth_headers(other_admin))
    assert final_other_check.json()["items"] == []
