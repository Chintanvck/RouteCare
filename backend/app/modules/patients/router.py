"""
RouteCare AI - Patient endpoints.

Read access (list/get) is available to any clinic role (CLINIC_ADMIN,
OFFICE_SCHEDULER, THERAPIST), but a THERAPIST caller is always further
restricted to patients they have (or had) at least one appointment with
(Phase 11 - see patient_service._active_patients_query's docstring for
why this is done via the existing Appointment relationship rather than
a new therapist_id/assignment column on Patient) - UNLESS the request
opts into `?for_scheduling=true` on the list endpoint, which lifts that
restriction for a THERAPIST so the New Appointment picker can offer any
active clinic patient, including one they've never been scheduled with
before (that first appointment is what establishes the relationship -
see appointment_service.create_appointment). Every other read path keeps
the "already assigned" restriction unchanged. Writes (create/update/
delete) are restricted to CLINIC_ADMIN and OFFICE_SCHEDULER, per
docs/09_Security_Privacy_Compliance.md's role table.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_clinic_id, get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import UserRole, require_role
from app.core.rate_limiting import rate_limit
from app.database.session import get_db
from app.models.patient import GeocodingStatus
from app.models.user import User
from app.schemas.availability import PatientAvailabilityPublic, SetPatientAvailabilityRequest
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.maps import PatientGeocodeResponse
from app.schemas.patient import PatientCreate, PatientPublic, PatientUpdate
from app.services import availability_service, patient_service, therapist_service

router = APIRouter()

_READ_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)
_WRITE_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER)


def _own_therapist_id_if_therapist(db: Session, *, clinic_id: uuid.UUID, current_user: User) -> uuid.UUID | None:
    """Mirrors app.modules.scheduling.router's helper (Phase 11) - a THERAPIST caller only ever
    sees patients they have at least one appointment with (see
    patient_service._active_patients_query); None for CLINIC_ADMIN/OFFICE_SCHEDULER (no
    restriction - clinic-wide patient access, per existing RBAC)."""
    if current_user.role != UserRole.THERAPIST:
        return None
    therapist = therapist_service.get_therapist_by_user_id(db, clinic_id=clinic_id, user_id=current_user.id)
    if therapist is None:
        raise NotFoundError("Patient was not found.", code="PATIENT_NOT_FOUND")
    return therapist.id


@router.get("", response_model=PaginatedResponse[PatientPublic], dependencies=[Depends(require_role(*_READ_ROLES))])
def list_patients(
    search: str | None = Query(None, description="Matches against first or last name"),
    zip_code: str | None = Query(None),
    sort_by: Literal["name", "created_at", "zip_code"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    for_scheduling: bool = Query(
        False,
        description=(
            "When true, a THERAPIST sees every active clinic patient, not just ones they already "
            "have an appointment with - lets the New Appointment picker offer a patient the "
            "therapist hasn't been scheduled with before (see appointment_service.create_appointment). "
            "No effect for CLINIC_ADMIN/OFFICE_SCHEDULER, who already see the full clinic list."
        ),
    ),
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PatientPublic]:
    restrict_to = None if for_scheduling else _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    items, total = patient_service.list_patients(
        db,
        clinic_id=clinic_id,
        pagination=pagination,
        search=search,
        zip_code=zip_code,
        sort_by=sort_by,
        sort_order=sort_order,
        restrict_to_therapist_id=restrict_to,
    )
    patients = [PatientPublic.model_validate(item) for item in items]
    return PaginatedResponse.create(patients, page=pagination.page, page_size=pagination.page_size, total=total)


@router.post(
    "",
    response_model=PatientPublic,
    status_code=201,
    dependencies=[Depends(require_role(*_WRITE_ROLES))],
)
def create_patient(
    payload: PatientCreate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientPublic:
    patient = patient_service.create_patient(db, clinic_id=clinic_id, data=payload, actor_user_id=current_user.id)
    return PatientPublic.model_validate(patient)


@router.get("/{patient_id}", response_model=PatientPublic, dependencies=[Depends(require_role(*_READ_ROLES))])
def get_patient(
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientPublic:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    patient = patient_service.get_patient(
        db, clinic_id=clinic_id, patient_id=patient_id, restrict_to_therapist_id=restrict_to
    )
    return PatientPublic.model_validate(patient)


@router.patch("/{patient_id}", response_model=PatientPublic, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientPublic:
    patient = patient_service.update_patient(
        db, clinic_id=clinic_id, patient_id=patient_id, data=payload, actor_user_id=current_user.id
    )
    return PatientPublic.model_validate(patient)


@router.delete("/{patient_id}", status_code=204, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def delete_patient(
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    patient_service.soft_delete_patient(db, clinic_id=clinic_id, patient_id=patient_id, actor_user_id=current_user.id)


@router.post(
    "/{patient_id}/geocode",
    response_model=PatientGeocodeResponse,
    dependencies=[
        Depends(require_role(*_WRITE_ROLES)),
        Depends(
            rate_limit(
                "geocode", limit=settings.RATE_LIMIT_GEOCODE_MAX, window_seconds=settings.RATE_LIMIT_GEOCODE_WINDOW_SECONDS
            )
        ),
    ],
)
def geocode_patient(
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PatientGeocodeResponse:
    patient, normalized_address = patient_service.geocode_patient(db, clinic_id=clinic_id, patient_id=patient_id)
    return PatientGeocodeResponse(
        success=patient.geocoding_status == GeocodingStatus.GEOCODED,
        normalized_address=normalized_address,
        patient=PatientPublic.model_validate(patient),
    )


@router.get(
    "/{patient_id}/availability",
    response_model=list[PatientAvailabilityPublic],
    dependencies=[Depends(require_role(*_READ_ROLES))],
)
def get_patient_availability(
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PatientAvailabilityPublic]:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    # 404s for cross-clinic/unknown/unauthorized (not-my-patient) ids alike.
    patient_service.get_patient(db, clinic_id=clinic_id, patient_id=patient_id, restrict_to_therapist_id=restrict_to)
    rows = availability_service.get_patient_availability(db, patient_id=patient_id)
    return [PatientAvailabilityPublic.model_validate(r) for r in rows]


@router.put(
    "/{patient_id}/availability",
    response_model=list[PatientAvailabilityPublic],
    dependencies=[Depends(require_role(*_WRITE_ROLES))],
)
def set_patient_availability(
    patient_id: uuid.UUID,
    payload: SetPatientAvailabilityRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> list[PatientAvailabilityPublic]:
    patient_service.get_patient(db, clinic_id=clinic_id, patient_id=patient_id)
    rows = availability_service.set_patient_availability(db, patient_id=patient_id, rules=payload.rules)
    return [PatientAvailabilityPublic.model_validate(r) for r in rows]
