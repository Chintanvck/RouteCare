"""RBAC and cross-clinic isolation tests for the imports API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.clinic import Clinic
from tests.conftest import auth_headers, build_theraoffice_xlsx, make_user

VALID_ROWS = [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]]
VALID_MAPPING = {
    "full_name": "Patient Full Name",
    "address_line_1": "Address",
    "city": "City",
    "state": "State",
    "zip_code": "ZIP",
}


def _upload(client: TestClient, user) -> str:
    response = client.post(
        "/api/v1/imports/patients",
        files={"file": ("patients.xlsx", build_theraoffice_xlsx(VALID_ROWS))},
        headers=auth_headers(user),
    )
    return response.json()["id"]


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/imports").status_code == 401


def test_get_requires_authentication(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload(client, admin)
    response = client.get(f"/api/v1/imports/{import_id}")
    assert response.status_code == 401


def test_therapist_cannot_list_imports(client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST)
    response = client.get("/api/v1/imports", headers=auth_headers(therapist))
    assert response.status_code == 403


def test_therapist_cannot_confirm_mapping(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="admin@example.com")
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST, email="therapist@example.com")
    import_id = _upload(client, admin)

    response = client.post(
        f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(therapist)
    )
    assert response.status_code == 403


def test_therapist_cannot_confirm_import(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN, email="admin@example.com")
    therapist = make_user(db_session, clinic, role=UserRole.THERAPIST, email="therapist@example.com")
    import_id = _upload(client, admin)

    response = client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=auth_headers(therapist))
    assert response.status_code == 403


def test_office_scheduler_can_upload_and_confirm(
    client: TestClient, db_session: Session, clinic, sync_import_tasks
) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER)
    import_id = _upload(client, scheduler)

    mapping_response = client.post(
        f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(scheduler)
    )
    assert mapping_response.status_code == 200

    confirm_response = client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=auth_headers(scheduler))
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "COMPLETED"


def test_system_admin_cannot_access_imports(client: TestClient, db_session: Session, clinic) -> None:
    system_admin = make_user(db_session, None, role=UserRole.SYSTEM_ADMIN, email="sysadmin@example.com")
    response = client.get("/api/v1/imports", headers=auth_headers(system_admin))
    assert response.status_code == 403


def _other_clinic_admin(db_session: Session) -> tuple[Clinic, object]:
    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    other_admin = make_user(db_session, other_clinic, role=UserRole.CLINIC_ADMIN, email="other-admin@example.com")
    return other_clinic, other_admin


def test_cross_clinic_get_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload(client, admin)

    _other_clinic, other_admin = _other_clinic_admin(db_session)
    response = client.get(f"/api/v1/imports/{import_id}", headers=auth_headers(other_admin))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMPORT_NOT_FOUND"


def test_cross_clinic_mapping_returns_404(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload(client, admin)

    _other_clinic, other_admin = _other_clinic_admin(db_session)
    response = client.post(
        f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(other_admin)
    )
    assert response.status_code == 404


def test_cross_clinic_preview_returns_404(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload(client, admin)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    _other_clinic, other_admin = _other_clinic_admin(db_session)
    response = client.get(f"/api/v1/imports/{import_id}/preview", headers=auth_headers(other_admin))
    assert response.status_code == 404


def test_cross_clinic_errors_returns_404(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload(client, admin)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    _other_clinic, other_admin = _other_clinic_admin(db_session)
    response = client.get(f"/api/v1/imports/{import_id}/errors", headers=auth_headers(other_admin))
    assert response.status_code == 404


def test_cross_clinic_confirm_returns_404(client: TestClient, db_session: Session, clinic, sync_import_tasks) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    import_id = _upload(client, admin)
    client.post(f"/api/v1/imports/{import_id}/mapping", json={"mapping": VALID_MAPPING}, headers=auth_headers(admin))

    _other_clinic, other_admin = _other_clinic_admin(db_session)
    response = client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=auth_headers(other_admin))
    assert response.status_code == 404


def test_cross_clinic_list_never_leaks_others_imports(client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    _upload(client, admin)

    _other_clinic, other_admin = _other_clinic_admin(db_session)
    _upload(client, other_admin)

    response = client.get("/api/v1/imports", headers=auth_headers(admin))
    assert response.json()["total"] == 1
