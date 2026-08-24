"""
RouteCare AI - Appointment request/response schemas.

Requests take `start_time` + `duration_minutes` (matching
docs/05_API_Design.md's example shape) rather than start_time+end_time -
`end_time` is computed server-side so the client can never send an
inconsistent trio of start/end/duration.
"""

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    therapist_id: uuid.UUID
    scheduled_date: date
    start_time: time
    duration_minutes: int = Field(gt=0, le=480)


class AppointmentUpdate(BaseModel):
    """PATCH semantics - only supplied fields change. Note: THERAPIST-role callers are further
    restricted (start_time/duration_minutes/status only) by the service layer, not by this schema -
    the schema describes what's structurally possible, RBAC decides what's allowed for whom."""

    patient_id: uuid.UUID | None = None
    therapist_id: uuid.UUID | None = None
    scheduled_date: date | None = None
    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=480)
    status: AppointmentStatus | None = None


class AppointmentValidateRequest(BaseModel):
    patient_id: uuid.UUID
    therapist_id: uuid.UUID
    scheduled_date: date
    start_time: time
    duration_minutes: int = Field(gt=0, le=480)
    exclude_appointment_id: uuid.UUID | None = Field(
        default=None, description="Pass the appointment's own id when validating a proposed move."
    )


class AppointmentValidateResponse(BaseModel):
    valid: bool
    errors: list[str]


class AppointmentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    therapist_id: uuid.UUID
    scheduled_date: date
    start_time: time
    end_time: time
    duration_minutes: int
    status: AppointmentStatus
    appointment_source: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # Enrichment for calendar rendering - avoids a second round-trip per appointment.
    patient_name: str
    therapist_name: str

    model_config = {"from_attributes": True}
