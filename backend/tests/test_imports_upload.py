"""Tests for POST /api/v1/imports/patients (upload + analyze)."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import UserRole
from app.models.import_job import ImportJob
from tests.conftest import auth_headers, build_theraoffice_xlsx, make_user

IMPORTS_URL = "/api/v1/imports/patients"

VALID_ROWS = [
    ["Mary Smith", "201-555-0100", "mary@example.com", "123 Main St", "Hoboken", "NJ", "07030"],
    ["John Doe", "201-555-0101", "john@example.com", "456 Other St", "Jersey City", "NJ", "07302"],
]


def _upload(client: TestClient, admin, content: bytes, filename: str = "patients.xlsx"):
    return client.post(
        IMPORTS_URL,
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers(admin),
    )


def test_upload_valid_xlsx_succeeds(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    content = build_theraoffice_xlsx(VALID_ROWS)

    response = _upload(client, admin, content)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["total_records"] == 2
    assert "Patient Full Name" in body["detected_headers"]
    assert body["suggested_mapping"].get("full_name") == "Patient Full Name"
    assert body["suggested_mapping"].get("zip_code") == "ZIP"


def test_upload_persists_original_file(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    content = build_theraoffice_xlsx(VALID_ROWS)

    response = _upload(client, admin, content)
    job = db_session.get(ImportJob, response.json()["id"])

    assert Path(job.stored_file_path).exists()
    assert Path(job.stored_file_path).read_bytes() == content
    # Storage is namespaced by clinic - never exposed via any URL.
    assert str(clinic.id) in job.stored_file_path


def test_upload_rejects_unsupported_file_type(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = _upload(client, admin, b"name,zip\nMary,07030", filename="patients.csv")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMPORT_UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_oversized_file(client: TestClient, db_session: Session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    monkeypatch.setattr(settings, "IMPORT_MAX_FILE_SIZE_BYTES", 100)
    content = build_theraoffice_xlsx(VALID_ROWS * 20)

    response = _upload(client, admin, content)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMPORT_FILE_TOO_LARGE"


def test_upload_rejects_corrupted_file(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = _upload(client, admin, b"PK\x03\x04this is not a real zip/xlsx payload" + b"\x00" * 50)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMPORT_FILE_UNREADABLE"


def test_upload_rejects_renamed_non_excel_file(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = _upload(client, admin, b"just some plain text pretending to be excel")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMPORT_FILE_CONTENT_MISMATCH"


def test_upload_flags_missing_headers() -> None:
    from app.core.exceptions import AppError
    from app.services.excel_parser import parse_workbook
    from tests.conftest import build_xlsx_bytes

    content = build_xlsx_bytes([], [])
    try:
        parse_workbook(content, ".xlsx")
        raised = False
    except AppError as exc:
        raised = True
        assert exc.code == "IMPORT_NO_HEADERS"
    assert raised


def test_upload_therapist_forbidden(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    content = build_theraoffice_xlsx(VALID_ROWS)

    response = _upload(client, therapist, content)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_upload_requires_authentication(client: TestClient) -> None:
    content = build_theraoffice_xlsx(VALID_ROWS)
    response = client.post(IMPORTS_URL, files={"file": ("patients.xlsx", content)})
    assert response.status_code == 401


def test_get_import_status(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    upload_response = _upload(client, admin, build_theraoffice_xlsx(VALID_ROWS))
    import_id = upload_response.json()["id"]

    response = client.get(f"/api/v1/imports/{import_id}", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["total_records"] == 2
    assert body["processed_records"] == 0


def test_list_imports_history(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    _upload(client, admin, build_theraoffice_xlsx(VALID_ROWS))
    _upload(client, admin, build_theraoffice_xlsx(VALID_ROWS))

    response = client.get("/api/v1/imports", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["total"] == 2
