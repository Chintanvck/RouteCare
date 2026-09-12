"""
RouteCare AI - Patient search for the "New Appointment" patient picker.

GET /patients already supported a `search` param (ILIKE against first_name
OR last_name, case-insensitive, DB-side - see patient_service.list_patients)
before this change; test_patients_list.py covers the basic
search-by-first-name / search-by-last-name-case-insensitive cases as a
CLINIC_ADMIN. This file is the single place exercising the combinations
that specifically matter for the new searchable patient combobox:
partial-substring matching, disambiguating similarly-named patients,
search combined with a THERAPIST's authorization restriction (both the
default "already assigned" scope and the `for_scheduling=true` opt-in that
lets them find a not-yet-assigned same-clinic patient), and that cross-
clinic isolation holds under search exactly like it does unfiltered.

No new backend endpoint was needed for this feature - GET /patients'
existing `search`/`for_scheduling`/pagination/clinic-scoping already cover
everything the picker requires; only the frontend changed to call it
incrementally instead of loading the whole clinic roster upfront.
"""

from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.clinic import Clinic
from tests.conftest import (
    auth_headers,
    make_appointment,
    make_patient,
    make_therapist,
    make_user,
    make_weekday_availability,
)

PATIENTS_URL = "/api/v1/patients"
APPOINTMENTS_URL = "/api/v1/appointments"

MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


# ============================================================
# Partial / substring matching
# ============================================================


def test_partial_first_name_search_matches_substring(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Johnathan", last_name="Reyes", email="j1@example.com")
    make_patient(db_session, clinic, first_name="Johnny", last_name="Davis", email="j2@example.com")
    make_patient(db_session, clinic, first_name="Sarah", last_name="Lee", email="s@example.com")

    response = client.get(f"{PATIENTS_URL}?search=john", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    names = {p["first_name"] for p in body["items"]}
    assert names == {"Johnathan", "Johnny"}


def test_partial_last_name_search_matches_substring(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="John", last_name="Smith", email="j1@example.com")
    make_patient(db_session, clinic, first_name="Sarah", last_name="Smithson", email="j2@example.com")
    make_patient(db_session, clinic, first_name="Amy", last_name="Lee", email="a@example.com")

    response = client.get(f"{PATIENTS_URL}?search=smith", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    names = {p["last_name"] for p in body["items"]}
    assert names == {"Smith", "Smithson"}


def test_search_is_case_insensitive_for_partial_matches(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Johnny", last_name="Davis")

    response = client.get(f"{PATIENTS_URL}?search=JOHN", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_search_no_results(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Mary", last_name="Smith")

    response = client.get(f"{PATIENTS_URL}?search=zzzznotfound", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_search_disambiguates_similar_names_via_address(client: TestClient, db_session: Session, clinic) -> None:
    """Two same-named patients must both come back, each still carrying the location fields
    (already part of PatientPublic) the picker uses to tell them apart - no new field needed."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(
        db_session, clinic, first_name="John", last_name="Smith", email="js1@example.com",
        city="Hoboken", zip_code="07030",
    )
    make_patient(
        db_session, clinic, first_name="John", last_name="Smith", email="js2@example.com",
        city="Jersey City", zip_code="07302",
    )

    response = client.get(f"{PATIENTS_URL}?search=smith", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    cities = {p["city"] for p in body["items"]}
    assert cities == {"Hoboken", "Jersey City"}


# ============================================================
# Search + THERAPIST authorization
# ============================================================


def test_therapist_search_without_for_scheduling_only_returns_assigned_patients(
    client: TestClient, db_session: Session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic)
    assigned = make_patient(db_session, clinic, first_name="Johnny", last_name="Assigned", email="a@example.com")
    make_patient(db_session, clinic, first_name="Johnny", last_name="Unassigned", email="u@example.com")
    make_appointment(
        db_session, clinic, patient=assigned, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )

    response = client.get(f"{PATIENTS_URL}?search=johnny", headers=auth_headers(therapist.user))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["last_name"] == "Assigned"


def test_therapist_search_with_for_scheduling_finds_unassigned_same_clinic_patient(
    client: TestClient, db_session: Session, clinic
) -> None:
    """This is the key case the New Appointment picker relies on: a therapist must be able to find
    a same-clinic patient they've never been scheduled with before, to create a first appointment."""
    therapist = make_therapist(db_session, clinic)
    make_patient(db_session, clinic, first_name="Johnny", last_name="Unassigned")

    response = client.get(f"{PATIENTS_URL}?search=johnny&for_scheduling=true", headers=auth_headers(therapist.user))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["last_name"] == "Unassigned"


def test_therapist_search_never_returns_another_clinics_patient(
    client: TestClient, db_session: Session, clinic
) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    therapist = make_therapist(db_session, clinic)
    make_patient(db_session, other_clinic, first_name="Johnny", last_name="OtherClinic", email="oc@example.com")

    response = client.get(f"{PATIENTS_URL}?search=johnny&for_scheduling=true", headers=auth_headers(therapist.user))

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_admin_search_never_returns_another_clinics_patient(client: TestClient, db_session: Session, clinic) -> None:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, other_clinic, first_name="Johnny", last_name="OtherClinic", email="oc@example.com")

    response = client.get(f"{PATIENTS_URL}?search=johnny", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["total"] == 0


# ============================================================
# Full chain: search -> select -> create appointment
# ============================================================


def test_therapist_can_search_and_create_first_appointment_with_result(
    client: TestClient, db_session: Session, clinic
) -> None:
    """Proves the id returned by a search result is directly usable to create the appointment -
    the same id the frontend combobox would submit after a user picks a result."""
    therapist = make_therapist(db_session, clinic)
    make_weekday_availability(db_session, therapist)
    make_patient(db_session, clinic, first_name="Johnny", last_name="NewPatient")

    search_resp = client.get(
        f"{PATIENTS_URL}?search=johnny&for_scheduling=true", headers=auth_headers(therapist.user)
    )
    assert search_resp.json()["total"] == 1
    found_patient_id = search_resp.json()["items"][0]["id"]

    create_resp = client.post(
        APPOINTMENTS_URL,
        json={
            "patient_id": found_patient_id,
            "scheduled_date": str(MONDAY),
            "start_time": "10:00:00",
            "duration_minutes": 30,
        },
        headers=auth_headers(therapist.user),
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["patient_id"] == found_patient_id
    assert create_resp.json()["therapist_id"] == str(therapist.id)


def test_search_results_are_paginated_with_a_small_limit(client: TestClient, db_session: Session, clinic) -> None:
    """The picker asks for a small page_size (not the whole clinic) - confirms the existing
    pagination plumbing honors that instead of silently returning everything."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    for i in range(15):
        make_patient(db_session, clinic, first_name=f"Johnny{i}", last_name="Match", email=f"j{i}@example.com")

    response = client.get(f"{PATIENTS_URL}?search=johnny&page_size=5", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 15
    assert len(body["items"]) == 5
