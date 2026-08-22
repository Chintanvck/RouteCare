"""
RouteCare AI - Role-based access control and tenant-isolation checks.

Defines the four platform roles plus reusable FastAPI dependencies that
enforce them. Every future module (patients, scheduling, optimization,
...) should compose these rather than re-implementing role/tenant
checks:

    @router.delete("/patients/{id}")
    def delete_patient(
        patient_id: uuid.UUID,
        current_user: User = Depends(require_role(UserRole.CLINIC_ADMIN)),
        db: Session = Depends(get_db),
    ):
        patient = db.get(Patient, patient_id) or raise NotFoundError(...)
        require_clinic_access(current_user, patient.clinic_id)
        ...

Note: `get_current_user`/`User` are imported inside the function bodies
below, not at module scope. app.models.user imports UserRole from this
module, so a module-level import of app.core.dependencies (which itself
imports app.models.user) here would be a circular import.
"""

from enum import Enum
from typing import Any, Callable

from app.core.exceptions import ForbiddenError


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    CLINIC_ADMIN = "CLINIC_ADMIN"
    OFFICE_SCHEDULER = "OFFICE_SCHEDULER"
    THERAPIST = "THERAPIST"


def require_role(*allowed_roles: UserRole) -> Callable[..., Any]:
    """
    Build a dependency that only lets callers with one of `allowed_roles`
    through. Raises 403 otherwise.

    Example - scheduling is manageable by schedulers and clinic admins,
    but not by therapists:

        Depends(require_role(UserRole.OFFICE_SCHEDULER, UserRole.CLINIC_ADMIN))
    """
    from fastapi import Depends

    from app.core.dependencies import get_current_user

    def dependency(current_user: Any = Depends(get_current_user)) -> Any:
        if current_user.role not in allowed_roles:
            raise ForbiddenError("You do not have permission to perform this action.")
        return current_user

    return dependency


def ensure_self_or_role(current_user: Any, target_user_id: Any, *allowed_roles: UserRole) -> None:
    """
    Reusable check for "own resource OR privileged role" endpoints, e.g.
    a therapist viewing their own profile/schedule vs. a clinic admin
    viewing anyone's. Raises 403 if neither condition holds.
    """
    if current_user.id == target_user_id:
        return
    if current_user.role in allowed_roles:
        return
    raise ForbiddenError("You do not have permission to access this resource.")


def require_clinic_access(current_user: Any, resource_clinic_id: Any) -> None:
    """
    Reusable check for "does this fetched resource belong to the
    caller's clinic" - use after loading a row by ID, before returning
    or mutating it, e.g.:

        patient = db.get(Patient, patient_id)
        if patient is None:
            raise NotFoundError("Patient was not found.", code="PATIENT_NOT_FOUND")
        require_clinic_access(current_user, patient.clinic_id)

    SYSTEM_ADMIN deliberately bypasses this check - it's the platform
    support/administration role and is expected to be able to reach
    data across clinics. Every other role must match exactly.
    """
    if current_user.role == UserRole.SYSTEM_ADMIN:
        return
    if current_user.clinic_id != resource_clinic_id:
        raise ForbiddenError("You do not have access to this resource.", code="CROSS_TENANT_ACCESS_DENIED")
