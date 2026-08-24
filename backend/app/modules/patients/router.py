"""
RouteCare AI - Patient endpoints.

Read access (list/get) is available to any clinic role (CLINIC_ADMIN,
OFFICE_SCHEDULER, THERAPIST) - THERAPIST is read-only pending Phase 4's
appointment-based "assigned patients" scoping (see
docs/09_Security_Privacy_Compliance.md's role table; there's no
therapist_id/assignment on Patient yet to scope by). Writes
(create/update/delete) are restricted to CLINIC_ADMIN and
OFFICE_SCHEDULER, per that same role table.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_clinic_id
from app.core.permissions import UserRole, require_role
from app.database.session import get_db
from app.models.patient import GeocodingStatus
from app.schemas.availability import PatientAvailabilityPublic, SetPatientAvailabilityRequest
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.maps import PatientGeocodeResponse
from app.schemas.patient import PatientCreate, PatientPublic, PatientUpdate
from app.services import availability_service, patient_service

router = APIRouter()

_READ_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)
_WRITE_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER)


@router.get("", response_model=PaginatedResponse[PatientPublic], dependencies=[Depends(require_role(*_READ_ROLES))])
def list_patients(
    search: str | None = Query(None, description="Matches against first or last name"),
    zip_code: str | None = Query(None),
    sort_by: Literal["name", "created_at", "zip_code"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PatientPublic]:
    items, total = patient_service.list_patients(
        db,
        clinic_id=clinic_id,
        pagination=pagination,
        search=search,
        zip_code=zip_code,
        sort_by=sort_by,
        sort_order=sort_order,
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
    db: Session = Depends(get_db),
) -> PatientPublic:
    patient = patient_service.create_patient(db, clinic_id=clinic_id, data=payload)
    return PatientPublic.model_validate(patient)


@router.get("/{patient_id}", response_model=PatientPublic, dependencies=[Depends(require_role(*_READ_ROLES))])
def get_patient(
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PatientPublic:
    patient = patient_service.get_patient(db, clinic_id=clinic_id, patient_id=patient_id)
    return PatientPublic.model_validate(patient)


@router.patch("/{patient_id}", response_model=PatientPublic, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PatientPublic:
    patient = patient_service.update_patient(db, clinic_id=clinic_id, patient_id=patient_id, data=payload)
    return PatientPublic.model_validate(patient)


@router.delete("/{patient_id}", status_code=204, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def delete_patient(
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> None:
    patient_service.soft_delete_patient(db, clinic_id=clinic_id, patient_id=patient_id)


@router.post(
    "/{patient_id}/geocode",
    response_model=PatientGeocodeResponse,
    dependencies=[Depends(require_role(*_WRITE_ROLES))],
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
    db: Session = Depends(get_db),
) -> list[PatientAvailabilityPublic]:
    patient_service.get_patient(db, clinic_id=clinic_id, patient_id=patient_id)  # 404s for cross-clinic/unknown ids
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
