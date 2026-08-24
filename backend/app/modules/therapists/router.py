"""
RouteCare AI - Therapist endpoints.

Read access (list/get/availability) is available to any clinic role;
create/update/availability-write are restricted to CLINIC_ADMIN and
OFFICE_SCHEDULER, matching Patient management's pattern and
docs/09_Security_Privacy_Compliance.md's role table.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_clinic_id
from app.core.permissions import UserRole, require_role
from app.database.session import get_db
from app.schemas.availability import SetTherapistAvailabilityRequest, TherapistAvailabilityPublic
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.therapist import TherapistCreate, TherapistPublic, TherapistUpdate
from app.services import availability_service, therapist_service

router = APIRouter()

_READ_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)
_WRITE_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER)


@router.get("", response_model=PaginatedResponse[TherapistPublic], dependencies=[Depends(require_role(*_READ_ROLES))])
def list_therapists(
    search: str | None = Query(None, description="Matches against first or last name"),
    is_active: bool | None = Query(None),
    sort_by: Literal["name", "created_at"] = Query("name"),
    sort_order: Literal["asc", "desc"] = Query("asc"),
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PaginatedResponse[TherapistPublic]:
    items, total = therapist_service.list_therapists(
        db,
        clinic_id=clinic_id,
        pagination=pagination,
        search=search,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    therapists = [TherapistPublic.model_validate(item) for item in items]
    return PaginatedResponse.create(therapists, page=pagination.page, page_size=pagination.page_size, total=total)


@router.post("", response_model=TherapistPublic, status_code=201, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def create_therapist(
    payload: TherapistCreate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> TherapistPublic:
    therapist = therapist_service.create_therapist(db, clinic_id=clinic_id, data=payload)
    return TherapistPublic.model_validate(therapist)


@router.get("/{therapist_id}", response_model=TherapistPublic, dependencies=[Depends(require_role(*_READ_ROLES))])
def get_therapist(
    therapist_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> TherapistPublic:
    therapist = therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id)
    return TherapistPublic.model_validate(therapist)


@router.patch("/{therapist_id}", response_model=TherapistPublic, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def update_therapist(
    therapist_id: uuid.UUID,
    payload: TherapistUpdate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> TherapistPublic:
    therapist = therapist_service.update_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id, data=payload)
    return TherapistPublic.model_validate(therapist)


@router.get(
    "/{therapist_id}/availability",
    response_model=list[TherapistAvailabilityPublic],
    dependencies=[Depends(require_role(*_READ_ROLES))],
)
def get_therapist_availability(
    therapist_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> list[TherapistAvailabilityPublic]:
    therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id)  # 404s cross-clinic/unknown
    rows = availability_service.get_therapist_availability(db, therapist_id=therapist_id)
    return [TherapistAvailabilityPublic.model_validate(r) for r in rows]


@router.put(
    "/{therapist_id}/availability",
    response_model=list[TherapistAvailabilityPublic],
    dependencies=[Depends(require_role(*_WRITE_ROLES))],
)
def set_therapist_availability(
    therapist_id: uuid.UUID,
    payload: SetTherapistAvailabilityRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> list[TherapistAvailabilityPublic]:
    therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id)
    rows = availability_service.set_therapist_availability(db, therapist_id=therapist_id, rules=payload.rules)
    return [TherapistAvailabilityPublic.model_validate(r) for r in rows]
