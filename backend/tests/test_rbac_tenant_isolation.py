"""
Tests for the reusable RBAC/tenant-isolation dependencies in
app.core.permissions and app.core.dependencies. These are exercised
directly (unit level) since no business endpoints exist yet in Phase 1B
to exercise them through - future modules (patients, scheduling, ...)
are expected to compose them exactly like this.
"""

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_clinic_id
from app.core.exceptions import AppError, register_exception_handlers
from app.core.permissions import UserRole, ensure_self_or_role, require_clinic_access, require_role
from app.core.security import create_access_token
from app.database.session import get_db
from tests.conftest import make_user

# --- Direct/unit-level tests of the dependency callables ---


def test_require_role_allows_matching_role(db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, email="admin@example.com", role=UserRole.CLINIC_ADMIN)

    dependency = require_role(UserRole.CLINIC_ADMIN)
    assert dependency(current_user=admin) is admin


def test_require_role_denies_non_matching_role(db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, email="therapist@example.com", role=UserRole.THERAPIST)

    dependency = require_role(UserRole.CLINIC_ADMIN)
    with pytest.raises(AppError) as exc_info:
        dependency(current_user=therapist)
    assert exc_info.value.status_code == 403


def test_require_role_accepts_multiple_allowed_roles(db_session: Session, clinic) -> None:
    scheduler = make_user(db_session, clinic, email="scheduler@example.com", role=UserRole.OFFICE_SCHEDULER)

    dependency = require_role(UserRole.OFFICE_SCHEDULER, UserRole.CLINIC_ADMIN)
    assert dependency(current_user=scheduler) is scheduler


def test_get_current_clinic_id_returns_clinic_for_scoped_user(db_session: Session, clinic) -> None:
    user = make_user(db_session, clinic, email="user@example.com")
    assert get_current_clinic_id(current_user=user) == clinic.id


def test_get_current_clinic_id_rejects_system_admin_with_no_clinic(db_session: Session) -> None:
    system_admin = make_user(db_session, None, email="sysadmin@example.com", role=UserRole.SYSTEM_ADMIN)

    with pytest.raises(AppError) as exc_info:
        get_current_clinic_id(current_user=system_admin)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "NO_CLINIC_CONTEXT"


def test_ensure_self_or_role_allows_own_resource(db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, email="therapist@example.com", role=UserRole.THERAPIST)
    ensure_self_or_role(therapist, therapist.id, UserRole.CLINIC_ADMIN)  # must not raise


def test_ensure_self_or_role_allows_privileged_role_for_others_resource(db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, email="admin@example.com", role=UserRole.CLINIC_ADMIN)
    other_user_id = uuid.uuid4()
    ensure_self_or_role(admin, other_user_id, UserRole.CLINIC_ADMIN)  # must not raise


def test_ensure_self_or_role_denies_other_resource_without_privilege(db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, email="therapist@example.com", role=UserRole.THERAPIST)
    other_user_id = uuid.uuid4()

    with pytest.raises(AppError) as exc_info:
        ensure_self_or_role(therapist, other_user_id, UserRole.CLINIC_ADMIN)
    assert exc_info.value.status_code == 403


# --- HTTP-level test of the same dependencies wired into a route, the
# way a future module (patients, scheduling, ...) would use them ---


def _build_probe_app() -> FastAPI:
    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    @probe_app.get("/admin-only")
    def admin_only(current_user=Depends(require_role(UserRole.CLINIC_ADMIN, UserRole.SYSTEM_ADMIN))):
        return {"ok": True, "role": current_user.role.value}

    @probe_app.get("/clinic-scoped")
    def clinic_scoped(clinic_id=Depends(get_current_clinic_id)):
        return {"clinic_id": str(clinic_id)}

    return probe_app


@pytest.fixture()
def probe_client(db_session: Session) -> TestClient:
    probe_app = _build_probe_app()
    probe_app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(probe_app)


def _bearer(user) -> dict:
    token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "clinic_id": str(user.clinic_id) if user.clinic_id else None,
            "role": user.role.value,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_probe_admin_route_denies_therapist(probe_client: TestClient, db_session: Session, clinic) -> None:
    therapist = make_user(db_session, clinic, email="therapist@example.com", role=UserRole.THERAPIST)
    response = probe_client.get("/admin-only", headers=_bearer(therapist))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_probe_admin_route_allows_clinic_admin(probe_client: TestClient, db_session: Session, clinic) -> None:
    admin = make_user(db_session, clinic, email="admin@example.com", role=UserRole.CLINIC_ADMIN)
    response = probe_client.get("/admin-only", headers=_bearer(admin))
    assert response.status_code == 200
    assert response.json() == {"ok": True, "role": "CLINIC_ADMIN"}


def test_probe_clinic_scoped_route_isolates_by_token(probe_client: TestClient, db_session: Session) -> None:
    from app.models.clinic import Clinic

    clinic_a = Clinic(name="Clinic A")
    clinic_b = Clinic(name="Clinic B")
    db_session.add_all([clinic_a, clinic_b])
    db_session.commit()

    user_a = make_user(db_session, clinic_a, email="a@example.com")
    user_b = make_user(db_session, clinic_b, email="b@example.com")

    response_a = probe_client.get("/clinic-scoped", headers=_bearer(user_a))
    response_b = probe_client.get("/clinic-scoped", headers=_bearer(user_b))

    assert response_a.json()["clinic_id"] == str(clinic_a.id)
    assert response_b.json()["clinic_id"] == str(clinic_b.id)
    assert response_a.json()["clinic_id"] != response_b.json()["clinic_id"]


def test_probe_clinic_scoped_route_rejects_system_admin(probe_client: TestClient, db_session: Session) -> None:
    system_admin = make_user(db_session, None, email="sysadmin@example.com", role=UserRole.SYSTEM_ADMIN)
    response = probe_client.get("/clinic-scoped", headers=_bearer(system_admin))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_CLINIC_CONTEXT"


# --- require_clinic_access: resource-level tenant isolation, for use
# after loading a row by ID (e.g. GET /patients/{id}) ---


def test_require_clinic_access_allows_matching_clinic(db_session: Session, clinic) -> None:
    user = make_user(db_session, clinic, email="user@example.com")
    require_clinic_access(user, clinic.id)  # must not raise


def test_require_clinic_access_denies_other_clinic(db_session: Session) -> None:
    from app.models.clinic import Clinic

    clinic_a = Clinic(name="Clinic A")
    clinic_b = Clinic(name="Clinic B")
    db_session.add_all([clinic_a, clinic_b])
    db_session.commit()

    user_a = make_user(db_session, clinic_a, email="a@example.com")

    with pytest.raises(AppError) as exc_info:
        require_clinic_access(user_a, clinic_b.id)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "CROSS_TENANT_ACCESS_DENIED"


def test_require_clinic_access_allows_system_admin_across_clinics(db_session: Session, clinic) -> None:
    system_admin = make_user(db_session, None, email="sysadmin@example.com", role=UserRole.SYSTEM_ADMIN)
    require_clinic_access(system_admin, clinic.id)  # must not raise despite no clinic of their own
