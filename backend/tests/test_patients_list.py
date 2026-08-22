"""Tests for GET /api/v1/patients: pagination, search, ZIP filter, sorting, soft-delete exclusion."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.conftest import auth_headers, make_patient, make_user

PATIENTS_URL = "/api/v1/patients"


def test_list_patients_empty(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.get(PATIENTS_URL, headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 0


def test_list_patients_default_pagination(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    for i in range(30):
        make_patient(db_session, clinic, first_name=f"Patient{i}", zip_code="07030")

    response = client.get(PATIENTS_URL, headers=auth_headers(admin))

    body = response.json()
    assert body["total"] == 30
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert len(body["items"]) == 25
    assert body["total_pages"] == 2


def test_list_patients_second_page(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    for i in range(30):
        make_patient(db_session, clinic, first_name=f"Patient{i}", zip_code="07030")

    response = client.get(f"{PATIENTS_URL}?page=2", headers=auth_headers(admin))

    body = response.json()
    assert len(body["items"]) == 5


def test_list_patients_page_size_capped(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.get(f"{PATIENTS_URL}?page_size=1000", headers=auth_headers(admin))
    assert response.status_code == 422


def test_search_by_first_name(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Mary", last_name="Smith")
    make_patient(db_session, clinic, first_name="John", last_name="Doe")

    response = client.get(f"{PATIENTS_URL}?search=mary", headers=auth_headers(admin))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["first_name"] == "Mary"


def test_search_by_last_name_case_insensitive(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Mary", last_name="Smith")
    make_patient(db_session, clinic, first_name="John", last_name="Doe")

    response = client.get(f"{PATIENTS_URL}?search=SMITH", headers=auth_headers(admin))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["last_name"] == "Smith"


def test_filter_by_zip_code(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Mary", zip_code="07030")
    make_patient(db_session, clinic, first_name="John", zip_code="10001")

    response = client.get(f"{PATIENTS_URL}?zip_code=07030", headers=auth_headers(admin))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["zip_code"] == "07030"


def test_sort_by_name_ascending(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="Zoe", last_name="Zephyr")
    make_patient(db_session, clinic, first_name="Amy", last_name="Adams")

    response = client.get(f"{PATIENTS_URL}?sort_by=name&sort_order=asc", headers=auth_headers(admin))

    names = [item["last_name"] for item in response.json()["items"]]
    assert names == ["Adams", "Zephyr"]


def test_sort_by_zip_code_descending(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    make_patient(db_session, clinic, first_name="A", zip_code="01000")
    make_patient(db_session, clinic, first_name="B", zip_code="99000")

    response = client.get(f"{PATIENTS_URL}?sort_by=zip_code&sort_order=desc", headers=auth_headers(admin))

    zips = [item["zip_code"] for item in response.json()["items"]]
    assert zips == ["99000", "01000"]


def test_deleted_patients_excluded_from_list(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, first_name="Mary")
    make_patient(db_session, clinic, first_name="John")

    client.delete(f"{PATIENTS_URL}/{patient.id}", headers=auth_headers(admin))
    response = client.get(PATIENTS_URL, headers=auth_headers(admin))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["first_name"] == "John"


def test_invalid_sort_by_value_rejected(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.get(f"{PATIENTS_URL}?sort_by=ssn", headers=auth_headers(admin))
    assert response.status_code == 422
