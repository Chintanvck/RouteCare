"""
RouteCare AI - Availability request/response schemas.

`day_of_week` follows Python's date.weekday() convention (0=Monday,
6=Sunday) everywhere in this API - see app/models/therapist_availability.py.
"""

import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field, field_validator

from app.models.patient_availability import PatientAvailabilityPreference


class TherapistAvailabilityRuleInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Monday ... 6=Sunday")
    start_time: time
    end_time: time
    is_available: bool = True

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("end_time must be after start_time.")
        return v


class SetTherapistAvailabilityRequest(BaseModel):
    rules: list[TherapistAvailabilityRuleInput]


class TherapistAvailabilityPublic(BaseModel):
    id: uuid.UUID
    therapist_id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time
    is_available: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientAvailabilityRuleInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Monday ... 6=Sunday")
    start_time: time
    end_time: time
    preference_type: PatientAvailabilityPreference

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("end_time must be after start_time.")
        return v


class SetPatientAvailabilityRequest(BaseModel):
    rules: list[PatientAvailabilityRuleInput]


class PatientAvailabilityPublic(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time
    preference_type: PatientAvailabilityPreference
    created_at: datetime

    model_config = {"from_attributes": True}
