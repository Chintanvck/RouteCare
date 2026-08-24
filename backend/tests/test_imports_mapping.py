"""Tests for POST /api/v1/imports/{id}/mapping and the preview/errors/confirm endpoints,
exercised through the real API using the sync_import_tasks fixture (see conftest.py)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.conftest import auth_headers, build_theraoffice_xlsx, make_user

VALID_ROWS = [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]]

VALID_MAPPING = {
    "full_name": "Patient Full Name",
    "address_line_1": "Address",
    "city": "City",
    "state": "State",
    "zip_code": "ZIP",
}


def _upload_and_get_id(client: TestClient, admin, rows=VALID_ROWS) -> str:
    response = client.post(
        "/api/v1/imports/patients",
        files={"file": ("patients.xlsx", build_theraoffice_xlsx(rows))},
        headers=auth_headers(admin),
    )
    return response.json()["id"]


def test_confirm_mapping_triggers_validation(
    client: TestClient, db_session: Session, clinic, sync_import_tasks
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload_and_get_id(client, admin)

    response = client.post(
        f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["status"] == "PENDING"
    )  # PROCESSING immediately, then back to PENDING once validation (run inline here) finishes
    assert body["valid_records"] == 1
    assert body["total_records"] == 1


def test_confirm_mapping_rejects_incomplete_mapping(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload_and_get_id(client, admin)

    response = client.post(
        f"/api/v1/imports/{import_id}/mapping",
        json={"mapping": {"full_name": "Patient Full Name"}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMPORT_MAPPING_INVALID"
    assert "problems" in response.json()["error"]["details"]


def test_preview_shows_row_classifications(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload_and_get_id(client, admin)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    response = client.get(f"/api/v1/imports/{import_id}/preview", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["classification"] == "VALID"
    assert body["items"][0]["mapped_data"]["first_name"] == "Mary"


def test_errors_endpoint_lists_row_errors(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    bad_rows = [["", "", "", "123 Main St", "Hoboken", "NJ", "bad-zip"]]
    import_id = _upload_and_get_id(client, admin, rows=bad_rows)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    response = client.get(f"/api/v1/imports/{import_id}/errors", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["items"][0]["row_number"] == 1


def test_confirm_import_end_to_end(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload_and_get_id(client, admin)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    response = client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["successful_records"] == 1
    assert body["failed_records"] == 0

    patients_response = client.get("/api/v1/patients", headers=auth_headers(admin))
    assert patients_response.json()["total"] == 1


def test_confirm_import_before_validation_rejected(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload_and_get_id(client, admin)

    response = client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=auth_headers(admin))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMPORT_NOT_READY"


def test_cancel_before_confirmation_leaves_no_patients(
    client: TestClient, db_session: Session, clinic, sync_import_tasks
) -> None:
    """'Cancelling' is simply never calling confirm - nothing should have been written."""
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload_and_get_id(client, admin)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    patients_response = client.get("/api/v1/patients", headers=auth_headers(admin))
    assert patients_response.json()["total"] == 0
