"""
RouteCare AI - Appointment/calendar endpoints.

CLINIC_ADMIN and OFFICE_SCHEDULER can create/manage any appointment in
the clinic; THERAPIST can view and lightly manage (reschedule/status)
only their own appointments - see app.services.appointment_service's
`restrict_to_therapist_id` mechanism, resolved here once per request
via the caller's linked Therapist profile.

Calendar views (day/week) are just this same list endpoint with a
start_date/end_date range - see docs/13_Coding_Standards.md-style
reasoning: one well-parameterized endpoint beats several overlapping
ones (superseding docs/05_API_Design.md's separate /schedule/day,
/schedule/week suggestions, per this phase's explicit instruction to
fold calendar retrieval into GET /appointments).

POST /appointments/validate is a dry-run beyond the minimal required
endpoint list - it exists because the manual-scheduling UX explicitly
separates "validate" from "create," and drag-and-drop explicitly
requires validating a proposed move before committing it. It reuses
the exact same validation function create/update call, so it can never
say "fine" when the real thing would fail.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_clinic_id, get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import UserRole, require_role
from app.database.session import get_db
from app.models.appointment import AppointmentStatus
from app.models.user import User
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentPublic,
    AppointmentUpdate,
    AppointmentValidateRequest,
    AppointmentValidateResponse,
)
from app.schemas.common import PaginatedResponse, PaginationParams
from app.services import appointment_service, therapist_service

router = APIRouter()

_READ_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)
_WRITE_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER)
_MODIFY_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)


def _own_therapist_id_if_therapist(db: Session, *, clinic_id: uuid.UUID, current_user: User) -> uuid.UUID | None:
    """Returns the caller's own therapist_id to force-scope by, or None if they're not a
    THERAPIST (i.e. no restriction needed for CLINIC_ADMIN/OFFICE_SCHEDULER)."""
    if current_user.role != UserRole.THERAPIST:
        return None
    therapist = therapist_service.get_therapist_by_user_id(db, clinic_id=clinic_id, user_id=current_user.id)
    if therapist is None:
        # A THERAPIST-role user with no linked Therapist profile can't have any appointments.
        raise NotFoundError("Appointment was not found.", code="APPOINTMENT_NOT_FOUND")
    return therapist.id


@router.get("", response_model=PaginatedResponse[AppointmentPublic], dependencies=[Depends(require_role(*_READ_ROLES))])
def list_appointments(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    therapist_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    status: AppointmentStatus | None = Query(None),
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AppointmentPublic]:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    items, total = appointment_service.list_appointments(
        db,
        clinic_id=clinic_id,
        pagination=pagination,
        start_date=start_date,
        end_date=end_date,
        therapist_id=therapist_id,
        patient_id=patient_id,
        status=status,
        restrict_to_therapist_id=restrict_to,
    )
    appointments = [AppointmentPublic.model_validate(item) for item in items]
    return PaginatedResponse.create(appointments, page=pagination.page, page_size=pagination.page_size, total=total)


@router.post("", response_model=AppointmentPublic, status_code=201, dependencies=[Depends(require_role(*_WRITE_ROLES))])
def create_appointment(
    payload: AppointmentCreate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentPublic:
    appointment = appointment_service.create_appointment(
        db, clinic_id=clinic_id, created_by=current_user.id, data=payload
    )
    return AppointmentPublic.model_validate(appointment)


@router.post(
    "/validate", response_model=AppointmentValidateResponse, dependencies=[Depends(require_role(*_WRITE_ROLES))]
)
def validate_appointment(
    payload: AppointmentValidateRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> AppointmentValidateResponse:
    errors = appointment_service.validate_appointment(
        db,
        clinic_id=clinic_id,
        therapist_id=payload.therapist_id,
        patient_id=payload.patient_id,
        scheduled_date=payload.scheduled_date,
        start_time=payload.start_time,
        duration_minutes=payload.duration_minutes,
        exclude_appointment_id=payload.exclude_appointment_id,
    )
    return AppointmentValidateResponse(valid=not errors, errors=errors)


@router.get("/{appointment_id}", response_model=AppointmentPublic, dependencies=[Depends(require_role(*_READ_ROLES))])
def get_appointment(
    appointment_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentPublic:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    appointment = appointment_service.get_appointment(
        db, clinic_id=clinic_id, appointment_id=appointment_id, restrict_to_therapist_id=restrict_to
    )
    return AppointmentPublic.model_validate(appointment)


@router.patch(
    "/{appointment_id}", response_model=AppointmentPublic, dependencies=[Depends(require_role(*_MODIFY_ROLES))]
)
def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentPublic:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    appointment = appointment_service.update_appointment(
        db,
        clinic_id=clinic_id,
        appointment_id=appointment_id,
        data=payload,
        current_user=current_user,
        restrict_to_therapist_id=restrict_to,
    )
    return AppointmentPublic.model_validate(appointment)


@router.delete("/{appointment_id}", status_code=204, dependencies=[Depends(require_role(*_MODIFY_ROLES))])
def cancel_appointment(
    appointment_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    appointment_service.cancel_appointment(
        db,
        clinic_id=clinic_id,
        appointment_id=appointment_id,
        restrict_to_therapist_id=restrict_to,
        actor_user_id=current_user.id,
    )
